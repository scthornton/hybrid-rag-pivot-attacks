"""Pipeline integration smoke tests.

Tests that the defense stack operates correctly end-to-end through
the HybridPipeline, using mocked vector/graph backends.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from pivorag.config import (
    DefenseConfig,
    GraphConfig,
    PipelineConfig,
    SensitivityTier,
)
from pivorag.graph.expand import ExpansionResult, GraphExpander
from pivorag.graph.schema import GraphNode
from pivorag.pipelines.hybrid import HybridPipeline


@dataclass
class _MockVectorResult:
    """Minimal vector result for testing."""

    chunk_id: str
    text: str
    score: float
    metadata: dict


def _mock_vector_retriever(results: list[_MockVectorResult]):
    """Create a mock VectorRetriever that returns fixed results."""
    retriever = MagicMock()
    retriever.retrieve.return_value = results
    return retriever


def _mock_graph_expander(nodes: list[GraphNode], depths: dict[str, int]):
    """Create a mock GraphExpander returning fixed expansion results."""
    expander = MagicMock(spec=GraphExpander)
    expander.bfs_expand.return_value = ExpansionResult(
        seed_nodes=["seed_1"],
        expanded_nodes=nodes,
        traversal_path=[],
        total_hops=2,
        nodes_visited=len(nodes),
        edges_traversed=0,
        node_depths=depths,
    )
    return expander


class TestHybridPipelineD1:
    """Test D1 per-hop authorization through the full pipeline."""

    def test_d1_filters_cross_tenant_nodes(self):
        """Cross-tenant nodes must be removed when D1 is enabled."""
        vector_results = [
            _MockVectorResult(
                chunk_id="chunk_1", text="test", score=0.9,
                metadata={"tenant": "acme_engineering", "sensitivity": "INTERNAL"},
            ),
        ]
        graph_nodes = [
            GraphNode(
                node_id="chunk_1", node_type="Chunk",
                tenant="acme_engineering", sensitivity="INTERNAL",
            ),
            GraphNode(
                node_id="ent_shared", node_type="Entity",
                tenant="", sensitivity="PUBLIC",
            ),
            GraphNode(
                node_id="cross_chunk", node_type="Chunk",
                tenant="globex_finance", sensitivity="CONFIDENTIAL",
            ),
        ]
        depths = {"chunk_1": 0, "ent_shared": 1, "cross_chunk": 2}

        config = PipelineConfig(
            name="test_d1", variant="P4",
            graph=GraphConfig(enabled=True),
            defenses=DefenseConfig(
                per_hop_authz={"enabled": True, "deny_cross_tenant": True},
            ),
        )

        pipeline = HybridPipeline(
            config=config,
            vector_retriever=_mock_vector_retriever(vector_results),
            graph_expander=_mock_graph_expander(graph_nodes, depths),
        )

        ctx = pipeline.retrieve(
            query="test query",
            user_id="u1",
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )

        # Only acme_engineering + within-clearance nodes survive
        graph_tenants = {n["tenant"] for n in ctx.graph_nodes}
        assert "globex_finance" not in graph_tenants
        assert "" not in graph_tenants  # Entity nodes filtered too
        assert "acme_engineering" in graph_tenants


class TestHybridPipelineD5:
    """Test D5 merge filter uses correct comparison (not alphabetical)."""

    def test_d5_uses_correct_comparison(self):
        """D5 must allow PUBLIC items for INTERNAL user (was broken with <=)."""
        vector_results = [
            _MockVectorResult(
                chunk_id="chunk_1", text="test", score=0.9,
                metadata={"tenant": "acme_engineering", "sensitivity": "PUBLIC"},
            ),
        ]
        graph_nodes = [
            GraphNode(
                node_id="pub_node", node_type="Chunk",
                tenant="acme_engineering", sensitivity="PUBLIC",
            ),
            GraphNode(
                node_id="internal_node", node_type="Chunk",
                tenant="acme_engineering", sensitivity="INTERNAL",
            ),
            GraphNode(
                node_id="conf_node", node_type="Chunk",
                tenant="acme_engineering", sensitivity="CONFIDENTIAL",
            ),
        ]
        depths = {"pub_node": 0, "internal_node": 1, "conf_node": 2}

        config = PipelineConfig(
            name="test_d5", variant="P8",
            graph=GraphConfig(enabled=True),
            defenses=DefenseConfig(
                merge_filter={"enabled": True},
            ),
        )

        pipeline = HybridPipeline(
            config=config,
            vector_retriever=_mock_vector_retriever(vector_results),
            graph_expander=_mock_graph_expander(graph_nodes, depths),
        )

        ctx = pipeline.retrieve(
            query="test query",
            user_id="u1",
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )

        result_sensitivities = {n["sensitivity"] for n in ctx.graph_nodes}
        # PUBLIC and INTERNAL should pass; CONFIDENTIAL should be blocked
        assert "PUBLIC" in result_sensitivities
        assert "INTERNAL" in result_sensitivities
        assert "CONFIDENTIAL" not in result_sensitivities


class TestDefenseStackOrdering:
    """Verify defenses are applied in the correct order: D1→D2→D3→D4→D5."""

    def test_d1_before_d4(self):
        """D1 removes unauthorized nodes BEFORE D4 checks trust scores.

        This means an unauthorized high-trust node is still removed.
        """
        vector_results = [
            _MockVectorResult(
                chunk_id="seed", text="test", score=0.9,
                metadata={"tenant": "acme_engineering", "sensitivity": "PUBLIC"},
            ),
        ]
        graph_nodes = [
            GraphNode(
                node_id="auth_low_trust", node_type="Chunk",
                tenant="acme_engineering", sensitivity="PUBLIC",
                provenance_score=0.3,
            ),
            GraphNode(
                node_id="auth_high_trust", node_type="Chunk",
                tenant="acme_engineering", sensitivity="PUBLIC",
                provenance_score=0.9,
            ),
            GraphNode(
                node_id="unauth_high_trust", node_type="Chunk",
                tenant="globex_finance", sensitivity="PUBLIC",
                provenance_score=0.99,
            ),
        ]
        depths = {n.node_id: 1 for n in graph_nodes}

        config = PipelineConfig(
            name="test_stack", variant="P4+D4",
            graph=GraphConfig(enabled=True),
            defenses=DefenseConfig(
                per_hop_authz={"enabled": True, "deny_cross_tenant": True},
                trust_weighting={"enabled": True, "min_trust_score": 0.5},
            ),
        )

        pipeline = HybridPipeline(
            config=config,
            vector_retriever=_mock_vector_retriever(vector_results),
            graph_expander=_mock_graph_expander(graph_nodes, depths),
        )

        ctx = pipeline.retrieve(
            query="test query",
            user_id="u1",
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )

        result_ids = {n["node_id"] for n in ctx.graph_nodes}
        # D1 removes unauth_high_trust (cross-tenant)
        assert "unauth_high_trust" not in result_ids
        # D4 removes auth_low_trust (trust < 0.5)
        assert "auth_low_trust" not in result_ids
        # Only auth_high_trust survives both filters
        assert "auth_high_trust" in result_ids


class TestD2QueryClassification:
    """Test that D2 classifies queries instead of always using 'general'."""

    def test_dependency_query_uses_dependency_edges(self):
        """A query about dependencies should get DEPENDS_ON edges."""
        vector_results = [
            _MockVectorResult(
                chunk_id="seed", text="test", score=0.9,
                metadata={"tenant": "acme_engineering", "sensitivity": "PUBLIC"},
            ),
        ]
        graph_nodes = []
        depths = {}

        config = PipelineConfig(
            name="test_d2", variant="P5",
            graph=GraphConfig(enabled=True),
            defenses=DefenseConfig(
                edge_allowlist={
                    "enabled": True,
                    "query_classes": {
                        "dependency": {"allowed": ["DEPENDS_ON"]},
                        "general": {"allowed": ["MENTIONS", "CONTAINS"]},
                    },
                },
            ),
        )

        pipeline = HybridPipeline(
            config=config,
            vector_retriever=_mock_vector_retriever(vector_results),
            graph_expander=_mock_graph_expander(graph_nodes, depths),
        )

        pipeline.retrieve(
            query="what depends on auth-service?",
            user_id="u1",
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )

        # Verify the expander was called with DEPENDS_ON edge type
        call_kwargs = pipeline.graph_expander.bfs_expand.call_args
        edge_types = call_kwargs.kwargs.get(
            "allowed_edge_types",
            call_kwargs[1].get("allowed_edge_types") if len(call_kwargs) > 1 else None,
        )
        assert edge_types == ["DEPENDS_ON"]
