"""Tests for graph schema, policy enforcement, and BFS expansion."""

from unittest.mock import MagicMock

from pivorag.config import SensitivityTier
from pivorag.graph.expand import VALID_EDGE_TYPES, ExpansionResult, GraphExpander
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

    def test_none_tenant_rejected_by_pydantic(self):
        """GraphNode schema enforces tenant as str, so None is impossible.

        This documents that the `node.tenant is None` branch in
        policy.py:38 is unreachable — Neo4j NULLs are coerced to ""
        by bfs_expand() before GraphNode construction.
        """
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            GraphNode(node_id="ent_1", node_type="Entity", tenant=None, sensitivity="PUBLIC")

    def test_entity_with_empty_tenant_denied(self):
        """Entity nodes default to tenant='' which D1 correctly denies.

        This is a critical design property: entity nodes are tenant-neutral,
        so D1 filters them out, preventing cross-tenant pivot at hop 1.
        This is the primary mechanism by which D1 eliminates leakage.
        """
        entity = GraphNode(
            node_id="ent_cloudcorp", node_type="Entity",
            tenant="", sensitivity="PUBLIC",
        )
        policy = TraversalPolicy(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.CONFIDENTIAL,
        )
        assert not policy.is_node_authorized(entity)

    def test_entity_with_matching_tenant_allowed(self):
        """If an entity carries a specific tenant label, D1 allows it."""
        entity = GraphNode(
            node_id="ent_proj_alpha", node_type="Entity",
            tenant="acme_engineering", sensitivity="PUBLIC",
        )
        policy = TraversalPolicy(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        assert policy.is_node_authorized(entity)

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

    def test_hop_blocks_sensitivity_escalation(self):
        """D1 blocks traversal from INTERNAL to RESTRICTED within same tenant."""
        internal_node = GraphNode(
            node_id="src_1", node_type="Chunk",
            tenant="acme_engineering", sensitivity="INTERNAL",
        )
        restricted_node = GraphNode(
            node_id="tgt_1", node_type="Chunk",
            tenant="acme_engineering", sensitivity="RESTRICTED",
        )
        policy = TraversalPolicy(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
            deny_sensitivity_escalation=True,
        )
        assert not policy.is_hop_allowed(internal_node, restricted_node, "DEPENDS_ON")

    def test_hop_allows_same_or_lower_sensitivity(self):
        """Traversal from INTERNAL to PUBLIC is always allowed."""
        internal_node = GraphNode(
            node_id="src_1", node_type="Chunk",
            tenant="acme_engineering", sensitivity="INTERNAL",
        )
        public_node = GraphNode(
            node_id="tgt_1", node_type="Chunk",
            tenant="acme_engineering", sensitivity="PUBLIC",
        )
        policy = TraversalPolicy(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        assert policy.is_hop_allowed(internal_node, public_node, "MENTIONS")


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

    def test_respects_branching_factor(self):
        budget = TraversalBudget(max_branching_factor=5)
        assert budget.can_continue(0, 4)
        assert not budget.can_continue(0, 5)

    def test_reset_clears_visited(self):
        budget = TraversalBudget(max_total_nodes=10)
        budget.record_visit(10)
        assert not budget.can_continue(0, 1)
        budget.reset()
        assert budget.can_continue(0, 1)


# ---------------------------------------------------------------------------
# BFS Expansion Tests (using mocked Neo4j driver)
# ---------------------------------------------------------------------------

def _mock_neo4j_records(records: list[dict]):
    """Create a mock Neo4j session that returns given records."""
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter(records))

    mock_session = MagicMock()
    mock_session.run.return_value = mock_result
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session
    return mock_driver


def _make_record(node_id, node_type="Chunk", tenant="acme_engineering",
                 sensitivity="PUBLIC", provenance_score=1.0, hop_depth=0, props=None):
    """Create a dict mimicking a Neo4j record."""
    return {
        "node_id": node_id,
        "node_type": node_type,
        "tenant": tenant,
        "sensitivity": sensitivity,
        "provenance_score": provenance_score,
        "props": props or {},
        "hop_depth": hop_depth,
    }


class TestBFSExpand:
    def test_single_seed_returns_neighbors(self):
        """BFS from a single seed returns the seed + its neighbors."""
        records = [
            _make_record("seed_1", hop_depth=0),
            _make_record("ent_alpha", node_type="Entity", tenant="", hop_depth=1),
            _make_record("chunk_2", hop_depth=2, tenant="globex_finance"),
        ]
        driver = _mock_neo4j_records(records)
        expander = GraphExpander(driver)

        result = expander.bfs_expand(["seed_1"], max_hops=2, max_total_nodes=50)

        assert isinstance(result, ExpansionResult)
        assert len(result.expanded_nodes) == 3
        assert result.seed_nodes == ["seed_1"]
        assert result.nodes_visited == 3

    def test_hop_depths_populated_correctly(self):
        """node_depths should map each node_id to its BFS distance."""
        records = [
            _make_record("seed_1", hop_depth=0),
            _make_record("hop1_a", hop_depth=1),
            _make_record("hop1_b", hop_depth=1),
            _make_record("hop2_a", hop_depth=2),
        ]
        driver = _mock_neo4j_records(records)
        expander = GraphExpander(driver)

        result = expander.bfs_expand(["seed_1"])

        assert result.node_depths["seed_1"] == 0
        assert result.node_depths["hop1_a"] == 1
        assert result.node_depths["hop1_b"] == 1
        assert result.node_depths["hop2_a"] == 2

    def test_hop_depths_monotonic(self):
        """Hop depths should be non-decreasing when results are ordered."""
        records = [
            _make_record("s", hop_depth=0),
            _make_record("a", hop_depth=1),
            _make_record("b", hop_depth=1),
            _make_record("c", hop_depth=2),
            _make_record("d", hop_depth=2),
            _make_record("e", hop_depth=3),
        ]
        driver = _mock_neo4j_records(records)
        expander = GraphExpander(driver)

        result = expander.bfs_expand(["s"], max_hops=3, max_total_nodes=100)

        depths = [result.node_depths[n.node_id] for n in result.expanded_nodes]
        for i in range(1, len(depths)):
            assert depths[i] >= depths[i - 1], (
                f"Hop depths not monotonic: {depths}"
            )

    def test_empty_result_for_nonexistent_seed(self):
        """If seed doesn't exist in graph, should return empty result."""
        driver = _mock_neo4j_records([])
        expander = GraphExpander(driver)

        result = expander.bfs_expand(["nonexistent_node"])

        assert len(result.expanded_nodes) == 0
        assert result.node_depths == {}
        assert result.nodes_visited == 0

    def test_tenant_preserved_from_neo4j(self):
        """Tenant labels from Neo4j should be preserved correctly."""
        records = [
            _make_record("chunk_1", tenant="acme_engineering", hop_depth=0),
            _make_record("ent_shared", tenant="", node_type="Entity", hop_depth=1),
            _make_record("chunk_2", tenant="globex_finance", hop_depth=2),
        ]
        driver = _mock_neo4j_records(records)
        expander = GraphExpander(driver)

        result = expander.bfs_expand(["chunk_1"])

        tenants = {n.node_id: n.tenant for n in result.expanded_nodes}
        assert tenants["chunk_1"] == "acme_engineering"
        assert tenants["ent_shared"] == ""
        assert tenants["chunk_2"] == "globex_finance"

    def test_null_tenant_becomes_empty_string(self):
        """Neo4j NULL tenant should be coerced to empty string."""
        records = [
            _make_record("ent_1", tenant=None, node_type="Entity", hop_depth=0),
        ]
        driver = _mock_neo4j_records(records)
        expander = GraphExpander(driver)

        result = expander.bfs_expand(["ent_1"])

        assert result.expanded_nodes[0].tenant == ""

    def test_edge_filter_passed_to_cypher(self):
        """allowed_edge_types should be included in the Cypher query."""
        driver = _mock_neo4j_records([])
        expander = GraphExpander(driver)

        expander.bfs_expand(
            ["seed_1"], allowed_edge_types=["MENTIONS", "DEPENDS_ON"],
        )

        session = driver.session.return_value.__enter__.return_value
        cypher_query = session.run.call_args[0][0]
        assert "MENTIONS|DEPENDS_ON" in cypher_query

    def test_max_total_nodes_passed_to_cypher(self):
        """max_total_nodes should be passed as $max_total parameter."""
        driver = _mock_neo4j_records([])
        expander = GraphExpander(driver)

        expander.bfs_expand(["seed_1"], max_total_nodes=25)

        session = driver.session.return_value.__enter__.return_value
        params = session.run.call_args[0][1]
        assert params["max_total"] == 25


# ---------------------------------------------------------------------------
# Cypher Injection Prevention Tests
# ---------------------------------------------------------------------------

class TestCypherInjectionPrevention:
    def test_invalid_edge_type_filtered(self):
        """Edge types not in VALID_EDGE_TYPES must be silently dropped."""
        driver = _mock_neo4j_records([])
        expander = GraphExpander(driver)

        expander.bfs_expand(
            ["seed_1"],
            allowed_edge_types=["MENTIONS", "EVIL_DROP_TABLE"],
        )

        session = driver.session.return_value.__enter__.return_value
        cypher_query = session.run.call_args[0][0]
        assert "MENTIONS" in cypher_query
        assert "EVIL_DROP_TABLE" not in cypher_query

    def test_edge_type_with_special_chars_rejected(self):
        """Edge types with Cypher injection characters must be rejected."""
        driver = _mock_neo4j_records([])
        expander = GraphExpander(driver)

        malicious_types = [
            "MENTIONS}] RETURN 1//",
            "'; DROP (n)--",
            "CONTAINS|MATCH (n)",
        ]
        expander.bfs_expand(["seed_1"], allowed_edge_types=malicious_types)

        session = driver.session.return_value.__enter__.return_value
        cypher_query = session.run.call_args[0][0]
        # None of the malicious types should appear in the query
        for mt in malicious_types:
            assert mt not in cypher_query

    def test_all_valid_edge_types_pass(self):
        """All types in VALID_EDGE_TYPES should pass validation."""
        driver = _mock_neo4j_records([])
        expander = GraphExpander(driver)

        expander.bfs_expand(
            ["seed_1"], allowed_edge_types=list(VALID_EDGE_TYPES),
        )

        session = driver.session.return_value.__enter__.return_value
        cypher_query = session.run.call_args[0][0]
        for edge_type in VALID_EDGE_TYPES:
            assert edge_type in cypher_query

    def test_empty_after_filtering_produces_no_edge_filter(self):
        """If all edge types are invalid, query should have no edge filter."""
        driver = _mock_neo4j_records([])
        expander = GraphExpander(driver)

        expander.bfs_expand(
            ["seed_1"], allowed_edge_types=["FAKE_TYPE_A", "FAKE_TYPE_B"],
        )

        session = driver.session.return_value.__enter__.return_value
        cypher_query = session.run.call_args[0][0]
        # The edge_filter should be empty — just the empty string in the query
        assert "FAKE_TYPE_A" not in cypher_query
        assert "FAKE_TYPE_B" not in cypher_query


# ---------------------------------------------------------------------------
# D3 Branching Factor Enforcement Tests
# ---------------------------------------------------------------------------

class TestBranchingFactorEnforcement:
    def test_branching_factor_limits_nodes_per_hop(self):
        """With max_branching=2, no hop level should have more than 2 nodes."""
        records = [
            _make_record("seed_1", hop_depth=0),
            _make_record("h1_a", hop_depth=1),
            _make_record("h1_b", hop_depth=1),
            _make_record("h1_c", hop_depth=1),  # Should be pruned
            _make_record("h1_d", hop_depth=1),  # Should be pruned
            _make_record("h2_a", hop_depth=2),
            _make_record("h2_b", hop_depth=2),
            _make_record("h2_c", hop_depth=2),  # Should be pruned
        ]
        driver = _mock_neo4j_records(records)
        expander = GraphExpander(driver)

        result = expander.bfs_expand(
            ["seed_1"], max_hops=2, max_branching=2, max_total_nodes=100,
        )

        # Count nodes per hop
        from collections import Counter
        hop_counts = Counter(result.node_depths[n.node_id] for n in result.expanded_nodes)
        # Hop 0: 1 seed (under limit)
        assert hop_counts[0] == 1
        # Hop 1: limited to 2
        assert hop_counts[1] == 2
        # Hop 2: limited to 2
        assert hop_counts[2] == 2

    def test_branching_preserves_order(self):
        """Branching pruning should keep the first N nodes per hop."""
        records = [
            _make_record("seed_1", hop_depth=0),
            _make_record("first", hop_depth=1),
            _make_record("second", hop_depth=1),
            _make_record("third", hop_depth=1),
        ]
        driver = _mock_neo4j_records(records)
        expander = GraphExpander(driver)

        result = expander.bfs_expand(
            ["seed_1"], max_branching=2, max_total_nodes=100,
        )

        hop1_ids = [
            n.node_id for n in result.expanded_nodes
            if result.node_depths[n.node_id] == 1
        ]
        assert hop1_ids == ["first", "second"]

    def test_no_pruning_when_under_limit(self):
        """No pruning when all hops are under the branching limit."""
        records = [
            _make_record("seed_1", hop_depth=0),
            _make_record("h1_a", hop_depth=1),
            _make_record("h1_b", hop_depth=1),
            _make_record("h2_a", hop_depth=2),
        ]
        driver = _mock_neo4j_records(records)
        expander = GraphExpander(driver)

        result = expander.bfs_expand(
            ["seed_1"], max_branching=10, max_total_nodes=100,
        )

        assert len(result.expanded_nodes) == 4
