"""Named Entity Recognition for graph node extraction.

Extracts entities from text chunks using spaCy NER,
then normalizes and deduplicates entity references.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedEntity:
    entity_id: str
    text: str
    entity_type: str
    canonical_name: str
    source_chunk_id: str
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


class EntityExtractor:
    """Extract named entities from text chunks using spaCy."""

    def __init__(self, model_name: str = "en_core_web_sm") -> None:
        self.model_name = model_name
        self._nlp = None

    @property
    def nlp(self):
        if self._nlp is None:
            import spacy
            self._nlp = spacy.load(self.model_name)
        return self._nlp

    def extract(self, text: str, chunk_id: str) -> list[ExtractedEntity]:
        """Extract entities from a single text chunk."""
        doc = self.nlp(text)
        entities = []
        for ent in doc.ents:
            canonical = ent.text.strip().lower().replace(" ", "_")
            entities.append(ExtractedEntity(
                entity_id=f"ent_{canonical}_{ent.label_}",
                text=ent.text,
                entity_type=ent.label_,
                canonical_name=canonical,
                source_chunk_id=chunk_id,
                confidence=1.0,
            ))
        return entities

    def extract_batch(
        self, texts: list[tuple[str, str]]
    ) -> list[list[ExtractedEntity]]:
        """Extract entities from multiple (text, chunk_id) pairs."""
        return [self.extract(text, cid) for text, cid in texts]
