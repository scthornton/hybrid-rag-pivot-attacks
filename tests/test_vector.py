"""Tests for vector store operations."""

from __future__ import annotations

import contextlib

import pytest


class TestEmbeddingModel:
    @pytest.mark.slow
    def test_embed_returns_array(self):
        from pivorag.vector.embed import EmbeddingModel

        model = EmbeddingModel("all-MiniLM-L6-v2")
        result = model.embed("test query")
        assert result.shape[0] == 384  # MiniLM-L6-v2 dimensionality

    @pytest.mark.slow
    def test_batch_embed(self):
        from pivorag.vector.embed import EmbeddingModel

        model = EmbeddingModel("all-MiniLM-L6-v2")
        results = model.embed_batch(["query one", "query two"])
        assert results.shape == (2, 384)

    @pytest.mark.slow
    def test_similar_texts_closer(self):
        """Verify that semantically similar texts produce closer embeddings."""
        import numpy as np

        from pivorag.vector.embed import EmbeddingModel

        model = EmbeddingModel("all-MiniLM-L6-v2")
        emb_a = model.embed("kubernetes cluster deployment")
        emb_b = model.embed("k8s container orchestration")
        emb_c = model.embed("salary compensation package")

        # Cosine similarity: a-b should be higher than a-c
        sim_ab = float(np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b)))
        sim_ac = float(np.dot(emb_a, emb_c) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_c)))
        assert sim_ab > sim_ac


def _chromadb_available() -> bool:
    """Check if local ChromaDB is reachable."""
    try:
        import chromadb
        from chromadb.config import Settings

        client = chromadb.HttpClient(
            host="localhost", port=8000,
            settings=Settings(anonymized_telemetry=False),
        )
        client.heartbeat()
        return True
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not _chromadb_available(), reason="ChromaDB not running on localhost:8000")
class TestVectorIndex:
    def test_add_and_count(self):
        from pivorag.vector.embed import EmbeddingModel
        from pivorag.vector.index import VectorIndex

        model = EmbeddingModel("all-MiniLM-L6-v2")
        index = VectorIndex(
            host="localhost", port=8000,
            collection_name="test_pivorag_integration",
        )

        # Clean slate
        with contextlib.suppress(Exception):
            index.reset()

        emb = model.embed("Test document about infrastructure.").tolist()
        index.add_chunks(
            ids=["test_001"],
            embeddings=[emb],
            documents=["Test document about infrastructure."],
            metadatas=[{
                "tenant": "acme_engineering",
                "sensitivity": "PUBLIC",
                "doc_id": "doc_test",
            }],
        )
        assert index.count() == 1

        # Cleanup
        index.reset()

    def test_retrieval_with_auth_filter(self):
        from pivorag.config import SensitivityTier
        from pivorag.vector.embed import EmbeddingModel
        from pivorag.vector.index import VectorIndex
        from pivorag.vector.retrieve import VectorRetriever

        model = EmbeddingModel("all-MiniLM-L6-v2")
        index = VectorIndex(
            host="localhost", port=8000,
            collection_name="test_pivorag_auth",
        )

        with contextlib.suppress(Exception):
            index.reset()

        # Insert one PUBLIC chunk and one RESTRICTED chunk
        texts = [
            "Public documentation about the api-gateway configuration.",
            "Restricted admin credentials for production vault access.",
        ]
        for i, (text, tier) in enumerate(zip(
            texts, ["PUBLIC", "RESTRICTED"], strict=True,
        )):
            emb = model.embed(text).tolist()
            index.add_chunks(
                ids=[f"auth_test_{i}"],
                embeddings=[emb],
                documents=[text],
                metadatas=[{
                    "tenant": "acme_engineering",
                    "sensitivity": tier,
                    "doc_id": f"doc_auth_{i}",
                }],
            )

        retriever = VectorRetriever(index=index, embedding_model=model)

        # PUBLIC user should only see PUBLIC chunks
        results = retriever.retrieve(
            query="api gateway config",
            top_k=10,
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.PUBLIC,
        )
        assert all(r.metadata["sensitivity"] == "PUBLIC" for r in results)

        # Cleanup
        index.reset()
