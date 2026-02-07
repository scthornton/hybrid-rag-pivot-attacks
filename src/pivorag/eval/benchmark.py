"""Benchmark runner: executes queries across pipeline variants and collects metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pivorag.config import SensitivityTier
from pivorag.eval.metrics import (
    SecurityMetrics,
    amplification_factor,
    leakage_at_k,
    pivot_depth,
    retrieval_pivot_risk,
)
from pivorag.eval.utility import UtilityMetrics, latency_percentiles
from pivorag.pipelines.base import BasePipeline, RetrievalContext


@dataclass
class BenchmarkQuery:
    query: str
    query_type: str  # benign | adversarial | attack_assisted
    expected_answer: str | None = None
    user_id: str = "eval_user"
    user_tenant: str = "acme_engineering"
    user_clearance: str = "INTERNAL"


@dataclass
class BenchmarkResult:
    pipeline_variant: str
    security: SecurityMetrics
    utility: UtilityMetrics
    raw_contexts: list[RetrievalContext] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BenchmarkRunner:
    """Run benchmark queries across pipeline variants and collect metrics."""

    def __init__(self, output_dir: str | Path = "results") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        pipeline: BasePipeline,
        queries: list[BenchmarkQuery],
        vector_baseline_contexts: list[RetrievalContext] | None = None,
    ) -> BenchmarkResult:
        """Execute all queries through a pipeline and compute metrics."""
        contexts = []
        for q in queries:
            ctx = pipeline.retrieve(
                query=q.query,
                user_id=q.user_id,
                user_tenant=q.user_tenant,
                user_clearance=SensitivityTier(q.user_clearance),
            )
            contexts.append(ctx)

        # Security metrics
        rpr = retrieval_pivot_risk(contexts)
        mean_leak = sum(leakage_at_k(ctx) for ctx in contexts) / max(len(contexts), 1)
        af = 1.0
        if vector_baseline_contexts:
            af = amplification_factor(contexts, vector_baseline_contexts)
        queries_with_leak = sum(1 for ctx in contexts if leakage_at_k(ctx) > 0)
        # Mean PD only over queries that have leakage (inf values excluded)
        pd_values = [pivot_depth(ctx) for ctx in contexts if leakage_at_k(ctx) > 0]
        mean_pd = sum(pd_values) / len(pd_values) if pd_values else float("inf")

        security = SecurityMetrics(
            rpr=rpr,
            mean_leakage=mean_leak,
            amplification_factor=af,
            mean_pivot_depth=mean_pd if mean_pd != float("inf") else -1,
            total_queries=len(contexts),
            queries_with_leakage=queries_with_leak,
        )

        # Utility metrics
        latencies = [ctx.latency_ms for ctx in contexts]
        p50, p95 = latency_percentiles(latencies)
        mean_ctx_size = sum(
            len(ctx.chunks) + len(ctx.graph_nodes) for ctx in contexts
        ) / max(len(contexts), 1)

        utility = UtilityMetrics(
            accuracy=0.0,  # Requires ground truth answers
            citation_support_rate=0.0,  # Requires answer generation
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            mean_context_size=mean_ctx_size,
            total_queries=len(contexts),
        )

        return BenchmarkResult(
            pipeline_variant=pipeline.variant,
            security=security,
            utility=utility,
            raw_contexts=contexts,
        )

    def save_results(self, result: BenchmarkResult, label: str = "") -> Path:
        """Save benchmark results to JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{result.pipeline_variant}_{label}_{timestamp}.json"
        path = self.output_dir / "tables" / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "pipeline_variant": result.pipeline_variant,
            "security": result.security.to_dict(),
            "utility": result.utility.to_dict(),
            "timestamp": timestamp,
        }
        path.write_text(json.dumps(data, indent=2))
        return path
