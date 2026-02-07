"""Relation extraction between entities for graph edge construction.

Uses lexical patterns on the text between entity mentions to infer
typed relationships (DEPENDS_ON, OWNED_BY, BELONGS_TO, etc.).
Falls back to co-occurrence RELATED_TO when no pattern matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ExtractedRelation:
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    evidence_text: str
    source_chunk_id: str
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


# Pattern-based relation detection.
# Each entry: (compiled regex on the text between two entity mentions,
#              relation_type if source→target matches,
#              confidence score)
# Patterns are tested on the text *between* the two entity mentions.
_RELATION_PATTERNS: list[tuple[re.Pattern, str, float]] = [
    # DEPENDS_ON: A depends on / relies on / requires / uses B
    (re.compile(
        r"(?:depends?\s+on|relies?\s+on|requires?|integrat\w+\s+with|"
        r"connects?\s+to|uses?|built\s+on|running\s+on|"
        r"communicat\w+\s+with|calls?|consumes?)",
        re.IGNORECASE,
    ), "DEPENDS_ON", 0.75),

    # OWNED_BY: A is owned by / managed by / maintained by / assigned to B
    (re.compile(
        r"(?:owned\s+by|managed\s+by|maintained\s+by|administered\s+by|"
        r"assigned\s+to|led\s+by|authored\s+by|reported\s+by|"
        r"created\s+by|responsible\s+for|point\s+of\s+contact|"
        r"team\s+lead|approved\s+by|reviewed\s+by)",
        re.IGNORECASE,
    ), "OWNED_BY", 0.75),

    # BELONGS_TO: A belongs to / part of / member of / within B
    (re.compile(
        r"(?:belongs?\s+to|part\s+of|member\s+of|within|"
        r"component\s+of|submodule\s+of|housed\s+in|"
        r"located\s+in|department|division|team\s+in|works?\s+in)",
        re.IGNORECASE,
    ), "BELONGS_TO", 0.70),

    # CONTAINS: A contains / includes / has / consists of B
    (re.compile(
        r"(?:contains?|includes?|consists?\s+of|comprises?|"
        r"encompasses|houses?|stores?|holds?|embeds?)",
        re.IGNORECASE,
    ), "CONTAINS", 0.70),

    # DERIVED_FROM: A derived from / based on / forked from / extracted from B
    (re.compile(
        r"(?:derived\s+from|based\s+on|forked\s+from|extracted\s+from|"
        r"evolved\s+from|migrated\s+from|converted\s+from|"
        r"cloned\s+from|inherited\s+from|adapted\s+from)",
        re.IGNORECASE,
    ), "DERIVED_FROM", 0.70),
]


class RelationExtractor:
    """Extract typed relations between entities using lexical patterns.

    Strategy:
    1. For each pair of entities in a chunk, find their positions in the text
    2. Extract the text between the two mentions
    3. Test lexical patterns against that inter-entity text
    4. Return the first matching relation type (patterns ordered by priority)
    5. Fall back to RELATED_TO at low confidence if no pattern matches
    """

    def __init__(self, co_occurrence_window: int = 3) -> None:
        self.co_occurrence_window = co_occurrence_window

    def _find_entity_span(
        self, text: str, entity_text: str,
    ) -> tuple[int, int] | None:
        """Find the first occurrence of entity_text in text (case-insensitive)."""
        idx = text.lower().find(entity_text.lower())
        if idx == -1:
            return None
        return (idx, idx + len(entity_text))

    def _classify_relation(
        self, between_text: str,
    ) -> tuple[str, float]:
        """Classify the relation type from text between two entity mentions."""
        for pattern, rel_type, confidence in _RELATION_PATTERNS:
            if pattern.search(between_text):
                return rel_type, confidence
        return "RELATED_TO", 0.4

    def extract_from_chunk(
        self,
        entities: list,
        chunk_text: str,
        chunk_id: str,
    ) -> list[ExtractedRelation]:
        """Extract typed relations from entity pairs in a chunk.

        For each entity pair, locates both mentions in the text,
        extracts the text between them, and applies pattern matching
        to determine the relation type. Falls back to RELATED_TO
        with low confidence for co-occurring entities with no
        identifiable lexical pattern.
        """
        relations = []
        for i, ent_a in enumerate(entities):
            for ent_b in entities[i + 1:]:
                a_id = getattr(ent_a, "entity_id", None) or ent_a.get("entity_id", "")
                b_id = getattr(ent_b, "entity_id", None) or ent_b.get("entity_id", "")

                if a_id == b_id:
                    continue

                # Get entity text for span lookup
                a_text = getattr(ent_a, "text", None) or ent_a.get("text", "")
                b_text = getattr(ent_b, "text", None) or ent_b.get("text", "")

                # Find spans in the chunk text
                a_span = self._find_entity_span(chunk_text, a_text) if a_text else None
                b_span = self._find_entity_span(chunk_text, b_text) if b_text else None

                if a_span and b_span:
                    # Extract text between the two entity mentions
                    start = min(a_span[1], b_span[1])
                    end = max(a_span[0], b_span[0])
                    if end > start:
                        between = chunk_text[start:end].strip()
                        rel_type, confidence = self._classify_relation(between)
                    else:
                        # Entities overlap or adjacent — use surrounding context
                        context_start = max(0, min(a_span[0], b_span[0]) - 50)
                        context_end = min(len(chunk_text), max(a_span[1], b_span[1]) + 50)
                        context = chunk_text[context_start:context_end]
                        rel_type, confidence = self._classify_relation(context)
                else:
                    # Can't find spans — fall back to full-text pattern matching
                    rel_type, confidence = self._classify_relation(chunk_text[:300])

                relations.append(ExtractedRelation(
                    source_entity_id=a_id,
                    target_entity_id=b_id,
                    relation_type=rel_type,
                    evidence_text=chunk_text[:200],
                    source_chunk_id=chunk_id,
                    confidence=confidence,
                    metadata={"method": "pattern" if confidence > 0.5 else "co_occurrence"},
                ))
        return relations
