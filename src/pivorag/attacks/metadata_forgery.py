"""A5: Targeted Metadata Forgery.

Attacker relabels injected nodes with the *target* tenant's name to
bypass D1's per-hop tenant check.  Two sub-variants:

- Random forgery: attacker picks victim tenant uniformly at random.
- Targeted forgery: attacker sets metadata to the specific tenant
  they want to read from.

D1 alone fails under this attack because the forged tenant label
passes the `tenant in allowed_tenants` check.  D4 (trust weighting)
catches forgery because injected documents have low provenance scores.

Attack surface: graph metadata (tenant labels on nodes)
Threat model: attacker can inject documents with arbitrary metadata
Defense coverage: D1 FAILS, D4 mitigates
"""

from __future__ import annotations

import uuid
from typing import Any

from pivorag.attacks.base import AttackResult, BaseAttack, InjectionPayload

# Sensitive content areas the attacker wants to access
FORGERY_TARGETS = {
    "security_secrets": {
        "target_tenant": "umbrella_security",
        "forged_sensitivity": "INTERNAL",
        "topic_entities": [
            "credential-vault", "auth-service", "splunk-siem",
            "pentest-q3-2025", "incident-findings",
        ],
        "sensitive_nodes": [
            "admin_credentials", "api_secrets", "vulnerability_details",
        ],
    },
    "hr_records": {
        "target_tenant": "initech_hr",
        "forged_sensitivity": "INTERNAL",
        "topic_entities": [
            "Maria Chen", "James Rodriguez", "Aisha Patel",
            "Project Nexus", "hiring pipeline",
        ],
        "sensitive_nodes": [
            "salary_data", "compensation_packages", "performance_reviews",
        ],
    },
    "financial_data": {
        "target_tenant": "globex_finance",
        "forged_sensitivity": "INTERNAL",
        "topic_entities": [
            "CloudCorp", "DataSync Inc", "SecureNet LLC",
            "SOC 2 audit", "budget-q4-2025",
        ],
        "sensitive_nodes": [
            "contract_values", "merger_plans", "vendor_pricing",
        ],
    },
}

# Templates with benign-sounding text that mimics internal documents
FORGERY_TEMPLATES = [
    (
        "Internal memo: {entity_1} status and {entity_2} update. "
        "As of this quarter, {entity_1} has completed all scheduled "
        "maintenance windows. {entity_2} integration is on track. "
        "Next review scheduled for end of month. Contact {entity_1} "
        "team lead for detailed status reports."
    ),
    (
        "Weekly standup notes for {entity_1} and {entity_2}. "
        "The {entity_1} deployment went smoothly last Tuesday. "
        "{entity_2} received a minor patch for a non-critical issue. "
        "Both {entity_1} and {entity_2} are green in the status dashboard. "
        "No blockers reported this week."
    ),
    (
        "Quarterly review: {entity_1} performance metrics. "
        "{entity_1} processed 2.3 million transactions this quarter. "
        "Uptime: 99.98%. {entity_2} handled the overflow during the "
        "peak period without degradation. {entity_1} and {entity_2} "
        "are scheduled for capacity upgrades next quarter."
    ),
]


class MetadataForgeryAttack(BaseAttack):
    """A5: Bypass D1 by forging tenant metadata on injected documents.

    Strategy:
    1. Craft benign-looking documents that mention target-area entities
    2. Label them with the TARGET tenant (not the attacker's real tenant)
    3. D1's `tenant in allowed_tenants` check passes for the forged label
    4. Graph expansion returns these nodes as if they were legitimate
    5. D4 catches this because provenance_score is low for injected docs
    """

    def __init__(
        self,
        injection_budget: int = 10,
        target_area: str = "security_secrets",
        attacker_tenant: str = "acme_engineering",
        forgery_rate: float = 1.0,
    ) -> None:
        super().__init__(injection_budget)
        self.target_area = target_area
        self.attacker_tenant = attacker_tenant
        self.forgery_rate = min(1.0, max(0.0, forgery_rate))

    @property
    def name(self) -> str:
        return "A5_metadata_forgery"

    def generate_payloads(
        self,
        target_queries: list[str],
        corpus_stats: dict[str, Any] | None = None,
    ) -> list[InjectionPayload]:
        """Generate payloads with forged tenant metadata.

        Each payload is labeled with the target tenant instead of the
        attacker's real tenant, so D1 cannot distinguish it from
        legitimate content.
        """
        config = FORGERY_TARGETS.get(
            self.target_area,
            FORGERY_TARGETS["security_secrets"],
        )
        target_tenant = config["target_tenant"]
        entities = config["topic_entities"]

        payloads = []
        for i in range(self.injection_budget):
            ent_1 = entities[i % len(entities)]
            ent_2 = entities[(i + 1) % len(entities)]
            template = FORGERY_TEMPLATES[i % len(FORGERY_TEMPLATES)]

            text = template.format(entity_1=ent_1, entity_2=ent_2)

            # Determine if this payload gets forged metadata
            forged = (i / max(self.injection_budget, 1)) < self.forgery_rate
            assigned_tenant = target_tenant if forged else self.attacker_tenant

            payloads.append(InjectionPayload(
                payload_id=f"a5_{uuid.uuid4().hex[:8]}",
                text=text,
                entities=[ent_1, ent_2],
                target_queries=target_queries[:5],
                metadata={
                    "attack": self.name,
                    "target_area": self.target_area,
                    "real_tenant": self.attacker_tenant,
                    "forged_tenant": assigned_tenant,
                    "is_forged": forged,
                    "sensitivity": config["forged_sensitivity"],
                    "tenant": assigned_tenant,
                    "provenance_score": 0.2,
                    "forgery_rate": self.forgery_rate,
                },
            ))

        return payloads

    def inject(
        self,
        payloads: list[InjectionPayload],
        vector_index,
        graph_builder,
    ) -> AttackResult:
        """Inject payloads with forged tenant labels.

        The key difference from A1-A4: the tenant field is set to the
        TARGET tenant, not the attacker's real tenant.  D1 sees these
        nodes as belonging to the target and allows them through.
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
                "tenant": payload.metadata["forged_tenant"],
                "sensitivity": payload.metadata["sensitivity"],
                "domain": "internal",
                "doc_type": "injected_forgery",
                "trust_score": 0.2,
                "provenance_score": 0.2,
            })
            total_tokens += len(payload.text.split())

        vector_index.add_chunks(ids, embeddings, documents, metadatas)

        # Build graph with forged tenant labels
        for payload in payloads:
            chunk_id = f"injected_{payload.payload_id}"

            graph_builder.add_node(GraphNode(
                node_id=chunk_id,
                node_type="Chunk",
                tenant=payload.metadata["forged_tenant"],
                sensitivity=payload.metadata["sensitivity"],
                provenance_score=0.2,
            ))

            for entity_name in payload.entities:
                canonical = entity_name.strip().lower().replace(" ", "_")
                entity_id = f"ent_{canonical}_FORGE"

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
                    trust_score=0.2,
                ))

        forged_count = sum(1 for p in payloads if p.metadata["is_forged"])
        return AttackResult(
            attack_name=self.name,
            payloads_injected=len(payloads),
            total_tokens_injected=total_tokens,
            target_queries=[q for p in payloads for q in p.target_queries],
            metadata={
                "target_area": self.target_area,
                "forgery_rate": self.forgery_rate,
                "forged_count": forged_count,
                "honest_count": len(payloads) - forged_count,
                "target_tenant": FORGERY_TARGETS.get(
                    self.target_area, FORGERY_TARGETS["security_secrets"],
                )["target_tenant"],
            },
        )
