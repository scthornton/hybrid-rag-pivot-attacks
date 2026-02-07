"""Tests for vector store operations."""

import pytest


class TestEmbeddingModel:
    @pytest.mark.slow
    def test_embed_returns_array(self):
        from pivorag.vector.embed import EmbeddingModel
        model = EmbeddingModel("all-MiniLM-L6-v2")
        result = model.embed("test query")
        assert result.shape[0] > 0

    @pytest.mark.slow
    def test_batch_embed(self):
        from pivorag.vector.embed import EmbeddingModel
        model = EmbeddingModel("all-MiniLM-L6-v2")
        results = model.embed_batch(["query one", "query two"])
        assert results.shape[0] == 2


class TestVectorIndex:
    @pytest.mark.integration
    def test_placeholder(self):
        """Integration test requiring running ChromaDB instance."""
        pytest.skip("Requires ChromaDB server")
