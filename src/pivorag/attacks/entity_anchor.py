"""A2: Entity Anchor Injection.

Injected chunks heavily mention high-value entities to force entity
linking into sensitive graph neighborhoods. The chunk text is designed
to trigger NER extraction of specific entity names that sit on the
boundary of sensitive subgraphs.
"""

from __future__ import annotations

from typing import Any

from pivorag.attacks.base import AttackResult, BaseAttack, InjectionPayload


class EntityAnchorAttack(BaseAttack):
    """A2: Force entity linking to sensitive graph neighborhoods."""

    @property
    def name(self) -> str:
        return "A2_entity_anchor"

    def generate_payloads(
        self,
        target_queries: list[str],
        corpus_stats: dict[str, Any] | None = None,
    ) -> list[InjectionPayload]:
        """Generate chunks densely mentioning target entities.

        Strategy: Identify high-value entity names (systems, code names,
        project names) that are 1-2 hops from sensitive nodes, then craft
        natural-sounding text that mentions them frequently.
        """
        raise NotImplementedError(
            "Implement entity-dense payload generation targeting "
            "border entities adjacent to sensitive subgraphs."
        )

    def inject(
        self,
        payloads: list[InjectionPayload],
        vector_index,
        graph_builder,
    ) -> AttackResult:
        """Inject entity-anchor payloads into vector store and graph."""
        raise NotImplementedError(
            "Inject chunks + create entity nodes in graph via extraction."
        )
