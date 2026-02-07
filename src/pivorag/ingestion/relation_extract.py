"""Relation extraction between entities for graph edge construction.

Uses co-occurrence and syntactic patterns to identify relationships
between extracted entities within and across chunks.
"""

from __future__ import annotations

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


class RelationExtractor:
    """Extract relations between entities using co-occurrence and patterns."""

    def __init__(self, co_occurrence_window: int = 3) -> None:
        self.co_occurrence_window = co_occurrence_window

    def extract_from_chunk(
        self,
        entities: list,
        chunk_text: str,
        chunk_id: str,
    ) -> list[ExtractedRelation]:
        """Extract relations from entities co-occurring in a chunk.

        Uses sentence-level co-occurrence as a proxy for relatedness.
        More sophisticated extraction (dependency parsing, LLM-based)
        can be added as method variants.
        """
        relations = []
        for i, ent_a in enumerate(entities):
            for ent_b in entities[i + 1:]:
                if ent_a.entity_id == ent_b.entity_id:
                    continue
                relations.append(ExtractedRelation(
                    source_entity_id=ent_a.entity_id,
                    target_entity_id=ent_b.entity_id,
                    relation_type="RELATED_TO",
                    evidence_text=chunk_text[:200],
                    source_chunk_id=chunk_id,
                    confidence=0.5,
                ))
        return relations
