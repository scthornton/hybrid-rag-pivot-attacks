"""Benchmark runner: executes queries across pipeline variants and collects metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from pivorag.config import SensitivityTier
from pivorag.eval.metrics import (
    SecurityMetrics,
    amplification_factor,
    amplification_factor_epsilon,
    delta_leakage,
    leakage_at_k,
    pivot_depth,
    pivot_depth_distribution,
    retrieval_pivot_risk,
    severity_weighted_leakage,
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


def bootstrap_ci(
    values: list[float],
    n_boot: int = 10000,
    alpha: float = 0.05,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Compute bootstrap confidence interval using the percentile method.

    Returns (mean, ci_low, ci_high) where ci_low/ci_high are the
    alpha/2 and 1-alpha/2 percentiles of the bootstrap distribution.
    """
    if not values:
        return (0.0, 0.0, 0.0)

    rng = np.random.default_rng(seed)
    arr = np.array(values, dtype=np.float64)
    n = len(arr)

    boot_means = np.empty(n_boot)
    for i in range(n_boot):
        sample = rng.choice(arr, size=n, replace=True)
        boot_means[i] = np.mean(sample)

    ci_low = float(np.percentile(boot_means, 100 * alpha / 2))
    ci_high = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    return (float(np.mean(arr)), ci_low, ci_high)


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
        compute_bootstrap: bool = False,
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
        leakages = [leakage_at_k(ctx) for ctx in contexts]
        mean_leak = sum(leakages) / max(len(contexts), 1)
        af = 1.0
        af_eps = 0.0
        d_leak = 0.0
        if vector_baseline_contexts:
            af = amplification_factor(contexts, vector_baseline_contexts)
            af_eps = amplification_factor_epsilon(contexts, vector_baseline_contexts)
            d_leak = delta_leakage(contexts, vector_baseline_contexts)
        queries_with_leak = sum(1 for leak in leakages if leak > 0)

        # Mean PD only over queries that have leakage (inf values excluded)
        pd_values = [pivot_depth(ctx) for ctx in contexts if leakage_at_k(ctx) > 0]
        mean_pd = sum(pd_values) / len(pd_values) if pd_values else float("inf")

        # Extended metrics
        mean_sev = sum(
            severity_weighted_leakage(ctx) for ctx in contexts
        ) / max(len(contexts), 1)
        pd_dist = pivot_depth_distribution(contexts)

        # Bootstrap CIs (optional — expensive for large query sets)
        rpr_ci = None
        leakage_ci = None
        if compute_bootstrap:
            rpr_indicators = [1.0 if leak > 0 else 0.0 for leak in leakages]
            rpr_ci = bootstrap_ci(rpr_indicators)
            leakage_ci = bootstrap_ci([float(x) for x in leakages])

        security = SecurityMetrics(
            rpr=rpr,
            mean_leakage=mean_leak,
            amplification_factor=af,
            mean_pivot_depth=mean_pd if mean_pd != float("inf") else -1,
            total_queries=len(contexts),
            queries_with_leakage=queries_with_leak,
            mean_severity_weighted_leakage=mean_sev,
            af_epsilon=af_eps,
            delta_leak=d_leak,
            pd_distribution=pd_dist,
            rpr_ci=rpr_ci,
            leakage_ci=leakage_ci,
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
