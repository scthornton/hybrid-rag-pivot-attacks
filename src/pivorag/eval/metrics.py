"""Core security metrics for retrieval pivot risk evaluation.

Implements the four novel metrics from the research plan:
- RPR: Retrieval Pivot Risk
- Leakage@k: Sensitive item count in top-k
- AF: Amplification Factor (hybrid vs vector-only)
- PD: Pivot Depth (min hops to first sensitive node)
"""

from __future__ import annotations

from dataclasses import dataclass

from pivorag.config import SensitivityTier
from pivorag.pipelines.base import RetrievalContext


def leakage_at_k(
    context: RetrievalContext,
    k: int | None = None,
) -> int:
    """Count sensitive items in the final top-k context set.

    Leakage@k(q) = |{x in S_k(q) : Sensitive(x)}|

    A sensitive item is anything with sensitivity > user's clearance,
    or anything the user's tenant policy doesn't authorize.
    """
    all_items = context.chunks + context.graph_nodes
    if k is not None:
        all_items = all_items[:k]

    count = 0
    for item in all_items:
        item_tier = SensitivityTier(item.get("sensitivity", "PUBLIC"))
        is_over_clearance = item_tier > context.user_clearance
        is_wrong_tenant = item.get("tenant") and item["tenant"] != context.user_tenant
        if is_over_clearance or is_wrong_tenant:
            count += 1
    return count


def retrieval_pivot_risk(
    contexts: list[RetrievalContext],
) -> float:
    """Compute RPR: probability that any query's context contains unauthorized items.

    RPR = Pr[Z(q,u) ∩ U_u ≠ ∅]
    """
    if not contexts:
        return 0.0
    violations = sum(1 for ctx in contexts if leakage_at_k(ctx) > 0)
    return violations / len(contexts)


def amplification_factor(
    hybrid_contexts: list[RetrievalContext],
    vector_contexts: list[RetrievalContext],
    k: int | None = None,
) -> float:
    """Compute AF: ratio of hybrid leakage to vector-only leakage.

    AF = E[Leakage@k]_hybrid / E[Leakage@k]_vector

    AF >> 1 means hybrid RAG significantly amplifies retrieval risk.
    """
    if not hybrid_contexts or not vector_contexts:
        return 0.0

    hybrid_leakage = sum(leakage_at_k(ctx, k) for ctx in hybrid_contexts) / len(hybrid_contexts)
    vector_leakage = sum(leakage_at_k(ctx, k) for ctx in vector_contexts) / len(vector_contexts)

    if vector_leakage == 0:
        return float("inf") if hybrid_leakage > 0 else 1.0
    return hybrid_leakage / vector_leakage


def pivot_depth(context: RetrievalContext) -> int | float:
    """Compute PD: minimum graph hop distance from seed to first sensitive node.

    PD(q) = min{d(seed, x) : x in S(q) ∧ Sensitive(x)}
    Returns inf if no sensitive nodes found.

    Note: Requires traversal path data in context.traversal_log.
    This is a simplified version using available metadata.
    """
    # Check if any graph nodes are sensitive (unauthorized)
    for node in context.graph_nodes:
        node_tier = SensitivityTier(node.get("sensitivity", "PUBLIC"))
        if node_tier > context.user_clearance:
            # Found a sensitive node — estimate depth from traversal log
            # Full implementation would track per-node hop distance
            return 1  # Placeholder: assume 1 hop for now
    return float("inf")


@dataclass
class SecurityMetrics:
    """Aggregated security metrics for a pipeline evaluation run."""

    rpr: float
    mean_leakage: float
    amplification_factor: float
    mean_pivot_depth: float
    total_queries: int
    queries_with_leakage: int

    def to_dict(self) -> dict:
        return {
            "rpr": self.rpr,
            "mean_leakage": self.mean_leakage,
            "amplification_factor": self.amplification_factor,
            "mean_pivot_depth": self.mean_pivot_depth,
            "total_queries": self.total_queries,
            "queries_with_leakage": self.queries_with_leakage,
        }
