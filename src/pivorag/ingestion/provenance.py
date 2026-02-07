"""Provenance and trust scoring for documents and entities.

Assigns trust scores based on source origin, curation status,
and data quality signals. Used by D4 (trust-weighted expansion).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceType(StrEnum):
    CURATED = "curated"
    INTERNAL_SYSTEM = "internal_system"
    USER_GENERATED = "user_generated"
    LLM_EXTRACTED = "llm_extracted"
    WEB_SCRAPED = "web_scraped"
    EXTERNAL_FEED = "external_feed"


# Default trust scores by source type
DEFAULT_TRUST_SCORES: dict[SourceType, float] = {
    SourceType.CURATED: 1.0,
    SourceType.INTERNAL_SYSTEM: 0.9,
    SourceType.USER_GENERATED: 0.5,
    SourceType.LLM_EXTRACTED: 0.4,
    SourceType.WEB_SCRAPED: 0.3,
    SourceType.EXTERNAL_FEED: 0.6,
}


@dataclass
class ProvenanceRecord:
    source_id: str
    source_type: SourceType
    trust_score: float
    created_at: str
    verified: bool = False
    verifier: str | None = None


class ProvenanceScorer:
    """Calculate trust scores for documents and entities."""

    def __init__(
        self,
        trust_overrides: dict[str, float] | None = None,
    ) -> None:
        self.trust_scores = dict(DEFAULT_TRUST_SCORES)
        if trust_overrides:
            for source_type_str, score in trust_overrides.items():
                self.trust_scores[SourceType(source_type_str)] = score

    def score(self, source_type: SourceType, verified: bool = False) -> float:
        """Return trust score for a given source type."""
        base = self.trust_scores.get(source_type, 0.5)
        if verified:
            base = min(base + 0.1, 1.0)
        return base
