"""Tests for graph schema and policy enforcement."""

from pivorag.config import SensitivityTier
from pivorag.graph.policy import EdgeAllowlist, TraversalBudget, TraversalPolicy
from pivorag.graph.schema import GraphNode


class TestTraversalPolicy:
    def test_denies_high_sensitivity(self, sensitive_node):
        policy = TraversalPolicy(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        assert not policy.is_node_authorized(sensitive_node)

    def test_allows_authorized_node(self, sample_chunk):
        node = GraphNode(
            node_id="chunk_1",
            node_type="Chunk",
            tenant="acme_engineering",
            sensitivity="PUBLIC",
        )
        policy = TraversalPolicy(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        assert policy.is_node_authorized(node)

    def test_denies_cross_tenant(self, bridge_node):
        policy = TraversalPolicy(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.CONFIDENTIAL,
            deny_cross_tenant=True,
        )
        # Bridge node has empty tenant, should be denied
        assert not policy.is_node_authorized(bridge_node)

    def test_filter_expansion_removes_unauthorized(self, sensitive_node):
        public_node = GraphNode(
            node_id="pub_1", node_type="Document",
            tenant="acme_engineering", sensitivity="PUBLIC",
        )
        policy = TraversalPolicy(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        filtered = policy.filter_expansion([public_node, sensitive_node])
        assert len(filtered) == 1
        assert filtered[0].node_id == "pub_1"


class TestEdgeAllowlist:
    def test_returns_allowed_edges(self):
        config = {
            "dependency": {"allowed": ["DEPENDS_ON", "CONTAINS"]},
            "general": {"allowed": ["CONTAINS", "MENTIONS"]},
        }
        allowlist = EdgeAllowlist(config)
        assert "DEPENDS_ON" in allowlist.get_allowed_edges("dependency")
        assert "DEPENDS_ON" not in allowlist.get_allowed_edges("general")


class TestTraversalBudget:
    def test_respects_hop_limit(self):
        budget = TraversalBudget(max_hops=2)
        assert budget.can_continue(1, 5)
        assert not budget.can_continue(2, 5)

    def test_respects_node_limit(self):
        budget = TraversalBudget(max_total_nodes=10)
        budget.record_visit(10)
        assert not budget.can_continue(0, 1)
