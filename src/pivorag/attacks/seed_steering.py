"""A1: Vector Seed Steering (Centroid Poisoning).

Crafts injected chunks that are semantically close to many target
queries. Goal: appear in vector top-k frequently to serve as pivot
seeds for graph expansion into sensitive neighborhoods.
"""

from __future__ import annotations

from typing import Any

from pivorag.attacks.base import AttackResult, BaseAttack, InjectionPayload


class SeedSteeringAttack(BaseAttack):
    """A1: Craft broad-spectrum chunks to maximize vector retrieval frequency."""

    @property
    def name(self) -> str:
        return "A1_seed_steering"

    def generate_payloads(
        self,
        target_queries: list[str],
        corpus_stats: dict[str, Any] | None = None,
    ) -> list[InjectionPayload]:
        """Generate chunks with high semantic overlap to target query families.

        Strategy: Combine common enterprise terms with entity names that
        are graphically adjacent to sensitive subgraphs.
        """
        raise NotImplementedError(
            "Implement centroid-based payload generation. "
            "Use embedding model to find centroid of target queries, "
            "then generate text near that centroid."
        )

    def inject(
        self,
        payloads: list[InjectionPayload],
        vector_index,
        graph_builder,
    ) -> AttackResult:
        """Inject seed-steering payloads into the vector store."""
        raise NotImplementedError(
            "Inject payloads as chunks into ChromaDB with benign metadata."
        )
