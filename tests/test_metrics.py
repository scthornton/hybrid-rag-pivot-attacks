"""Tests for security and utility metrics."""

from pivorag.config import SensitivityTier
from pivorag.eval.metrics import (
    amplification_factor,
    leakage_at_k,
    retrieval_pivot_risk,
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
