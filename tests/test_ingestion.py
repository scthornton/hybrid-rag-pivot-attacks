"""Tests for the ingestion pipeline: chunking, entity extraction, sensitivity."""

from pivorag.config import SensitivityTier
from pivorag.ingestion.chunker import TokenChunker
from pivorag.ingestion.sensitivity import SensitivityLabeler


class TestTokenChunker:
    def test_chunk_short_document(self, sample_document):
        chunker = TokenChunker(target_size=50, overlap=10)
        chunks = chunker.chunk_document(sample_document)
        assert len(chunks) >= 1
        assert all(c.doc_id == "doc_001" for c in chunks)
        assert all(c.tenant == "acme_engineering" for c in chunks)

    def test_chunk_ids_are_unique(self, sample_document):
        chunker = TokenChunker(target_size=20, overlap=5)
        chunks = chunker.chunk_document(sample_document)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))


class TestSensitivityLabeler:
    def test_detects_restricted_keywords(self):
        labeler = SensitivityLabeler()
        assert labeler.label("The password is stored in vault") == SensitivityTier.RESTRICTED

    def test_detects_confidential_keywords(self):
        labeler = SensitivityLabeler()
        assert labeler.label("M&A target acquisition details") == SensitivityTier.CONFIDENTIAL

    def test_defaults_to_public(self):
        labeler = SensitivityLabeler()
        assert labeler.label("The weather is nice today") == SensitivityTier.PUBLIC

    def test_metadata_override(self):
        labeler = SensitivityLabeler()
        assert labeler.label("Anything", metadata_tier="RESTRICTED") == SensitivityTier.RESTRICTED
