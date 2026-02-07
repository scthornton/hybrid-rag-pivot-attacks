"""A2: Entity Anchor Injection.

Injected chunks heavily mention high-value entities to force entity
linking into sensitive graph neighborhoods. The chunk text is designed
to trigger NER extraction of specific entity names that sit on the
boundary of sensitive subgraphs.

Attack surface: entity linking (Step 2 of hybrid pipeline)
Threat model: attacker knows entity names near sensitive neighborhoods
Defense coverage: D2 (edge allowlist) and D3 (budgets) partially mitigate
"""

from __future__ import annotations

import uuid
from typing import Any

from pivorag.attacks.base import AttackResult, BaseAttack, InjectionPayload

# Target entities that sit near sensitive graph neighborhoods
# Organized by the sensitive area they provide access to
TARGET_ENTITIES = {
    "security_credentials": {
        "anchor_entities": [
            "auth-service", "Vault", "credential-vault",
            "k8s-prod-cluster", "api-gateway",
        ],
        "sensitive_neighbors": [
            "admin passwords", "API keys", "service accounts",
        ],
    },
    "financial_data": {
        "anchor_entities": [
            "CloudCorp", "DataSync Inc", "SecureNet LLC",
            "SOC 2 audit", "PCI DSS",
        ],
        "sensitive_neighbors": [
            "contract values", "budget details", "vendor pricing",
        ],
    },
    "hr_records": {
        "anchor_entities": [
            "Maria Chen", "James Rodriguez", "Aisha Patel",
            "Project Nexus", "Project Horizon",
        ],
        "sensitive_neighbors": [
            "salary data", "compensation packages", "performance reviews",
        ],
    },
}

# Templates that densely mention target entities (3+ mentions per chunk)
ANCHOR_TEMPLATES = [
    (
        "Technical review of {entity} integration patterns. "
        "The {entity} system has been evaluated for compliance with internal standards. "
        "Key finding: {entity} requires updated access controls to meet the latest "
        "security requirements. Contact the {entity} team for remediation timeline. "
        "Related systems: {related_1}, {related_2}."
    ),
    (
        "Monthly status update for {entity} operations. "
        "{entity} processed 500,000 transactions this month with 99.9% uptime. "
        "The {entity} maintenance window is scheduled for next Saturday. "
        "Dependencies affected: {related_1} and {related_2}. "
        "No critical issues reported for {entity} this period."
    ),
    (
        "Reference architecture for {entity} deployment. "
        "The {entity} service connects to {related_1} for data persistence "
        "and {related_2} for authentication. "
        "{entity} is classified as a Tier-1 critical service. "
        "Disaster recovery for {entity} follows the standard playbook."
    ),
]


class EntityAnchorAttack(BaseAttack):
    """A2: Force entity linking to sensitive graph neighborhoods.

    Strategy:
    1. Identify target entities near sensitive nodes (1-2 hops away)
    2. Craft benign-looking documents that mention those entities 3+ times
    3. When NER processes these documents, it creates MENTIONS edges
    4. Future queries retrieving these chunks trigger expansion toward sensitive area
    """

    def __init__(
        self,
        injection_budget: int = 10,
        target_area: str = "security_credentials",
        attacker_tenant: str = "acme_engineering",
    ) -> None:
        super().__init__(injection_budget)
        self.target_area = target_area
        self.attacker_tenant = attacker_tenant

    @property
    def name(self) -> str:
        return "A2_entity_anchor"

    def generate_payloads(
        self,
        target_queries: list[str],
        corpus_stats: dict[str, Any] | None = None,
    ) -> list[InjectionPayload]:
        """Generate chunks densely mentioning target entities.

        Each payload mentions a primary target entity 3+ times and
        includes 2 related entities to create additional graph edges.
        """
        target_config = TARGET_ENTITIES.get(
            self.target_area,
            TARGET_ENTITIES["security_credentials"],
        )
        anchor_entities = target_config["anchor_entities"]

        payloads = []
        for i in range(min(self.injection_budget, len(anchor_entities) * 2)):
            primary = anchor_entities[i % len(anchor_entities)]
            related_1 = anchor_entities[(i + 1) % len(anchor_entities)]
            related_2 = anchor_entities[(i + 2) % len(anchor_entities)]
            template = ANCHOR_TEMPLATES[i % len(ANCHOR_TEMPLATES)]

            text = template.format(
                entity=primary,
                related_1=related_1,
                related_2=related_2,
            )

            payloads.append(InjectionPayload(
                payload_id=f"a2_{uuid.uuid4().hex[:8]}",
                text=text,
                entities=[primary, related_1, related_2],
                target_queries=target_queries[:5],
                metadata={
                    "attack": self.name,
                    "target_area": self.target_area,
                    "primary_entity": primary,
                    "sensitivity": "PUBLIC",
                    "tenant": self.attacker_tenant,
                    "provenance_score": 0.4,
                },
            ))

        return payloads

    def inject(
        self,
        payloads: list[InjectionPayload],
        vector_index,
        graph_builder,
    ) -> AttackResult:
        """Inject entity-anchor payloads into vector store and graph.

        Chunks go into ChromaDB. When the NER pipeline processes them,
        it will create MENTIONS edges to the anchor entities in the graph.
        We also directly create the entity nodes if they don't exist.
        """
        from pivorag.graph.schema import GraphEdge, GraphNode
        from pivorag.vector.embed import EmbeddingModel

        model = EmbeddingModel()
        total_tokens = 0

        # Insert into vector store
        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for payload in payloads:
            chunk_id = f"injected_{payload.payload_id}"
            embedding = model.embed(payload.text).tolist()

            ids.append(chunk_id)
            embeddings.append(embedding)
            documents.append(payload.text)
            metadatas.append({
                "doc_id": f"injected_doc_{payload.payload_id}",
                "tenant": self.attacker_tenant,
                "sensitivity": "PUBLIC",
                "domain": "engineering",
                "doc_type": "injected_anchor",
                "trust_score": 0.4,
                "provenance_score": 0.4,
            })
            total_tokens += len(payload.text.split())

        vector_index.add_chunks(ids, embeddings, documents, metadatas)

        # Create entity nodes and MENTIONS edges in graph
        for payload in payloads:
            chunk_id = f"injected_{payload.payload_id}"

            # Create chunk node
            graph_builder.add_node(GraphNode(
                node_id=chunk_id,
                node_type="Chunk",
                tenant=self.attacker_tenant,
                sensitivity="PUBLIC",
                provenance_score=0.4,
            ))

            # Create MENTIONS edges to each entity
            for entity_name in payload.entities:
                canonical = entity_name.strip().lower().replace(" ", "_")
                entity_id = f"ent_{canonical}_ANCHOR"

                graph_builder.add_node(GraphNode(
                    node_id=entity_id,
                    node_type="Entity",
                    properties={
                        "canonical_name": canonical,
                        "text": entity_name,
                    },
                ))

                graph_builder.add_edge(GraphEdge(
                    source_id=chunk_id,
                    target_id=entity_id,
                    edge_type="MENTIONS",
                    trust_score=0.4,
                ))

        return AttackResult(
            attack_name=self.name,
            payloads_injected=len(payloads),
            total_tokens_injected=total_tokens,
            target_queries=[q for p in payloads for q in p.target_queries],
            metadata={
                "target_area": self.target_area,
                "anchor_entities": list({e for p in payloads for e in p.entities}),
            },
        )
