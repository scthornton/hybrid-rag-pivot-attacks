"""Tests for defense implementations."""

from pivorag.config import SensitivityTier
from pivorag.defenses.budgets import BudgetDefense
from pivorag.defenses.edge_allowlist import EdgeAllowlistDefense
from pivorag.defenses.merge_filter import MergeFilterDefense
from pivorag.defenses.per_hop_authz import PerHopAuthzDefense
from pivorag.defenses.trust_weighting import TrustWeightingDefense
from pivorag.graph.schema import GraphNode


class TestPerHopAuthz:
    def test_filters_unauthorized(self, sensitive_node):
        defense = PerHopAuthzDefense(
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
        )
        result = defense.filter([sensitive_node])
        assert len(result) == 0


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
