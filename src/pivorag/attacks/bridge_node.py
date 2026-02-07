"""A4: Bridge Node Attack.

Creates connector entities that plausibly relate to both benign and
sensitive subgraphs. These artificial "bridges" create short paths
between public and restricted regions, enabling traversal pivots.
"""

from __future__ import annotations

from typing import Any

from pivorag.attacks.base import AttackResult, BaseAttack, InjectionPayload


class BridgeNodeAttack(BaseAttack):
    """A4: Create cross-boundary bridge entities."""

    @property
    def name(self) -> str:
        return "A4_bridge_node"

    def generate_payloads(
        self,
        target_queries: list[str],
        corpus_stats: dict[str, Any] | None = None,
    ) -> list[InjectionPayload]:
        """Generate bridge entity payloads.

        Strategy: Create entities with names/types that plausibly relate
        to both benign and sensitive subgraphs. Examples:
        - Shared vendor names (connects finance ↔ engineering)
        - Reused abbreviations (connects public docs ↔ restricted systems)
        - Shared project tags (connects HR ↔ security)
        """
        raise NotImplementedError(
            "Implement bridge entity generation. Identify pairs of "
            "(benign_subgraph, sensitive_subgraph) and create entities "
            "that connect them with plausible relationship types."
        )

    def inject(
        self,
        payloads: list[InjectionPayload],
        vector_index,
        graph_builder,
    ) -> AttackResult:
        """Inject bridge nodes and their connecting edges."""
        raise NotImplementedError(
            "Create bridge entities in the graph with edges to both "
            "benign and sensitive neighborhoods."
        )
