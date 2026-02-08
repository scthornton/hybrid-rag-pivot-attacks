"""Core security metrics for retrieval pivot risk evaluation.

Implements the four novel metrics from the research plan:
- RPR: Retrieval Pivot Risk
- Leakage@k: Sensitive item count in top-k
- AF: Amplification Factor (hybrid vs vector-only)
- PD: Pivot Depth (min hops to first sensitive node)

Extended metrics for reviewer response:
- Severity-weighted leakage: weights by tier distance
- AF(ε): finite amplification factor with epsilon floor
- ΔLeakage: absolute leakage difference
- PD distribution: (min, median, max) pivot depth
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

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

    Reads per-node hop_depth from graph_nodes (populated by
    GraphExpander.bfs_expand via apoc.path.spanningTree).
    """
    min_depth = float("inf")
    for node in context.graph_nodes:
        node_tier = SensitivityTier(node.get("sensitivity", "PUBLIC"))
        is_over_clearance = node_tier > context.user_clearance
        is_wrong_tenant = node.get("tenant") and node["tenant"] != context.user_tenant
        if is_over_clearance or is_wrong_tenant:
            hop = node.get("hop_depth", -1)
            min_depth = min(min_depth, hop) if hop >= 0 else min(min_depth, 1)
    return min_depth


def severity_weighted_leakage(
    context: RetrievalContext,
    k: int | None = None,
) -> float:
    """Compute severity-weighted leakage: sum of tier distances for leaked items.

    Weight = leaked_tier.level - user_clearance.level for over-clearance items,
    plus 1 for each cross-tenant violation. Higher values indicate more severe
    leakage (e.g., RESTRICTED data reaching PUBLIC user = weight 3).
    """
    all_items = context.chunks + context.graph_nodes
    if k is not None:
        all_items = all_items[:k]

    total_weight = 0.0
    for item in all_items:
        item_tier = SensitivityTier(item.get("sensitivity", "PUBLIC"))
        is_over_clearance = item_tier > context.user_clearance
        is_wrong_tenant = item.get("tenant") and item["tenant"] != context.user_tenant

        if is_over_clearance:
            total_weight += item_tier.level - context.user_clearance.level
        elif is_wrong_tenant:
            total_weight += 1.0
    return total_weight


def amplification_factor_epsilon(
    hybrid_contexts: list[RetrievalContext],
    vector_contexts: list[RetrievalContext],
    epsilon: float = 0.1,
    k: int | None = None,
) -> float:
    """Compute AF(ε): finite amplification factor with epsilon floor.

    AF(ε) = E[Leakage@k]_hybrid / max(E[Leakage@k]_vector, ε)

    Avoids division-by-zero when vector baseline leaks nothing,
    producing a finite, plottable value.
    """
    if not hybrid_contexts or not vector_contexts:
        return 0.0

    hybrid_leakage = sum(leakage_at_k(ctx, k) for ctx in hybrid_contexts) / len(hybrid_contexts)
    vector_leakage = sum(leakage_at_k(ctx, k) for ctx in vector_contexts) / len(vector_contexts)

    return hybrid_leakage / max(vector_leakage, epsilon)


def delta_leakage(
    hybrid_contexts: list[RetrievalContext],
    vector_contexts: list[RetrievalContext],
    k: int | None = None,
) -> float:
    """Compute ΔLeakage: absolute difference in mean leakage.

    ΔLeakage = E[Leakage@k]_hybrid - E[Leakage@k]_vector

    Complementary to AF — shows absolute magnitude rather than ratio.
    """
    if not hybrid_contexts or not vector_contexts:
        return 0.0

    hybrid_leakage = sum(leakage_at_k(ctx, k) for ctx in hybrid_contexts) / len(hybrid_contexts)
    vector_leakage = sum(leakage_at_k(ctx, k) for ctx in vector_contexts) / len(vector_contexts)

    return hybrid_leakage - vector_leakage


def pivot_depth_distribution(
    contexts: list[RetrievalContext],
) -> dict[str, float]:
    """Compute PD distribution: min, median, max across queries with leakage.

    Only includes queries where leakage occurred (PD != inf).
    Returns {"min": ..., "median": ..., "max": ...} or all inf if no leakage.
    """
    depths = []
    for ctx in contexts:
        pd = pivot_depth(ctx)
        if pd != float("inf"):
            depths.append(pd)

    if not depths:
        return {"min": float("inf"), "median": float("inf"), "max": float("inf")}

    return {
        "min": min(depths),
        "median": statistics.median(depths),
        "max": max(depths),
    }


@dataclass
class SecurityMetrics:
    """Aggregated security metrics for a pipeline evaluation run."""

    rpr: float
    mean_leakage: float
    amplification_factor: float
    mean_pivot_depth: float
    total_queries: int
    queries_with_leakage: int
    # Extended metrics (reviewer response)
    mean_severity_weighted_leakage: float = 0.0
    af_epsilon: float = 0.0
    delta_leak: float = 0.0
    pd_distribution: dict[str, float] = field(default_factory=lambda: {
        "min": float("inf"), "median": float("inf"), "max": float("inf"),
    })
    rpr_ci: tuple[float, float, float] | None = None  # (mean, ci_low, ci_high)
    leakage_ci: tuple[float, float, float] | None = None

    def to_dict(self) -> dict:
        result = {
            "rpr": self.rpr,
            "mean_leakage": self.mean_leakage,
            "amplification_factor": self.amplification_factor,
            "mean_pivot_depth": self.mean_pivot_depth,
            "total_queries": self.total_queries,
            "queries_with_leakage": self.queries_with_leakage,
            "mean_severity_weighted_leakage": self.mean_severity_weighted_leakage,
            "af_epsilon": self.af_epsilon,
            "delta_leakage": self.delta_leak,
            "pd_distribution": self.pd_distribution,
        }
        if self.rpr_ci is not None:
            result["rpr_ci"] = list(self.rpr_ci)
        if self.leakage_ci is not None:
            result["leakage_ci"] = list(self.leakage_ci)
        return result
