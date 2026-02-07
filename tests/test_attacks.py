"""Tests for attack implementations."""

import pytest

from pivorag.attacks.base import InjectionPayload


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


class TestAttackInterface:
    def test_seed_steering_not_implemented(self):
        from pivorag.attacks.seed_steering import SeedSteeringAttack
        attack = SeedSteeringAttack(injection_budget=5)
        with pytest.raises(NotImplementedError):
            attack.generate_payloads(["test query"])
