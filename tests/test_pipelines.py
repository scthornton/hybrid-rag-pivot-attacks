"""Tests for pipeline implementations.

Integration tests require running ChromaDB and Neo4j services.
Start with: docker compose up -d
"""

from __future__ import annotations

import contextlib

import pytest


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
class TestVectorOnlyPipeline:
    """P1 pipeline integration tests against local ChromaDB."""

    def test_retrieval_returns_context(self):
        from pivorag.config import PipelineConfig, SensitivityTier
        from pivorag.pipelines.vector_only import VectorOnlyPipeline
        from pivorag.vector.embed import EmbeddingModel
        from pivorag.vector.index import VectorIndex
        from pivorag.vector.retrieve import VectorRetriever

        model = EmbeddingModel("all-MiniLM-L6-v2")
        index = VectorIndex(
            host="localhost", port=8000,
            collection_name="test_pipeline_p1",
        )

        with contextlib.suppress(Exception):
            index.reset()

        # Seed with test data
        docs = [
            ("The k8s-prod-cluster runs on Kubernetes 1.28.", "acme_engineering", "PUBLIC"),
            ("Budget for Q4 2025 approved at $2.3M.", "globex_finance", "INTERNAL"),
            ("Admin credentials rotated on 2025-09-15.", "umbrella_security", "RESTRICTED"),
        ]
        for i, (text, tenant, tier) in enumerate(docs):
            emb = model.embed(text).tolist()
            index.add_chunks(
                ids=[f"p1_test_{i}"],
                embeddings=[emb],
                documents=[text],
                metadatas=[{
                    "tenant": tenant,
                    "sensitivity": tier,
                    "doc_id": f"doc_p1_{i}",
                }],
            )

        retriever = VectorRetriever(index=index, embedding_model=model)
        config = PipelineConfig(name="test_p1", variant="P1")
        pipeline = VectorOnlyPipeline(config=config, retriever=retriever)

        ctx = pipeline.retrieve(
            query="kubernetes cluster configuration",
            user_id="user_001",
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.PUBLIC,
        )

        assert ctx.query == "kubernetes cluster configuration"
        assert ctx.pipeline_variant == "P1"
        assert len(ctx.chunks) >= 1
        # Auth prefilter should exclude RESTRICTED and other tenants
        for chunk in ctx.chunks:
            assert chunk["sensitivity"] == "PUBLIC"
            assert chunk["tenant"] == "acme_engineering"

        index.reset()

    def test_no_cross_tenant_leakage(self):
        from pivorag.config import PipelineConfig, SensitivityTier
        from pivorag.pipelines.vector_only import VectorOnlyPipeline
        from pivorag.vector.embed import EmbeddingModel
        from pivorag.vector.index import VectorIndex
        from pivorag.vector.retrieve import VectorRetriever

        model = EmbeddingModel("all-MiniLM-L6-v2")
        index = VectorIndex(
            host="localhost", port=8000,
            collection_name="test_pipeline_p1_leak",
        )

        with contextlib.suppress(Exception):
            index.reset()

        # Insert docs from different tenants about similar topics
        texts = [
            ("Salary data for engineering team: $120K-$180K.", "acme_engineering", "CONFIDENTIAL"),
            ("Salary data for finance team: $100K-$150K.", "globex_finance", "CONFIDENTIAL"),
        ]
        for i, (text, tenant, tier) in enumerate(texts):
            emb = model.embed(text).tolist()
            index.add_chunks(
                ids=[f"leak_test_{i}"],
                embeddings=[emb],
                documents=[text],
                metadatas=[{
                    "tenant": tenant,
                    "sensitivity": tier,
                    "doc_id": f"doc_leak_{i}",
                }],
            )

        retriever = VectorRetriever(index=index, embedding_model=model)
        config = PipelineConfig(name="test_p1_leak", variant="P1")
        pipeline = VectorOnlyPipeline(config=config, retriever=retriever)

        # Finance user should NOT see engineering salary data
        ctx = pipeline.retrieve(
            query="salary data",
            user_id="user_fin",
            user_tenant="globex_finance",
            user_clearance=SensitivityTier.CONFIDENTIAL,
        )

        for chunk in ctx.chunks:
            assert chunk["tenant"] == "globex_finance"

        index.reset()


@pytest.mark.integration
@pytest.mark.skipif(not _chromadb_available(), reason="Requires ChromaDB + Neo4j")
class TestHybridPipeline:
    """P3 hybrid pipeline tests — currently skipped until Neo4j Docker is also available."""

    def test_placeholder(self):
        pytest.skip("Requires ChromaDB + Neo4j + populated indexes")
