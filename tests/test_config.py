"""Tests for SensitivityTier comparison operator completeness.

Verifies that all four comparison operators (__lt__, __le__, __ge__, __gt__)
use numeric level ordering, NOT StrEnum's default alphabetical ordering.
"""

import pytest

from pivorag.config import SensitivityTier

# All 4 tiers in ascending order
TIERS = [
    SensitivityTier.PUBLIC,
    SensitivityTier.INTERNAL,
    SensitivityTier.CONFIDENTIAL,
    SensitivityTier.RESTRICTED,
]


class TestSensitivityTierOrdering:
    """Verify numeric ordering across all tier-pair combinations."""

    @pytest.mark.parametrize("tier", TIERS)
    def test_equal_to_self(self, tier):
        assert tier >= tier
        assert tier <= tier
        assert not (tier > tier)
        assert not (tier < tier)

    @pytest.mark.parametrize("lower,higher", [
        (SensitivityTier.PUBLIC, SensitivityTier.INTERNAL),
        (SensitivityTier.PUBLIC, SensitivityTier.CONFIDENTIAL),
        (SensitivityTier.PUBLIC, SensitivityTier.RESTRICTED),
        (SensitivityTier.INTERNAL, SensitivityTier.CONFIDENTIAL),
        (SensitivityTier.INTERNAL, SensitivityTier.RESTRICTED),
        (SensitivityTier.CONFIDENTIAL, SensitivityTier.RESTRICTED),
    ])
    def test_lt_correct(self, lower, higher):
        assert lower < higher
        assert not (higher < lower)

    @pytest.mark.parametrize("lower,higher", [
        (SensitivityTier.PUBLIC, SensitivityTier.INTERNAL),
        (SensitivityTier.PUBLIC, SensitivityTier.CONFIDENTIAL),
        (SensitivityTier.PUBLIC, SensitivityTier.RESTRICTED),
        (SensitivityTier.INTERNAL, SensitivityTier.CONFIDENTIAL),
        (SensitivityTier.INTERNAL, SensitivityTier.RESTRICTED),
        (SensitivityTier.CONFIDENTIAL, SensitivityTier.RESTRICTED),
    ])
    def test_le_correct(self, lower, higher):
        assert lower <= higher
        assert not (higher <= lower)

    @pytest.mark.parametrize("lower,higher", [
        (SensitivityTier.PUBLIC, SensitivityTier.INTERNAL),
        (SensitivityTier.PUBLIC, SensitivityTier.CONFIDENTIAL),
        (SensitivityTier.PUBLIC, SensitivityTier.RESTRICTED),
        (SensitivityTier.INTERNAL, SensitivityTier.CONFIDENTIAL),
        (SensitivityTier.INTERNAL, SensitivityTier.RESTRICTED),
        (SensitivityTier.CONFIDENTIAL, SensitivityTier.RESTRICTED),
    ])
    def test_gt_correct(self, lower, higher):
        assert higher > lower
        assert not (lower > higher)

    @pytest.mark.parametrize("lower,higher", [
        (SensitivityTier.PUBLIC, SensitivityTier.INTERNAL),
        (SensitivityTier.PUBLIC, SensitivityTier.CONFIDENTIAL),
        (SensitivityTier.PUBLIC, SensitivityTier.RESTRICTED),
        (SensitivityTier.INTERNAL, SensitivityTier.CONFIDENTIAL),
        (SensitivityTier.INTERNAL, SensitivityTier.RESTRICTED),
        (SensitivityTier.CONFIDENTIAL, SensitivityTier.RESTRICTED),
    ])
    def test_ge_correct(self, lower, higher):
        assert higher >= lower
        assert not (lower >= higher)


class TestSensitivityTierNotAlphabetical:
    """Explicit regression tests proving ordering is NOT alphabetical.

    Alphabetically: CONFIDENTIAL < INTERNAL < PUBLIC < RESTRICTED.
    By level:       PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED.
    These tests catch any regression to default StrEnum __le__/__lt__.
    """

    def test_public_less_than_internal(self):
        """Alphabetically P > I, but PUBLIC is lower-level than INTERNAL."""
        assert SensitivityTier.PUBLIC < SensitivityTier.INTERNAL
        assert SensitivityTier.PUBLIC <= SensitivityTier.INTERNAL

    def test_public_less_than_confidential(self):
        """Alphabetically P > C, but PUBLIC is lower-level than CONFIDENTIAL."""
        assert SensitivityTier.PUBLIC < SensitivityTier.CONFIDENTIAL
        assert SensitivityTier.PUBLIC <= SensitivityTier.CONFIDENTIAL

    def test_internal_less_than_restricted(self):
        assert SensitivityTier.INTERNAL < SensitivityTier.RESTRICTED

    def test_le_consistent_with_ge(self):
        """For every pair, (a <= b) should equal (b >= a)."""
        for a in TIERS:
            for b in TIERS:
                assert (a <= b) == (b >= a), f"Inconsistent: {a} <= {b} vs {b} >= {a}"

    def test_lt_consistent_with_gt(self):
        """For every pair, (a < b) should equal (b > a)."""
        for a in TIERS:
            for b in TIERS:
                assert (a < b) == (b > a), f"Inconsistent: {a} < {b} vs {b} > {a}"
