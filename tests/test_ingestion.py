"""Tests for the ingestion pipeline: chunking, entity extraction, sensitivity, relations."""

from pivorag.config import SensitivityTier
from pivorag.ingestion.chunker import TokenChunker
from pivorag.ingestion.relation_extract import RelationExtractor
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


def _make_entity(entity_id: str, text: str) -> dict:
    """Helper to create entity dicts for relation extraction tests."""
    return {"entity_id": entity_id, "text": text}


class TestRelationExtractor:
    def test_depends_on_pattern(self):
        extractor = RelationExtractor()
        entities = [
            _make_entity("ent_api_gateway", "api-gateway"),
            _make_entity("ent_auth_service", "auth-service"),
        ]
        text = "The api-gateway depends on auth-service for token validation."
        relations = extractor.extract_from_chunk(entities, text, "chunk_1")
        assert len(relations) == 1
        assert relations[0].relation_type == "DEPENDS_ON"
        assert relations[0].confidence >= 0.7

    def test_owned_by_pattern(self):
        extractor = RelationExtractor()
        entities = [
            _make_entity("ent_project_nexus", "Project Nexus"),
            _make_entity("ent_maria_chen", "Maria Chen"),
        ]
        text = "Project Nexus is managed by Maria Chen, who oversees the team."
        relations = extractor.extract_from_chunk(entities, text, "chunk_2")
        assert len(relations) == 1
        assert relations[0].relation_type == "OWNED_BY"

    def test_belongs_to_pattern(self):
        extractor = RelationExtractor()
        entities = [
            _make_entity("ent_james", "James Rodriguez"),
            _make_entity("ent_engineering", "Engineering"),
        ]
        text = "James Rodriguez is part of the Engineering department."
        relations = extractor.extract_from_chunk(entities, text, "chunk_3")
        assert len(relations) == 1
        assert relations[0].relation_type == "BELONGS_TO"

    def test_fallback_to_related(self):
        extractor = RelationExtractor()
        entities = [
            _make_entity("ent_alpha", "Alpha"),
            _make_entity("ent_beta", "Beta"),
        ]
        text = "Alpha and Beta were mentioned at the conference."
        relations = extractor.extract_from_chunk(entities, text, "chunk_4")
        assert len(relations) == 1
        assert relations[0].relation_type == "RELATED_TO"
        assert relations[0].confidence < 0.5

    def test_skips_same_entity(self):
        extractor = RelationExtractor()
        entities = [
            _make_entity("ent_same", "SameEntity"),
            _make_entity("ent_same", "SameEntity"),
        ]
        text = "SameEntity appears twice but should not self-relate."
        relations = extractor.extract_from_chunk(entities, text, "chunk_5")
        assert len(relations) == 0

    def test_multiple_pairs(self):
        extractor = RelationExtractor()
        entities = [
            _make_entity("ent_a", "ServiceA"),
            _make_entity("ent_b", "ServiceB"),
            _make_entity("ent_c", "ServiceC"),
        ]
        text = "ServiceA connects to ServiceB which uses ServiceC for caching."
        relations = extractor.extract_from_chunk(entities, text, "chunk_6")
        # 3 entities → 3 pairs: (A,B), (A,C), (B,C)
        assert len(relations) == 3
