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
