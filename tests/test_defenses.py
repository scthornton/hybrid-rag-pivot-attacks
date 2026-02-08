"""Tests for defense implementations.

Tests cover:
- D1 (PerHopAuthz): entity filtering, multi-hop escalation, bypass attempts
- D2 (EdgeAllowlist): query classification, edge restriction
- D3 (Budget): traversal cap enforcement, parameter constraining
- D4 (TrustWeighting): low-trust filtering, path decay
- D5 (MergeFilter): cross-tenant backstop, sensitivity filtering
- Defense combinations: D1+D2+D3 layered enforcement
"""

from pivorag.config import SensitivityTier
from pivorag.defenses.budgets import BudgetDefense
from pivorag.defenses.edge_allowlist import EdgeAllowlistDefense
from pivorag.defenses.merge_filter import MergeFilterDefense
from pivorag.defenses.per_hop_authz import PerHopAuthzDefense
from pivorag.defenses.trust_weighting import TrustWeightingDefense
from pivorag.graph.schema import GraphNode

# ---------------------------------------------------------------------------
# Helper: build a set of nodes simulating a typical BFS expansion result
# ---------------------------------------------------------------------------

def _make_expansion_nodes() -> list[GraphNode]:
    """Simulate a 2-hop BFS expansion across tenants.

    Seed chunk (acme) → entity (tenant="") → target chunk (globex).
    This is the exact 2-hop pivot path the paper describes.
    """
    return [
        GraphNode(
            node_id="seed_chunk", node_type="Chunk",
            tenant="acme_engineering", sensitivity="INTERNAL",
        ),
        GraphNode(
            node_id="ent_cloudcorp", node_type="Entity",
            tenant="", sensitivity="PUBLIC",
        ),
        GraphNode(
            node_id="cross_chunk", node_type="Chunk",
            tenant="globex_finance", sensitivity="CONFIDENTIAL",
        ),
        GraphNode(
            node_id="same_chunk", node_type="Chunk",
            tenant="acme_engineering", sensitivity="PUBLIC",
        ),
    ]


class TestPerHopAuthz:
    def test_filters_unauthorized(self, sensitive_node):
        defense = PerHopAuthzDefense(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        result = defense.filter([sensitive_node])
        assert len(result) == 0

    def test_d1_filters_entity_nodes_with_empty_tenant(self):
        """D1 must filter entity nodes with tenant="" — this severs the pivot path."""
        nodes = _make_expansion_nodes()
        defense = PerHopAuthzDefense(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.CONFIDENTIAL,
        )
        result = defense.filter(nodes)
        result_ids = {n.node_id for n in result}
        # Entity with empty tenant is filtered (severs pivot)
        assert "ent_cloudcorp" not in result_ids
        # Cross-tenant chunk is also filtered
        assert "cross_chunk" not in result_ids
        # Same-tenant chunks survive
        assert "seed_chunk" in result_ids
        assert "same_chunk" in result_ids

    def test_d1_blocks_multi_hop_sensitivity_escalation(self):
        """D1 blocks INTERNAL→CONFIDENTIAL→RESTRICTED escalation within same tenant."""
        internal_chunk = GraphNode(
            node_id="internal_1", node_type="Chunk",
            tenant="acme_engineering", sensitivity="INTERNAL",
        )
        confidential_chunk = GraphNode(
            node_id="confidential_1", node_type="Chunk",
            tenant="acme_engineering", sensitivity="CONFIDENTIAL",
        )
        restricted_chunk = GraphNode(
            node_id="restricted_1", node_type="Chunk",
            tenant="acme_engineering", sensitivity="RESTRICTED",
        )
        defense = PerHopAuthzDefense(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        # Hop-level check: INTERNAL→CONFIDENTIAL blocked
        assert not defense.check_hop(
            internal_chunk, confidential_chunk, "MENTIONS",
        )
        # Hop-level check: INTERNAL→RESTRICTED blocked
        assert not defense.check_hop(
            internal_chunk, restricted_chunk, "MENTIONS",
        )
        # Node-level filter removes both
        result = defense.filter([internal_chunk, confidential_chunk, restricted_chunk])
        assert len(result) == 1
        assert result[0].node_id == "internal_1"

    def test_d1_allows_all_authorized_nodes(self):
        """D1 retains all nodes matching tenant + clearance."""
        nodes = [
            GraphNode(
                node_id=f"chunk_{i}", node_type="Chunk",
                tenant="acme_engineering", sensitivity="PUBLIC",
            )
            for i in range(10)
        ]
        defense = PerHopAuthzDefense(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        result = defense.filter(nodes)
        assert len(result) == 10

    def test_d1_rpr_zero_on_mixed_expansion(self):
        """Simulates D1 on a realistic expansion: only authorized items remain."""
        nodes = _make_expansion_nodes()
        defense = PerHopAuthzDefense(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        result = defense.filter(nodes)
        # Every surviving node must be acme_engineering + within clearance
        for node in result:
            assert node.tenant == "acme_engineering"
            node_tier = SensitivityTier(node.sensitivity)
            assert not (node_tier > SensitivityTier.INTERNAL)


class TestEdgeAllowlist:
    def test_classifies_dependency_query(self):
        defense = EdgeAllowlistDefense({
            "dependency": {"allowed": ["DEPENDS_ON", "CONTAINS"]},
            "general": {"allowed": ["MENTIONS"]},
        })
        # Keyword classifier matches "depends" (not stem "depend")
        assert defense.classify_query("what depends on this?") == "dependency"
        assert defense.classify_query("show me the dependency chain") == "dependency"
        assert defense.classify_query("tell me about the project") == "general"

    def test_restricts_edge_types(self):
        defense = EdgeAllowlistDefense({
            "dependency": {"allowed": ["DEPENDS_ON"]},
            "general": {"allowed": ["MENTIONS", "CONTAINS"]},
        })
        dep_edges = defense.get_allowed_edges("dependency")
        assert dep_edges == ["DEPENDS_ON"]
        assert "MENTIONS" not in dep_edges

    def test_falls_back_to_general(self):
        defense = EdgeAllowlistDefense({
            "general": {"allowed": ["MENTIONS"]},
        })
        edges = defense.get_allowed_edges("unknown_class")
        assert edges == ["MENTIONS"]


class TestBudgetDefense:
    def test_constrains_parameters(self):
        defense = BudgetDefense(max_hops=2, max_branching_factor=5, max_total_nodes=20)
        hops, branch, total = defense.get_constrained_params(
            requested_hops=5, requested_branching=10, requested_total=100,
        )
        assert hops == 2
        assert branch == 5
        assert total == 20

    def test_passes_through_smaller_requests(self):
        defense = BudgetDefense(max_hops=3, max_branching_factor=10, max_total_nodes=50)
        hops, branch, total = defense.get_constrained_params(
            requested_hops=1, requested_branching=5, requested_total=25,
        )
        assert hops == 1
        assert branch == 5
        assert total == 25


class TestTrustWeighting:
    def test_filters_low_trust(self):
        defense = TrustWeightingDefense(min_trust_score=0.6)
        low_trust = GraphNode(
            node_id="lt_1", node_type="Entity",
            provenance_score=0.3,
        )
        high_trust = GraphNode(
            node_id="ht_1", node_type="Entity",
            provenance_score=0.9,
        )
        result = defense.filter_by_trust([low_trust, high_trust])
        assert len(result) == 1
        assert result[0].node_id == "ht_1"

    def test_path_trust_decays(self):
        defense = TrustWeightingDefense(trust_decay_per_hop=0.15)
        trust = defense.compute_path_trust([0.9, 0.8, 0.7])
        assert trust < 0.9 * 0.8 * 0.7  # Decay should reduce further

    def test_boundary_trust_score(self):
        """Node exactly at threshold should be retained."""
        defense = TrustWeightingDefense(min_trust_score=0.5)
        boundary = GraphNode(
            node_id="b_1", node_type="Chunk",
            provenance_score=0.5,
        )
        result = defense.filter_by_trust([boundary])
        assert len(result) == 1


class TestMergeFilter:
    def test_denies_cross_tenant(self):
        defense = MergeFilterDefense(deny_by_default=True)
        items = [
            {"sensitivity": "PUBLIC", "tenant": "acme_engineering"},
            {"sensitivity": "PUBLIC", "tenant": "umbrella_security"},
        ]
        result = defense.filter_context(
            items,
            user_clearance=SensitivityTier.INTERNAL,
            user_tenant="acme_engineering",
        )
        assert len(result) == 1

    def test_denies_over_clearance(self):
        """D5 must filter items above user clearance regardless of tenant."""
        defense = MergeFilterDefense(deny_by_default=True)
        items = [
            {"sensitivity": "RESTRICTED", "tenant": "acme_engineering"},
            {"sensitivity": "PUBLIC", "tenant": "acme_engineering"},
        ]
        result = defense.filter_context(
            items,
            user_clearance=SensitivityTier.INTERNAL,
            user_tenant="acme_engineering",
        )
        assert len(result) == 1
        assert result[0]["sensitivity"] == "PUBLIC"


class TestD5StrEnumComparison:
    """Regression tests for the D5 merge filter StrEnum comparison bug.

    The original code used ``node_tier <= user_clearance`` which invoked
    StrEnum's alphabetical __le__. These tests verify the fix uses numeric
    level ordering via the custom comparison operators.
    """

    def test_d5_allows_public_for_internal_user(self):
        """PUBLIC (level 0) should pass for INTERNAL (level 1) user.

        This was the critical failure: alphabetically P > I, so
        ``PUBLIC <= INTERNAL`` returned False, wrongly filtering PUBLIC items.
        """
        defense = MergeFilterDefense(deny_by_default=True)
        items = [{"sensitivity": "PUBLIC", "tenant": "acme_engineering"}]
        result = defense.filter_context(
            items,
            user_clearance=SensitivityTier.INTERNAL,
            user_tenant="acme_engineering",
        )
        assert len(result) == 1

    def test_d5_allows_internal_for_internal_user(self):
        """INTERNAL == INTERNAL should pass (same level)."""
        defense = MergeFilterDefense(deny_by_default=True)
        items = [{"sensitivity": "INTERNAL", "tenant": "acme_engineering"}]
        result = defense.filter_context(
            items,
            user_clearance=SensitivityTier.INTERNAL,
            user_tenant="acme_engineering",
        )
        assert len(result) == 1

    def test_d5_blocks_confidential_for_internal_user(self):
        """CONFIDENTIAL (level 2) must be blocked for INTERNAL (level 1) user."""
        defense = MergeFilterDefense(deny_by_default=True)
        items = [{"sensitivity": "CONFIDENTIAL", "tenant": "acme_engineering"}]
        result = defense.filter_context(
            items,
            user_clearance=SensitivityTier.INTERNAL,
            user_tenant="acme_engineering",
        )
        assert len(result) == 0

    def test_d5_blocks_restricted_for_internal_user(self):
        """RESTRICTED (level 3) must be blocked for INTERNAL (level 1) user."""
        defense = MergeFilterDefense(deny_by_default=True)
        items = [{"sensitivity": "RESTRICTED", "tenant": "acme_engineering"}]
        result = defense.filter_context(
            items,
            user_clearance=SensitivityTier.INTERNAL,
            user_tenant="acme_engineering",
        )
        assert len(result) == 0

    def test_d5_blocks_restricted_for_confidential_user(self):
        """RESTRICTED (level 3) blocked for CONFIDENTIAL (level 2) user."""
        defense = MergeFilterDefense(deny_by_default=True)
        items = [{"sensitivity": "RESTRICTED", "tenant": "acme_engineering"}]
        result = defense.filter_context(
            items,
            user_clearance=SensitivityTier.CONFIDENTIAL,
            user_tenant="acme_engineering",
        )
        assert len(result) == 0

    def test_d5_comparison_not_alphabetical(self):
        """Explicit regression: alphabetical ordering is wrong for D5.

        Alphabetically: CONFIDENTIAL < INTERNAL < PUBLIC < RESTRICTED.
        This means ``CONFIDENTIAL <= INTERNAL`` would be True (C < I, correct
        by accident) but ``PUBLIC <= INTERNAL`` would be False (P > I, WRONG).
        """
        defense = MergeFilterDefense(deny_by_default=True)
        items = [
            {"sensitivity": "PUBLIC", "tenant": "acme_engineering"},
            {"sensitivity": "INTERNAL", "tenant": "acme_engineering"},
            {"sensitivity": "CONFIDENTIAL", "tenant": "acme_engineering"},
            {"sensitivity": "RESTRICTED", "tenant": "acme_engineering"},
        ]
        result = defense.filter_context(
            items,
            user_clearance=SensitivityTier.INTERNAL,
            user_tenant="acme_engineering",
        )
        # Only PUBLIC and INTERNAL should pass
        result_tiers = {item["sensitivity"] for item in result}
        assert result_tiers == {"PUBLIC", "INTERNAL"}


# ---------------------------------------------------------------------------
# Defense combination tests
# ---------------------------------------------------------------------------

class TestDefenseCombinations:
    """Test layered defense-in-depth behavior (D1+D2+D3, D1+D4, etc.)."""

    def test_d1_plus_d4_layered_filtering(self):
        """D1 removes unauthorized; D4 removes low-provenance from survivors."""
        nodes = [
            GraphNode(
                node_id="auth_high", node_type="Chunk",
                tenant="acme_engineering", sensitivity="PUBLIC",
                provenance_score=0.9,
            ),
            GraphNode(
                node_id="auth_low", node_type="Chunk",
                tenant="acme_engineering", sensitivity="PUBLIC",
                provenance_score=0.2,
            ),
            GraphNode(
                node_id="unauth", node_type="Chunk",
                tenant="globex_finance", sensitivity="PUBLIC",
                provenance_score=0.9,
            ),
        ]

        # D1 pass
        d1 = PerHopAuthzDefense(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        after_d1 = d1.filter(nodes)
        assert len(after_d1) == 2  # unauth removed

        # D4 pass
        d4 = TrustWeightingDefense(min_trust_score=0.5)
        after_d4 = d4.filter_by_trust(after_d1)
        assert len(after_d4) == 1
        assert after_d4[0].node_id == "auth_high"

    def test_d2_restricts_then_d1_filters(self):
        """D2 limits edge types (query-level), D1 filters nodes (expansion-level)."""
        d2 = EdgeAllowlistDefense({
            "general": {"allowed": ["MENTIONS"]},
            "dependency": {"allowed": ["DEPENDS_ON"]},
        })
        # Simulating: query classified as "general" → only MENTIONS edges
        allowed = d2.get_allowed_edges("general")
        assert "DEPENDS_ON" not in allowed

        # After BFS runs with restricted edges, D1 still filters
        d1 = PerHopAuthzDefense(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        expansion_result = _make_expansion_nodes()
        after_d1 = d1.filter(expansion_result)
        # Entity and cross-tenant both removed
        assert all(n.tenant == "acme_engineering" for n in after_d1)

    def test_d3_constrains_before_d1_filters(self):
        """D3 limits traversal scope, D1 filters the (smaller) result."""
        d3 = BudgetDefense(max_hops=1, max_total_nodes=5)
        hops, _, total = d3.get_constrained_params(
            requested_hops=3, requested_branching=10, requested_total=100,
        )
        assert hops == 1  # Would prevent reaching hop-2 nodes

        # Even if D3 fails (e.g., bug), D1 still catches unauthorized
        d1 = PerHopAuthzDefense(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        expansion_result = _make_expansion_nodes()
        after_d1 = d1.filter(expansion_result)
        assert all(n.tenant == "acme_engineering" for n in after_d1)
