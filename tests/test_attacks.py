"""Tests for attack implementations."""

from __future__ import annotations

from pivorag.attacks.base import InjectionPayload

TARGET_QUERIES = [
    "How is the k8s production cluster configured?",
    "What are the auth-service access controls?",
    "Show me the budget for Project Nexus.",
]


class TestInjectionPayload:
    def test_payload_creation(self):
        payload = InjectionPayload(
            payload_id="atk_001",
            text="Benign-looking text about shared infrastructure.",
            entities=["ent_shared_vendor"],
            target_queries=["What systems does vendor X support?"],
        )
        assert payload.payload_id == "atk_001"
        assert len(payload.entities) == 1

    def test_payload_defaults(self):
        payload = InjectionPayload(payload_id="atk_002", text="test")
        assert payload.entities == []
        assert payload.target_queries == []
        assert payload.metadata == {}


class TestSeedSteeringAttack:
    def test_generate_payloads(self):
        from pivorag.attacks.seed_steering import SeedSteeringAttack

        attack = SeedSteeringAttack(injection_budget=5)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        assert len(payloads) == 5
        assert attack.name == "A1_seed_steering"

        for p in payloads:
            assert p.payload_id.startswith("a1_")
            assert len(p.entities) == 2
            assert len(p.text) > 50
            assert p.metadata["attack"] == "A1_seed_steering"
            assert p.metadata["sensitivity"] == "PUBLIC"

    def test_respects_budget(self):
        from pivorag.attacks.seed_steering import SeedSteeringAttack

        attack = SeedSteeringAttack(injection_budget=3)
        payloads = attack.generate_payloads(TARGET_QUERIES)
        assert len(payloads) == 3

    def test_different_target_paths(self):
        from pivorag.attacks.seed_steering import SeedSteeringAttack

        for path in ["engineering_to_security", "finance_to_security",
                      "engineering_to_hr", "finance_to_hr"]:
            attack = SeedSteeringAttack(injection_budget=2, target_path=path)
            payloads = attack.generate_payloads(TARGET_QUERIES)
            assert len(payloads) == 2
            assert payloads[0].metadata["target_path"] == path


class TestEntityAnchorAttack:
    def test_generate_payloads(self):
        from pivorag.attacks.entity_anchor import EntityAnchorAttack

        attack = EntityAnchorAttack(injection_budget=5)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        assert len(payloads) == 5
        assert attack.name == "A2_entity_anchor"

        for p in payloads:
            assert p.payload_id.startswith("a2_")
            assert len(p.entities) == 3  # primary + 2 related
            assert p.metadata["attack"] == "A2_entity_anchor"

    def test_dense_entity_mentions(self):
        """Each anchor payload should mention the primary entity 3+ times."""
        from pivorag.attacks.entity_anchor import EntityAnchorAttack

        attack = EntityAnchorAttack(injection_budget=3)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        for p in payloads:
            primary = p.metadata["primary_entity"]
            count = p.text.lower().count(primary.lower())
            assert count >= 3, f"Primary entity '{primary}' mentioned only {count} times"

    def test_different_target_areas(self):
        from pivorag.attacks.entity_anchor import EntityAnchorAttack

        for area in ["security_credentials", "financial_data", "hr_records"]:
            attack = EntityAnchorAttack(injection_budget=2, target_area=area)
            payloads = attack.generate_payloads(TARGET_QUERIES)
            assert len(payloads) == 2
            assert payloads[0].metadata["target_area"] == area


class TestNeighborhoodFloodAttack:
    def test_generate_payloads(self):
        from pivorag.attacks.neighborhood_flood import NeighborhoodFloodAttack

        attack = NeighborhoodFloodAttack(injection_budget=10)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        assert len(payloads) == 10
        assert attack.name == "A3_neighborhood_flood"

        for p in payloads:
            assert p.payload_id.startswith("a3_")
            assert len(p.entities) == 3  # target + neighbor + supporting
            assert p.metadata["attack"] == "A3_neighborhood_flood"

    def test_supporting_entities_cycle(self):
        """Supporting entities should cycle through 5 variants."""
        from pivorag.attacks.neighborhood_flood import NeighborhoodFloodAttack

        attack = NeighborhoodFloodAttack(injection_budget=10)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        supporting = [p.entities[2] for p in payloads]
        # Should contain _component_0 through _component_4
        suffixes = {s.split("_component_")[1] for s in supporting if "_component_" in s}
        assert len(suffixes) == 5

    def test_different_neighborhoods(self):
        from pivorag.attacks.neighborhood_flood import NeighborhoodFloodAttack

        for hood in ["security_neighborhood", "finance_neighborhood",
                     "hr_neighborhood"]:
            attack = NeighborhoodFloodAttack(
                injection_budget=3, target_neighborhood=hood,
            )
            payloads = attack.generate_payloads(TARGET_QUERIES)
            assert len(payloads) == 3


class TestBridgeNodeAttack:
    def test_generate_payloads(self):
        from pivorag.attacks.bridge_node import BridgeNodeAttack

        attack = BridgeNodeAttack(injection_budget=5)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        assert len(payloads) == 5
        assert attack.name == "A4_bridge_node"

        for p in payloads:
            assert p.payload_id.startswith("a4_")
            assert len(p.entities) == 2  # one from each side
            assert p.metadata["attack"] == "A4_bridge_node"
            assert "source_tenant" in p.metadata
            assert "target_tenant" in p.metadata
            assert p.metadata["source_tenant"] != p.metadata["target_tenant"]

    def test_cross_tenant_entities(self):
        """Each payload should mention entities from different tenants."""
        from pivorag.attacks.bridge_node import BRIDGE_CONFIGS, BridgeNodeAttack

        attack = BridgeNodeAttack(
            injection_budget=5, bridge_path="engineering_to_security",
        )
        payloads = attack.generate_payloads(TARGET_QUERIES)
        config = BRIDGE_CONFIGS["engineering_to_security"]

        for p in payloads:
            src = p.metadata["source_entity"]
            tgt = p.metadata["target_entity"]
            assert src in config["attacker_entities"]
            assert tgt in config["target_entities"]

    def test_different_bridge_paths(self):
        from pivorag.attacks.bridge_node import BridgeNodeAttack

        for path in ["engineering_to_security", "finance_to_hr",
                     "engineering_to_hr"]:
            attack = BridgeNodeAttack(injection_budget=3, bridge_path=path)
            payloads = attack.generate_payloads(TARGET_QUERIES)
            assert len(payloads) == 3
            assert payloads[0].metadata["bridge_path"] == path

    def test_payload_text_mentions_both_entities(self):
        """Bridge text should mention entities from both sides."""
        from pivorag.attacks.bridge_node import BridgeNodeAttack

        attack = BridgeNodeAttack(injection_budget=5)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        for p in payloads:
            src = p.metadata["source_entity"]
            tgt = p.metadata["target_entity"]
            assert src in p.text, f"Source entity '{src}' not in text"
            assert tgt in p.text, f"Target entity '{tgt}' not in text"
