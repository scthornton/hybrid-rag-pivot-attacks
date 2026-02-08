"""Tests for adaptive attacker implementations (A5-A7)."""

from __future__ import annotations

TARGET_QUERIES = [
    "What credentials does auth-service use?",
    "Show me Maria Chen's compensation details.",
    "What are CloudCorp's contract terms?",
]


# ---------------------------------------------------------------------------
# A5: Metadata Forgery tests
# ---------------------------------------------------------------------------


class TestMetadataForgeryAttack:
    def test_generate_payloads(self) -> None:
        from pivorag.attacks.metadata_forgery import MetadataForgeryAttack

        attack = MetadataForgeryAttack(injection_budget=5)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        assert len(payloads) == 5
        assert attack.name == "A5_metadata_forgery"

        for p in payloads:
            assert p.payload_id.startswith("a5_")
            assert len(p.entities) == 2
            assert len(p.text) > 50
            assert p.metadata["attack"] == "A5_metadata_forgery"

    def test_full_forgery_uses_target_tenant(self) -> None:
        """With forgery_rate=1.0, ALL payloads get the target tenant."""
        from pivorag.attacks.metadata_forgery import MetadataForgeryAttack

        attack = MetadataForgeryAttack(
            injection_budget=5,
            target_area="security_secrets",
            forgery_rate=1.0,
        )
        payloads = attack.generate_payloads(TARGET_QUERIES)

        for p in payloads:
            assert p.metadata["is_forged"] is True
            assert p.metadata["forged_tenant"] == "umbrella_security"
            assert p.metadata["real_tenant"] == "acme_engineering"
            assert p.metadata["tenant"] == "umbrella_security"

    def test_zero_forgery_uses_real_tenant(self) -> None:
        """With forgery_rate=0.0, NO payloads are forged."""
        from pivorag.attacks.metadata_forgery import MetadataForgeryAttack

        attack = MetadataForgeryAttack(
            injection_budget=5, forgery_rate=0.0,
        )
        payloads = attack.generate_payloads(TARGET_QUERIES)

        for p in payloads:
            assert p.metadata["is_forged"] is False
            assert p.metadata["forged_tenant"] == "acme_engineering"
            assert p.metadata["tenant"] == "acme_engineering"

    def test_partial_forgery_rate(self) -> None:
        """With forgery_rate=0.5, roughly half should be forged."""
        from pivorag.attacks.metadata_forgery import MetadataForgeryAttack

        attack = MetadataForgeryAttack(
            injection_budget=10, forgery_rate=0.5,
        )
        payloads = attack.generate_payloads(TARGET_QUERIES)
        forged = [p for p in payloads if p.metadata["is_forged"]]
        honest = [p for p in payloads if not p.metadata["is_forged"]]

        assert len(forged) == 5
        assert len(honest) == 5

    def test_low_provenance_score(self) -> None:
        """Forged payloads should have low provenance to be caught by D4."""
        from pivorag.attacks.metadata_forgery import MetadataForgeryAttack

        attack = MetadataForgeryAttack(injection_budget=3)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        for p in payloads:
            assert p.metadata["provenance_score"] <= 0.3

    def test_different_target_areas(self) -> None:
        from pivorag.attacks.metadata_forgery import MetadataForgeryAttack

        for area in ["security_secrets", "hr_records", "financial_data"]:
            attack = MetadataForgeryAttack(
                injection_budget=2, target_area=area,
            )
            payloads = attack.generate_payloads(TARGET_QUERIES)
            assert len(payloads) == 2
            assert payloads[0].metadata["target_area"] == area

    def test_respects_budget(self) -> None:
        from pivorag.attacks.metadata_forgery import MetadataForgeryAttack

        attack = MetadataForgeryAttack(injection_budget=3)
        payloads = attack.generate_payloads(TARGET_QUERIES)
        assert len(payloads) == 3


# ---------------------------------------------------------------------------
# A6: Entity Manipulation tests
# ---------------------------------------------------------------------------


class TestEntityManipulationAttack:
    def test_generate_payloads(self) -> None:
        from pivorag.attacks.entity_manipulation import (
            EntityManipulationAttack,
        )

        attack = EntityManipulationAttack(injection_budget=5)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        assert len(payloads) == 5
        assert attack.name == "A6_entity_manipulation"

        for p in payloads:
            assert p.payload_id.startswith("a6_")
            assert len(p.entities) == 2
            assert p.metadata["attack"] == "A6_entity_manipulation"

    def test_uses_target_entity_names(self) -> None:
        """Payloads should mention entities from the target namespace."""
        from pivorag.attacks.entity_manipulation import (
            TARGET_ENTITY_NAMES,
            EntityManipulationAttack,
        )

        attack = EntityManipulationAttack(
            injection_budget=5, target_namespace="security_personnel",
        )
        payloads = attack.generate_payloads(TARGET_QUERIES)

        target_names = TARGET_ENTITY_NAMES["security_personnel"][
            "entity_names"
        ]
        for p in payloads:
            for ent in p.entities:
                assert ent in target_names

    def test_entities_appear_in_text(self) -> None:
        """Each entity should actually appear in the payload text."""
        from pivorag.attacks.entity_manipulation import (
            EntityManipulationAttack,
        )

        attack = EntityManipulationAttack(injection_budget=5)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        for p in payloads:
            for ent in p.entities:
                assert ent in p.text, (
                    f"Entity '{ent}' not in text"
                )

    def test_attacker_tenant_preserved(self) -> None:
        """A6 uses the attacker's real tenant (unlike A5 forgery)."""
        from pivorag.attacks.entity_manipulation import (
            EntityManipulationAttack,
        )

        attack = EntityManipulationAttack(injection_budget=3)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        for p in payloads:
            assert p.metadata["tenant"] == "acme_engineering"

    def test_different_namespaces(self) -> None:
        from pivorag.attacks.entity_manipulation import (
            EntityManipulationAttack,
        )

        for ns in ["security_personnel", "hr_personnel", "finance_vendors"]:
            attack = EntityManipulationAttack(
                injection_budget=2, target_namespace=ns,
            )
            payloads = attack.generate_payloads(TARGET_QUERIES)
            assert len(payloads) == 2
            assert payloads[0].metadata["target_namespace"] == ns

    def test_respects_budget(self) -> None:
        from pivorag.attacks.entity_manipulation import (
            EntityManipulationAttack,
        )

        attack = EntityManipulationAttack(injection_budget=4)
        payloads = attack.generate_payloads(TARGET_QUERIES)
        assert len(payloads) == 4


# ---------------------------------------------------------------------------
# A7: Query Manipulation tests
# ---------------------------------------------------------------------------


class TestQueryManipulationAttack:
    def test_generate_payloads(self) -> None:
        from pivorag.attacks.query_manipulation import (
            QueryManipulationAttack,
        )

        attack = QueryManipulationAttack(injection_budget=5)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        assert len(payloads) == 5
        assert attack.name == "A7_query_manipulation"

        for p in payloads:
            assert p.payload_id.startswith("a7_")
            assert len(p.entities) == 2
            assert p.metadata["attack"] == "A7_query_manipulation"
            assert p.metadata["is_query_attack"] is True

    def test_payloads_are_queries(self) -> None:
        """A7 payloads should contain well-formed questions."""
        from pivorag.attacks.query_manipulation import (
            QueryManipulationAttack,
        )

        attack = QueryManipulationAttack(injection_budget=5)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        for p in payloads:
            assert "?" in p.text, "Crafted query should be a question"
            assert p.metadata["crafted_query"] == p.text

    def test_queries_mention_target_entities(self) -> None:
        """Each crafted query should mention target entity names."""
        from pivorag.attacks.query_manipulation import (
            QUERY_TARGETS,
            QueryManipulationAttack,
        )

        attack = QueryManipulationAttack(
            injection_budget=5, target_recon="security_recon",
        )
        payloads = attack.generate_payloads(TARGET_QUERIES)

        target_entities = QUERY_TARGETS["security_recon"]["entity_mentions"]
        for p in payloads:
            for ent in p.entities:
                assert ent in target_entities
                assert ent in p.text

    def test_inject_is_noop(self) -> None:
        """A7 inject() should not modify vector/graph stores."""
        from pivorag.attacks.query_manipulation import (
            QueryManipulationAttack,
        )

        attack = QueryManipulationAttack(injection_budget=3)
        payloads = attack.generate_payloads(TARGET_QUERIES)

        result = attack.inject(payloads, None, None)

        assert result.payloads_injected == 0
        assert result.total_tokens_injected == 0
        assert result.metadata["is_query_only_attack"] is True
        assert len(result.target_queries) == 3

    def test_different_recon_targets(self) -> None:
        from pivorag.attacks.query_manipulation import (
            QueryManipulationAttack,
        )

        for recon in ["security_recon", "hr_recon", "finance_recon"]:
            attack = QueryManipulationAttack(
                injection_budget=2, target_recon=recon,
            )
            payloads = attack.generate_payloads(TARGET_QUERIES)
            assert len(payloads) == 2
            assert payloads[0].metadata["target_recon"] == recon

    def test_respects_budget(self) -> None:
        from pivorag.attacks.query_manipulation import (
            QueryManipulationAttack,
        )

        attack = QueryManipulationAttack(injection_budget=7)
        payloads = attack.generate_payloads(TARGET_QUERIES)
        assert len(payloads) == 7
