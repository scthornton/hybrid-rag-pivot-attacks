"""P1: Vector-only RAG pipeline.

Baseline comparison — retrieves chunks via vector similarity only,
with optional auth pre-filtering. No graph expansion.
"""

from __future__ import annotations

import time

from pivorag.config import PipelineConfig, SensitivityTier
from pivorag.pipelines.base import BasePipeline, RetrievalContext
from pivorag.vector.retrieve import VectorRetriever


class VectorOnlyPipeline(BasePipeline):
    """P1: Pure vector retrieval baseline."""

    def __init__(self, config: PipelineConfig, retriever: VectorRetriever) -> None:
        super().__init__(config)
        self.retriever = retriever

    def retrieve(
        self,
        query: str,
        user_id: str,
        user_tenant: str,
        user_clearance: SensitivityTier,
    ) -> RetrievalContext:
        start = time.perf_counter()

        results = self.retriever.retrieve(
            query=query,
            top_k=self.config.vector.top_k,
            user_tenant=user_tenant,
            user_clearance=user_clearance,
            auth_prefilter=self.config.vector.auth_prefilter,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        chunks = [
            {
                "chunk_id": r.chunk_id,
                "text": r.text,
                "score": r.score,
                **r.metadata,
            }
            for r in results
        ]

        return RetrievalContext(
            query=query,
            user_id=user_id,
            user_tenant=user_tenant,
            user_clearance=user_clearance,
            chunks=chunks,
            seed_chunk_ids=[r.chunk_id for r in results],
            latency_ms=elapsed_ms,
            pipeline_variant=self.variant,
        )
