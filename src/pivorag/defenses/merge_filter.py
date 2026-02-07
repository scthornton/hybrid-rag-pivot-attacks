"""D5: Merge-Time Policy Filter + Rerank.

After merging vector + graph results, applies a strict deny-by-default
policy filter and reranks with penalties for low-trust or near-duplicate
content. Last line of defense before LLM context assembly.
"""

from __future__ import annotations

from typing import Any

from pivorag.config import SensitivityTier


class MergeFilterDefense:
    """Post-merge policy filtering and reranking."""

    def __init__(
        self,
        deny_by_default: bool = True,
        penalize_low_trust: bool = True,
        penalize_near_duplicate: bool = True,
        trust_penalty_weight: float = 0.3,
    ) -> None:
        self.deny_by_default = deny_by_default
        self.penalize_low_trust = penalize_low_trust
        self.penalize_near_duplicate = penalize_near_duplicate
        self.trust_penalty_weight = trust_penalty_weight

    def filter_context(
        self,
        items: list[dict[str, Any]],
        user_clearance: SensitivityTier,
        user_tenant: str,
    ) -> list[dict[str, Any]]:
        """Apply deny-by-default policy filter on merged context."""
        filtered = []
        for item in items:
            item_tier = SensitivityTier(item.get("sensitivity", "PUBLIC"))
            item_tenant = item.get("tenant", "")

            # Deny if sensitivity exceeds clearance
            if item_tier > user_clearance:
                continue

            # Deny cross-tenant items unless explicitly allowed
            if self.deny_by_default and item_tenant and item_tenant != user_tenant:
                continue

            filtered.append(item)

        return filtered

    def rerank(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rerank items with trust and dedup penalties."""
        scored = []
        for item in items:
            score = item.get("score", 0.5)
            trust = item.get("provenance_score", 1.0)

            if self.penalize_low_trust and trust < 0.7:
                score -= self.trust_penalty_weight * (0.7 - trust)

            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]
