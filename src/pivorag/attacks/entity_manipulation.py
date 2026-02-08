"""A6: Entity Manipulation Attack.

Attacker creates documents that mention entities from the target tenant's
namespace.  When spaCy NER processes these documents, it extracts the
same canonical entity names, causing the entity linker to merge them
with existing nodes in the target's subgraph.

This creates shared entity nodes where none should exist, enabling
the chunk→entity→chunk pivot path even without natural bridges.

Attack surface: entity linking / deduplication
Threat model: attacker knows entity names from target tenant (e.g.,
              from public org charts, press releases, LinkedIn)
Defense coverage: D1 blocks (entity tenant=""), D2 (edge allowlist)
                  provides additional protection
"""

from __future__ import annotations

import uuid
from typing import Any

from pivorag.attacks.base import AttackResult, BaseAttack, InjectionPayload

# Target entity names from each tenant's namespace.
# In practice, these would be discovered through OSINT
# (org charts, press releases, LinkedIn profiles, product pages).
TARGET_ENTITY_NAMES = {
    "security_personnel": {
        "target_tenant": "umbrella_security",
        "entity_names": [
            "Sarah Kim", "David Park", "Lisa Thompson",
            "Security Operations Center", "Vulnerability Assessment",
        ],
        "context_topics": [
            "cybersecurity conference presentation",
            "industry panel discussion",
            "published security research",
            "open-source security tool contribution",
            "professional development workshop",
        ],
    },
    "hr_personnel": {
        "target_tenant": "initech_hr",
        "entity_names": [
            "Maria Chen", "James Rodriguez", "Aisha Patel",
            "Employee Relations", "Talent Acquisition",
        ],
        "context_topics": [
            "HR industry conference",
            "professional networking event",
            "published HR best practices article",
            "workplace culture webinar",
            "diversity and inclusion panel",
        ],
    },
    "finance_vendors": {
        "target_tenant": "globex_finance",
        "entity_names": [
            "CloudCorp", "DataSync Inc", "SecureNet LLC",
            "Financial Planning", "Risk Assessment",
        ],
        "context_topics": [
            "industry trade show",
            "partnership announcement",
            "market analysis report",
            "technology integration review",
            "quarterly business update",
        ],
    },
}

# Templates that naturally mention target entities in plausible contexts.
# The attacker needs NER to extract these names and link them to existing
# entity nodes in the graph.
MANIPULATION_TEMPLATES = [
    (
        "At the recent {topic}, {entity_1} and {entity_2} were featured "
        "prominently. {entity_1} presented on emerging trends while "
        "{entity_2} led a hands-on workshop. Both {entity_1} and "
        "{entity_2} received positive feedback from attendees. "
        "Follow-up sessions are planned for next quarter."
    ),
    (
        "Industry report mentions {entity_1} alongside {entity_2} as "
        "leading examples in the field. According to the analysis, "
        "{entity_1} has shown consistent growth in capabilities. "
        "{entity_2} complements {entity_1} with specialized expertise. "
        "Together they represent a comprehensive approach."
    ),
    (
        "Public records indicate {entity_1} participated in a joint "
        "initiative with {entity_2}. The collaboration between "
        "{entity_1} and {entity_2} focused on shared standards. "
        "Both {entity_1} and {entity_2} contributed their domain "
        "knowledge to the final deliverable."
    ),
]


class EntityManipulationAttack(BaseAttack):
    """A6: Force entity linker to create shared nodes with target tenant.

    Strategy:
    1. Discover entity names from the target tenant (OSINT/public info)
    2. Craft benign documents that heavily mention those names
    3. NER extracts the same canonical names → linker merges with existing
    4. Now there are chunk→entity→chunk paths from attacker to target
    5. D1 blocks because entity nodes have tenant="" (not in allowed_tenants)
    """

    def __init__(
        self,
        injection_budget: int = 10,
        target_namespace: str = "security_personnel",
        attacker_tenant: str = "acme_engineering",
    ) -> None:
        super().__init__(injection_budget)
        self.target_namespace = target_namespace
        self.attacker_tenant = attacker_tenant

    @property
    def name(self) -> str:
        return "A6_entity_manipulation"

    def generate_payloads(
        self,
        target_queries: list[str],
        corpus_stats: dict[str, Any] | None = None,
    ) -> list[InjectionPayload]:
        """Generate documents mentioning entities from the target namespace.

        Each payload mentions 2 target entities in a plausible public
        context.  When NER processes these, the extracted canonical names
        match existing entity nodes in the target's subgraph.
        """
        config = TARGET_ENTITY_NAMES.get(
            self.target_namespace,
            TARGET_ENTITY_NAMES["security_personnel"],
        )
        entity_names = config["entity_names"]
        topics = config["context_topics"]

        payloads = []
        for i in range(self.injection_budget):
            ent_1 = entity_names[i % len(entity_names)]
            ent_2 = entity_names[(i + 1) % len(entity_names)]
            topic = topics[i % len(topics)]
            template = MANIPULATION_TEMPLATES[i % len(MANIPULATION_TEMPLATES)]

            text = template.format(
                entity_1=ent_1, entity_2=ent_2, topic=topic,
            )

            payloads.append(InjectionPayload(
                payload_id=f"a6_{uuid.uuid4().hex[:8]}",
                text=text,
                entities=[ent_1, ent_2],
                target_queries=target_queries[:5],
                metadata={
                    "attack": self.name,
                    "target_namespace": self.target_namespace,
                    "target_tenant": config["target_tenant"],
                    "manipulated_entities": [ent_1, ent_2],
                    "sensitivity": "PUBLIC",
                    "tenant": self.attacker_tenant,
                    "provenance_score": 0.5,
                },
            ))

        return payloads

    def inject(
        self,
        payloads: list[InjectionPayload],
        vector_index,
        graph_builder,
    ) -> AttackResult:
        """Inject payloads and create entity nodes that collide with target.

        The injected chunks belong to the attacker's tenant, but the
        entity nodes they create share canonical names with the target's
        entity nodes.  This creates the pivot path:
        attacker_chunk → shared_entity → target_chunk.
        """
        from pivorag.graph.schema import GraphEdge, GraphNode
        from pivorag.vector.embed import EmbeddingModel

        model = EmbeddingModel()
        total_tokens = 0

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
                "domain": "public",
                "doc_type": "injected_entity_manipulation",
                "trust_score": 0.5,
                "provenance_score": 0.5,
            })
            total_tokens += len(payload.text.split())

        vector_index.add_chunks(ids, embeddings, documents, metadatas)

        manipulated_entities: set[str] = set()
        for payload in payloads:
            chunk_id = f"injected_{payload.payload_id}"

            graph_builder.add_node(GraphNode(
                node_id=chunk_id,
                node_type="Chunk",
                tenant=self.attacker_tenant,
                sensitivity="PUBLIC",
                provenance_score=0.5,
            ))

            for entity_name in payload.entities:
                canonical = entity_name.strip().lower().replace(" ", "_")
                # Use the SAME naming scheme as legitimate entity nodes
                # so the linker deduplicates them into shared nodes
                entity_id = f"ent_{canonical}"

                graph_builder.add_node(GraphNode(
                    node_id=entity_id,
                    node_type="Entity",
                    # Entity nodes are tenant-neutral (tenant="")
                    # This is what D1 checks — empty tenant is not in
                    # any allowed_tenants set
                    properties={
                        "canonical_name": canonical,
                        "text": entity_name,
                    },
                ))

                graph_builder.add_edge(GraphEdge(
                    source_id=chunk_id,
                    target_id=entity_id,
                    edge_type="MENTIONS",
                    trust_score=0.5,
                ))
                manipulated_entities.add(canonical)

        return AttackResult(
            attack_name=self.name,
            payloads_injected=len(payloads),
            total_tokens_injected=total_tokens,
            target_queries=[q for p in payloads for q in p.target_queries],
            metadata={
                "target_namespace": self.target_namespace,
                "target_tenant": TARGET_ENTITY_NAMES.get(
                    self.target_namespace,
                    TARGET_ENTITY_NAMES["security_personnel"],
                )["target_tenant"],
                "manipulated_entity_count": len(manipulated_entities),
                "manipulated_entities": sorted(manipulated_entities),
            },
        )
