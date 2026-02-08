"""Tests for security and utility metrics."""

from pivorag.config import SensitivityTier
from pivorag.eval.benchmark import bootstrap_ci
from pivorag.eval.metrics import (
    amplification_factor,
    amplification_factor_epsilon,
    delta_leakage,
    leakage_at_k,
    pivot_depth,
    pivot_depth_distribution,
    retrieval_pivot_risk,
    severity_weighted_leakage,
)
from pivorag.eval.utility import context_precision_at_k, context_recall_at_k
from pivorag.pipelines.base import RetrievalContext


def _make_context(
    chunks: list[dict] | None = None,
    graph_nodes: list[dict] | None = None,
    clearance: str = "INTERNAL",
    tenant: str = "acme_engineering",
) -> RetrievalContext:
    return RetrievalContext(
        query="test",
        user_id="u1",
        user_tenant=tenant,
        user_clearance=SensitivityTier(clearance),
        chunks=chunks or [],
        graph_nodes=graph_nodes or [],
    )


class TestLeakageAtK:
    def test_no_leakage(self):
        ctx = _make_context(
            chunks=[{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}],
        )
        assert leakage_at_k(ctx) == 0

    def test_detects_sensitivity_leakage(self):
        ctx = _make_context(
            graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "acme_engineering"}],
        )
        assert leakage_at_k(ctx) == 1

    def test_detects_cross_tenant_leakage(self):
        ctx = _make_context(
            graph_nodes=[{"sensitivity": "PUBLIC", "tenant": "umbrella_security"}],
        )
        assert leakage_at_k(ctx) == 1

    def test_empty_tenant_entity_not_counted_as_leakage(self):
        """Entity nodes with tenant='' are excluded from cross-tenant leakage.

        This documents a design decision: entity nodes are tenant-neutral
        shared concepts. They don't "leak" data themselves — they are bridge
        nodes through which leakage flows to chunk nodes (which DO have
        tenants and ARE counted). D1 prevents traversal through them.
        """
        ctx = _make_context(
            graph_nodes=[
                {"sensitivity": "PUBLIC", "tenant": ""},  # Entity — not leakage
            ],
        )
        assert leakage_at_k(ctx) == 0

    def test_cross_tenant_chunk_counted_as_leakage(self):
        """Chunk nodes with a different non-empty tenant ARE leakage."""
        ctx = _make_context(
            graph_nodes=[
                {"sensitivity": "PUBLIC", "tenant": "globex_finance"},
            ],
        )
        assert leakage_at_k(ctx) == 1


class TestRPR:
    def test_zero_rpr(self):
        contexts = [
            _make_context(chunks=[{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}])
            for _ in range(10)
        ]
        assert retrieval_pivot_risk(contexts) == 0.0

    def test_full_rpr(self):
        contexts = [
            _make_context(graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "x"}])
            for _ in range(10)
        ]
        assert retrieval_pivot_risk(contexts) == 1.0

    def test_partial_rpr(self):
        contexts = [
            _make_context(chunks=[{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}])
            for _ in range(5)
        ] + [
            _make_context(graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "x"}])
            for _ in range(5)
        ]
        assert retrieval_pivot_risk(contexts) == 0.5


class TestAmplificationFactor:
    def test_amplification_detected(self):
        hybrid = [
            _make_context(graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "x"}])
            for _ in range(10)
        ]
        vector = [
            _make_context(chunks=[{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}])
            for _ in range(10)
        ]
        af = amplification_factor(hybrid, vector)
        assert af == float("inf")  # Vector has 0 leakage

    def test_no_amplification(self):
        both = [
            _make_context(chunks=[{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}])
            for _ in range(10)
        ]
        af = amplification_factor(both, both)
        assert af == 1.0


class TestSeverityWeightedLeakage:
    def test_no_leakage_zero_weight(self):
        ctx = _make_context(
            chunks=[{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}],
        )
        assert severity_weighted_leakage(ctx) == 0.0

    def test_confidential_to_internal_user(self):
        # INTERNAL user (level 1) sees CONFIDENTIAL (level 2) → weight = 1
        ctx = _make_context(
            graph_nodes=[{"sensitivity": "CONFIDENTIAL", "tenant": "acme_engineering"}],
            clearance="INTERNAL",
        )
        assert severity_weighted_leakage(ctx) == 1.0

    def test_restricted_to_internal_user(self):
        # INTERNAL user (level 1) sees RESTRICTED (level 3) → weight = 2
        ctx = _make_context(
            graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "acme_engineering"}],
            clearance="INTERNAL",
        )
        assert severity_weighted_leakage(ctx) == 2.0

    def test_restricted_to_public_user(self):
        # PUBLIC user (level 0) sees RESTRICTED (level 3) → weight = 3
        ctx = _make_context(
            graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "acme_engineering"}],
            clearance="PUBLIC",
        )
        assert severity_weighted_leakage(ctx) == 3.0

    def test_cross_tenant_adds_weight_one(self):
        # Cross-tenant item that is NOT over-clearance → weight = 1
        ctx = _make_context(
            graph_nodes=[{"sensitivity": "PUBLIC", "tenant": "umbrella_security"}],
            clearance="INTERNAL",
        )
        assert severity_weighted_leakage(ctx) == 1.0

    def test_multiple_items_cumulative(self):
        # Two items: CONFIDENTIAL (weight 1) + RESTRICTED (weight 2) = 3
        ctx = _make_context(
            graph_nodes=[
                {"sensitivity": "CONFIDENTIAL", "tenant": "acme_engineering"},
                {"sensitivity": "RESTRICTED", "tenant": "acme_engineering"},
            ],
            clearance="INTERNAL",
        )
        assert severity_weighted_leakage(ctx) == 3.0

    def test_swl_cross_tenant_adds_one(self):
        """Cross-tenant item at or below clearance gets penalty of 1.0.

        This matches the paper formula: w(x,u) = 1 when
        tenant(x) != tenant(u) AND level(x) <= level(u).
        """
        ctx = _make_context(
            graph_nodes=[
                {"sensitivity": "PUBLIC", "tenant": "umbrella_security"},
            ],
            clearance="INTERNAL",
        )
        assert severity_weighted_leakage(ctx) == 1.0

    def test_swl_over_clearance_uses_tier_distance(self):
        """Over-clearance items get weight = tier distance, not +1."""
        ctx = _make_context(
            graph_nodes=[
                {"sensitivity": "RESTRICTED", "tenant": "acme_engineering"},
            ],
            clearance="PUBLIC",
        )
        # RESTRICTED (3) - PUBLIC (0) = 3
        assert severity_weighted_leakage(ctx) == 3.0

    def test_swl_matches_paper_formula(self):
        """Verify SWL matches the two-case formula from the paper.

        Case 1: over-clearance → weight = level_x - level_u
        Case 2: cross-tenant, within clearance → weight = 1
        """
        ctx = _make_context(
            graph_nodes=[
                # Case 1: CONFIDENTIAL (2) for INTERNAL (1) user → weight = 1
                {"sensitivity": "CONFIDENTIAL", "tenant": "acme_engineering"},
                # Case 2: PUBLIC (0) from other tenant → weight = 1
                {"sensitivity": "PUBLIC", "tenant": "umbrella_security"},
                # Not leaked: same tenant, within clearance
                {"sensitivity": "INTERNAL", "tenant": "acme_engineering"},
                # Case 1: RESTRICTED (3) for INTERNAL (1) → weight = 2
                {"sensitivity": "RESTRICTED", "tenant": "acme_engineering"},
            ],
            clearance="INTERNAL",
        )
        # Total: 1 + 1 + 0 + 2 = 4
        assert severity_weighted_leakage(ctx) == 4.0

    def test_swl_entity_empty_tenant_not_counted(self):
        """Entity nodes (tenant='') are excluded from SWL cross-tenant penalty."""
        ctx = _make_context(
            graph_nodes=[
                {"sensitivity": "PUBLIC", "tenant": ""},
            ],
            clearance="INTERNAL",
        )
        assert severity_weighted_leakage(ctx) == 0.0


class TestAmplificationFactorEpsilon:
    def test_finite_when_vector_zero(self):
        hybrid = [
            _make_context(graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "x"}])
            for _ in range(10)
        ]
        vector = [
            _make_context(chunks=[{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}])
            for _ in range(10)
        ]
        af_eps = amplification_factor_epsilon(hybrid, vector, epsilon=0.1)
        # Hybrid leakage = 1.0 per query, vector = 0 → AF(ε) = 1.0/0.1 = 10.0
        assert af_eps == 10.0

    def test_equals_standard_when_vector_nonzero(self):
        # Both have leakage → epsilon doesn't matter
        hybrid = [
            _make_context(graph_nodes=[
                {"sensitivity": "RESTRICTED", "tenant": "x"},
                {"sensitivity": "RESTRICTED", "tenant": "x"},
            ])
            for _ in range(10)
        ]
        vector = [
            _make_context(graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "x"}])
            for _ in range(10)
        ]
        af_eps = amplification_factor_epsilon(hybrid, vector, epsilon=0.1)
        # Hybrid = 2 per query, vector = 1 per query → AF(ε) = 2/max(1, 0.1) = 2.0
        assert af_eps == 2.0

    def test_zero_when_empty(self):
        assert amplification_factor_epsilon([], [], epsilon=0.1) == 0.0


class TestDeltaLeakage:
    def test_positive_delta(self):
        hybrid = [
            _make_context(graph_nodes=[
                {"sensitivity": "RESTRICTED", "tenant": "x"},
                {"sensitivity": "RESTRICTED", "tenant": "x"},
            ])
            for _ in range(10)
        ]
        vector = [
            _make_context(chunks=[{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}])
            for _ in range(10)
        ]
        d = delta_leakage(hybrid, vector)
        assert d == 2.0  # Hybrid = 2 per query, vector = 0

    def test_zero_delta_when_equal(self):
        both = [
            _make_context(graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "x"}])
            for _ in range(10)
        ]
        assert delta_leakage(both, both) == 0.0

    def test_zero_when_empty(self):
        assert delta_leakage([], []) == 0.0


class TestPivotDepth:
    def test_returns_hop_depth(self):
        ctx = _make_context(
            graph_nodes=[
                {"sensitivity": "RESTRICTED", "tenant": "x", "hop_depth": 2},
            ],
        )
        assert pivot_depth(ctx) == 2

    def test_returns_inf_when_no_leakage(self):
        ctx = _make_context(
            chunks=[{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}],
        )
        assert pivot_depth(ctx) == float("inf")

    def test_picks_minimum_depth(self):
        ctx = _make_context(
            graph_nodes=[
                {"sensitivity": "RESTRICTED", "tenant": "x", "hop_depth": 3},
                {"sensitivity": "RESTRICTED", "tenant": "x", "hop_depth": 2},
                {"sensitivity": "RESTRICTED", "tenant": "x", "hop_depth": 5},
            ],
        )
        assert pivot_depth(ctx) == 2

    def test_skips_missing_hop_depth(self):
        """Nodes without hop_depth should be skipped, not silently default to 1."""
        ctx = _make_context(
            graph_nodes=[
                {"sensitivity": "RESTRICTED", "tenant": "x"},  # No hop_depth
            ],
        )
        # Should return inf (skip) rather than silently reporting depth=1
        assert pivot_depth(ctx) == float("inf")

    def test_skips_invalid_hop_depth_uses_valid(self):
        """If some nodes have valid depth and some don't, use only valid ones."""
        ctx = _make_context(
            graph_nodes=[
                {"sensitivity": "RESTRICTED", "tenant": "x"},  # No hop_depth → skip
                {"sensitivity": "RESTRICTED", "tenant": "x", "hop_depth": 3},  # Valid
            ],
        )
        assert pivot_depth(ctx) == 3

    def test_negative_hop_depth_skipped(self):
        """Explicitly negative hop_depth (-1) should be skipped."""
        ctx = _make_context(
            graph_nodes=[
                {"sensitivity": "RESTRICTED", "tenant": "x", "hop_depth": -1},
            ],
        )
        assert pivot_depth(ctx) == float("inf")


class TestPivotDepthDistribution:
    def test_all_same_depth(self):
        contexts = [
            _make_context(
                graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "x", "hop_depth": 2}],
            )
            for _ in range(5)
        ]
        dist = pivot_depth_distribution(contexts)
        assert dist == {"min": 2, "median": 2, "max": 2}

    def test_varied_depths(self):
        contexts = [
            _make_context(
                graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "x", "hop_depth": d}],
            )
            for d in [1, 2, 2, 3, 4]
        ]
        dist = pivot_depth_distribution(contexts)
        assert dist["min"] == 1
        assert dist["median"] == 2
        assert dist["max"] == 4

    def test_no_leakage_returns_inf(self):
        contexts = [
            _make_context(chunks=[{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}])
            for _ in range(5)
        ]
        dist = pivot_depth_distribution(contexts)
        assert dist["min"] == float("inf")
        assert dist["median"] == float("inf")
        assert dist["max"] == float("inf")

    def test_mixed_leakage_and_clean(self):
        # 3 queries with leakage (depth 2), 2 clean queries
        contexts = [
            _make_context(
                graph_nodes=[{"sensitivity": "RESTRICTED", "tenant": "x", "hop_depth": 2}],
            )
            for _ in range(3)
        ] + [
            _make_context(chunks=[{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}])
            for _ in range(2)
        ]
        dist = pivot_depth_distribution(contexts)
        # Only 3 queries contribute PD; clean queries excluded
        assert dist == {"min": 2, "median": 2, "max": 2}


class TestBootstrapCI:
    def test_deterministic_with_seed(self):
        values = [0.0, 1.0, 1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0]
        ci1 = bootstrap_ci(values, n_boot=1000, seed=42)
        ci2 = bootstrap_ci(values, n_boot=1000, seed=42)
        assert ci1 == ci2

    def test_mean_matches(self):
        values = [1.0, 1.0, 1.0, 1.0, 1.0]
        mean, ci_low, ci_high = bootstrap_ci(values, n_boot=1000, seed=42)
        assert mean == 1.0
        assert ci_low == 1.0
        assert ci_high == 1.0

    def test_zero_values(self):
        values = [0.0, 0.0, 0.0, 0.0, 0.0]
        mean, ci_low, ci_high = bootstrap_ci(values, n_boot=1000, seed=42)
        assert mean == 0.0
        assert ci_low == 0.0
        assert ci_high == 0.0

    def test_empty_returns_zeros(self):
        assert bootstrap_ci([]) == (0.0, 0.0, 0.0)

    def test_ci_contains_mean(self):
        values = [0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
        mean, ci_low, ci_high = bootstrap_ci(values, n_boot=5000, seed=42)
        assert ci_low <= mean <= ci_high

    def test_wider_ci_with_more_variance(self):
        # Uniform values → narrow CI
        narrow_vals = [0.5] * 20
        _, narrow_low, narrow_high = bootstrap_ci(narrow_vals, n_boot=1000, seed=42)
        narrow_width = narrow_high - narrow_low

        # Variable values → wider CI
        wide_vals = [0.0, 1.0] * 10
        _, wide_low, wide_high = bootstrap_ci(wide_vals, n_boot=1000, seed=42)
        wide_width = wide_high - wide_low

        assert wide_width > narrow_width


# ---------------------------------------------------------------------------
# Context Recall and Precision (Utility Metrics)
# ---------------------------------------------------------------------------

class TestContextRecall:
    def test_perfect_recall(self):
        retrieved = ["doc_1", "doc_2", "doc_3"]
        ground_truth = ["doc_1", "doc_2", "doc_3"]
        assert context_recall_at_k(retrieved, ground_truth) == 1.0

    def test_partial_recall(self):
        retrieved = ["doc_1", "doc_4", "doc_5"]
        ground_truth = ["doc_1", "doc_2", "doc_3"]
        assert context_recall_at_k(retrieved, ground_truth) == 1 / 3

    def test_zero_recall(self):
        retrieved = ["doc_4", "doc_5"]
        ground_truth = ["doc_1", "doc_2"]
        assert context_recall_at_k(retrieved, ground_truth) == 0.0

    def test_empty_ground_truth(self):
        assert context_recall_at_k(["doc_1"], []) == 0.0

    def test_empty_retrieved(self):
        assert context_recall_at_k([], ["doc_1"]) == 0.0

    def test_superset_retrieval(self):
        """Retrieving more than ground truth still yields perfect recall."""
        retrieved = ["doc_1", "doc_2", "doc_3", "doc_4", "doc_5"]
        ground_truth = ["doc_1", "doc_2"]
        assert context_recall_at_k(retrieved, ground_truth) == 1.0


class TestContextPrecision:
    def test_perfect_precision(self):
        retrieved = ["doc_1", "doc_2"]
        ground_truth = ["doc_1", "doc_2"]
        assert context_precision_at_k(retrieved, ground_truth) == 1.0

    def test_partial_precision(self):
        retrieved = ["doc_1", "doc_4", "doc_5"]
        ground_truth = ["doc_1", "doc_2"]
        assert context_precision_at_k(retrieved, ground_truth) == 1 / 3

    def test_zero_precision(self):
        retrieved = ["doc_4", "doc_5"]
        ground_truth = ["doc_1", "doc_2"]
        assert context_precision_at_k(retrieved, ground_truth) == 0.0

    def test_empty_retrieved(self):
        assert context_precision_at_k([], ["doc_1"]) == 0.0

    def test_defense_reduces_precision_denominator(self):
        """When D1 filters items, precision denominator shrinks.

        This tests the key security-utility insight: D1 removes
        unauthorized items (reducing denominator) but also removes
        entity nodes (which may be relevant), potentially reducing
        the numerator too.
        """
        # Before D1: 10 items, 3 relevant
        before = [f"doc_{i}" for i in range(10)]
        gt = ["doc_0", "doc_1", "doc_2"]
        precision_before = context_precision_at_k(before, gt)

        # After D1: 5 items (filtered 5 unauthorized), 3 relevant survive
        after = ["doc_0", "doc_1", "doc_2", "doc_7", "doc_8"]
        precision_after = context_precision_at_k(after, gt)

        # Precision improves when unauthorized (irrelevant) items are removed
        assert precision_after > precision_before
