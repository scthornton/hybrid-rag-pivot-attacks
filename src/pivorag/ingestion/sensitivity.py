"""Sensitivity tier labeling for documents and chunks.

Assigns sensitivity tiers (PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED)
based on content patterns and metadata.
"""

from __future__ import annotations

import re

from pivorag.config import SensitivityTier

# Keywords that signal higher sensitivity (for synthetic data generation)
SENSITIVITY_PATTERNS: dict[SensitivityTier, list[str]] = {
    SensitivityTier.RESTRICTED: [
        r"\bpassword\b", r"\bcredential\b", r"\bsecret\b", r"\bapi[_\s]?key\b",
        r"\bssn\b", r"\bsocial\s+security\b", r"\bsalary\b", r"\bcompensation\b",
    ],
    SensitivityTier.CONFIDENTIAL: [
        r"\bm&a\b", r"\bacquisition\b", r"\bbudget\b", r"\bcontract\s+value\b",
        r"\bnda\b", r"\bproprietary\b", r"\btrade\s+secret\b",
    ],
    SensitivityTier.INTERNAL: [
        r"\binternal\b", r"\brunbook\b", r"\barchitecture\b", r"\bplaybook\b",
    ],
}


class SensitivityLabeler:
    """Assign sensitivity tiers to documents and chunks."""

    def __init__(self, custom_patterns: dict | None = None) -> None:
        self.patterns = dict(SENSITIVITY_PATTERNS)
        if custom_patterns:
            for tier_str, pats in custom_patterns.items():
                tier = SensitivityTier(tier_str)
                self.patterns.setdefault(tier, []).extend(pats)

    def label(self, text: str, metadata_tier: str | None = None) -> SensitivityTier:
        """Determine sensitivity tier from text content and/or metadata."""
        if metadata_tier:
            return SensitivityTier(metadata_tier)

        text_lower = text.lower()
        for tier in [
            SensitivityTier.RESTRICTED,
            SensitivityTier.CONFIDENTIAL,
            SensitivityTier.INTERNAL,
        ]:
            for pattern in self.patterns.get(tier, []):
                if re.search(pattern, text_lower):
                    return tier
        return SensitivityTier.PUBLIC
