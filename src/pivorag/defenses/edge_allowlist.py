"""D2: Edge-Type Allowlisting (Query-Class Aware).

Only traverse edge types explicitly permitted for the query class.
Reduces attack surface by limiting the relationship types that
graph expansion can follow.
"""

from __future__ import annotations

from pivorag.graph.policy import EdgeAllowlist


class EdgeAllowlistDefense:
    """Filter graph expansion to only permitted edge types."""

    def __init__(self, allowlist_config: dict) -> None:
        self.allowlist = EdgeAllowlist(allowlist_config)

    def get_allowed_edges(self, query_class: str = "general") -> list[str]:
        """Return the set of edge types allowed for this query class."""
        return self.allowlist.get_allowed_edges(query_class)

    def classify_query(self, query: str) -> str:
        """Classify a query to determine which edge allowlist to apply.

        Simple keyword-based classification. Can be upgraded to
        an LLM-based or embedding-based classifier.
        """
        query_lower = query.lower()
        if any(kw in query_lower for kw in ["depends", "dependency", "upstream", "downstream"]):
            return "dependency"
        if any(kw in query_lower for kw in ["owner", "responsible", "who manages"]):
            return "ownership"
        return "general"
