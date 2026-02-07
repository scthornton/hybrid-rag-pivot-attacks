"""D4: Provenance/Trust-Weighted Expansion.

Maintains a trust score for nodes/edges based on provenance.
Low-trust sources are downweighted or excluded during expansion.
Effective against GRAGPoison-style attacks that inject through
low-quality documents.
"""

from __future__ import annotations

from pivorag.graph.schema import GraphNode


class TrustWeightingDefense:
    """Filter and weight graph expansion by provenance trust scores."""

    def __init__(
        self,
        min_trust_score: float = 0.6,
        trust_decay_per_hop: float = 0.15,
        low_trust_sources: list[str] | None = None,
    ) -> None:
        self.min_trust_score = min_trust_score
        self.trust_decay_per_hop = trust_decay_per_hop
        self.low_trust_sources = low_trust_sources or []

    def filter_by_trust(self, nodes: list[GraphNode]) -> list[GraphNode]:
        """Remove nodes below the minimum trust threshold."""
        return [n for n in nodes if n.provenance_score >= self.min_trust_score]

    def compute_path_trust(
        self,
        trust_scores: list[float],
    ) -> float:
        """Compute cumulative trust along a traversal path.

        Trust decays multiplicatively along the path:
        path_trust = product(scores) * decay^(hops-1)
        """
        if not trust_scores:
            return 0.0
        product = 1.0
        for score in trust_scores:
            product *= score
        hops = len(trust_scores) - 1
        decay = (1.0 - self.trust_decay_per_hop) ** hops
        return product * decay

    def score_node(
        self,
        node: GraphNode,
        relevance: float,
        sensitivity_penalty: float = 0.0,
        alpha: float = 0.5,
        beta: float = 0.3,
        gamma: float = 0.2,
    ) -> float:
        """Compute trust-adjusted retrieval score for a node.

        score = alpha * relevance + beta * trust - gamma * sensitivity
        """
        return (
            alpha * relevance
            + beta * node.provenance_score
            - gamma * sensitivity_penalty
        )
