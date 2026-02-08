#!/usr/bin/env python3
"""Run baseline and defense-ablation experiments against live services.

Executes queries through pipeline variants P1 (vector-only) and P3-P8 (hybrid),
measures security metrics (RPR, Leakage@k, AF, PD), and saves results.

Usage:
    # Baseline comparison (P1 vs P3)
    python scripts/run_experiments.py --baseline

    # Full ablation (P1 vs P3 vs P4-P8)
    python scripts/run_experiments.py --full

    # Run against Enron dataset
    python scripts/run_experiments.py --baseline --dataset enron

    # Adversarial queries only
    python scripts/run_experiments.py --baseline --queries adversarial

    # Custom connection settings
    python scripts/run_experiments.py --baseline \
        --chroma-host localhost --chroma-port 8000 \
        --neo4j-uri bolt://localhost:7687 --neo4j-user neo4j --neo4j-pass secret
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import click

from pivorag.config import (
    DefenseConfig,
    GraphConfig,
    PipelineConfig,
    SensitivityTier,
    VectorConfig,
)
from pivorag.eval.benchmark import BenchmarkQuery, BenchmarkRunner
from pivorag.eval.metrics import (
    amplification_factor,
    amplification_factor_epsilon,
    delta_leakage,
    leakage_at_k,
    pivot_depth,
    pivot_depth_distribution,
    severity_weighted_leakage,
)
from pivorag.pipelines.base import RetrievalContext

# ── Pipeline factory ─────────────────────────────────────────────

def _make_vector_config() -> VectorConfig:
    return VectorConfig(
        model="all-MiniLM-L6-v2",
        top_k=10,
        auth_prefilter=True,
    )


def _make_graph_config(max_hops: int = 3, max_total: int = 100) -> GraphConfig:
    return GraphConfig(
        enabled=True,
        max_hops=max_hops,
        max_branching_factor=15,
        max_total_nodes=max_total,
        edge_types=[
            "CONTAINS", "MENTIONS", "BELONGS_TO",
            "DEPENDS_ON", "OWNED_BY", "DERIVED_FROM", "RELATED_TO",
        ],
    )


PIPELINE_DEFS: dict[str, dict[str, Any]] = {
    "P1": {
        "name": "vector_only",
        "graph_enabled": False,
        "defenses": {},
    },
    "P3": {
        "name": "hybrid_baseline",
        "graph_enabled": True,
        "defenses": {},
        "description": "Hybrid, no defenses",
    },
    "P4": {
        "name": "hybrid_d1",
        "graph_enabled": True,
        "defenses": {
            "per_hop_authz": {
                "enabled": True,
                "deny_cross_tenant": True,
                "deny_sensitivity_escalation": True,
            },
        },
        "description": "D1: Per-hop AuthZ",
    },
    "P5": {
        "name": "hybrid_d1d2",
        "graph_enabled": True,
        "defenses": {
            "per_hop_authz": {
                "enabled": True,
                "deny_cross_tenant": True,
                "deny_sensitivity_escalation": True,
            },
            "edge_allowlist": {
                "enabled": True,
                "query_classes": {
                    "general": {"allowed": ["CONTAINS", "MENTIONS", "BELONGS_TO"]},
                },
            },
        },
        "description": "D1+D2: AuthZ + Edge Allowlist",
    },
    "P6": {
        "name": "hybrid_d1d2d3",
        "graph_enabled": True,
        "defenses": {
            "per_hop_authz": {
                "enabled": True,
                "deny_cross_tenant": True,
                "deny_sensitivity_escalation": True,
            },
            "edge_allowlist": {
                "enabled": True,
                "query_classes": {
                    "general": {"allowed": ["CONTAINS", "MENTIONS", "BELONGS_TO"]},
                },
            },
            "budgets": {
                "enabled": True,
                "max_hops": 2,
                "max_branching_factor": 8,
                "max_total_nodes": 40,
            },
        },
        "description": "D1+D2+D3: + Budgets",
    },
    "P7": {
        "name": "hybrid_d1d2d3d4",
        "graph_enabled": True,
        "defenses": {
            "per_hop_authz": {
                "enabled": True,
                "deny_cross_tenant": True,
                "deny_sensitivity_escalation": True,
            },
            "edge_allowlist": {
                "enabled": True,
                "query_classes": {
                    "general": {"allowed": ["CONTAINS", "MENTIONS", "BELONGS_TO"]},
                },
            },
            "budgets": {
                "enabled": True,
                "max_hops": 2,
                "max_branching_factor": 8,
                "max_total_nodes": 40,
            },
            "trust_weighting": {
                "enabled": True,
                "min_trust_score": 0.6,
            },
        },
        "description": "D1+D2+D3+D4: + Trust",
    },
    "P8": {
        "name": "hybrid_all_defenses",
        "graph_enabled": True,
        "defenses": {
            "per_hop_authz": {
                "enabled": True,
                "deny_cross_tenant": True,
                "deny_sensitivity_escalation": True,
            },
            "edge_allowlist": {
                "enabled": True,
                "query_classes": {
                    "general": {"allowed": ["CONTAINS", "MENTIONS", "BELONGS_TO"]},
                },
            },
            "budgets": {
                "enabled": True,
                "max_hops": 2,
                "max_branching_factor": 8,
                "max_total_nodes": 40,
            },
            "trust_weighting": {
                "enabled": True,
                "min_trust_score": 0.6,
            },
            "merge_filter": {
                "enabled": True,
            },
        },
        "description": "All defenses (D1-D5)",
    },
}


def build_pipeline_config(variant: str) -> PipelineConfig:
    """Build a PipelineConfig programmatically for a given variant."""
    pdef = PIPELINE_DEFS[variant]
    defenses_raw = pdef.get("defenses", {})
    defense_kwargs = {}
    for key in ("per_hop_authz", "edge_allowlist", "budgets", "trust_weighting", "merge_filter"):
        defense_kwargs[key] = defenses_raw.get(key, {"enabled": False})

    graph_config = _make_graph_config() if pdef["graph_enabled"] else GraphConfig(enabled=False)

    return PipelineConfig(
        name=pdef["name"],
        variant=variant,
        vector=_make_vector_config(),
        graph=graph_config,
        defenses=DefenseConfig(**defense_kwargs),
    )


def create_pipeline(
    variant: str,
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    embed_model: str = "all-MiniLM-L6-v2",
    chroma_collection: str = "pivorag_chunks",
):
    """Create a pipeline instance connected to live services."""
    from pivorag.vector.embed import EmbeddingModel
    from pivorag.vector.index import VectorIndex
    from pivorag.vector.retrieve import VectorRetriever

    config = build_pipeline_config(variant)
    model = EmbeddingModel(embed_model)
    index = VectorIndex(
        host=chroma_host,
        port=chroma_port,
        collection_name=chroma_collection,
    )
    retriever = VectorRetriever(index=index, embedding_model=model)

    if variant == "P1":
        from pivorag.pipelines.vector_only import VectorOnlyPipeline
        return VectorOnlyPipeline(config=config, retriever=retriever)

    # Hybrid pipelines (P3-P8) need a graph expander
    from neo4j import GraphDatabase

    from pivorag.graph.expand import GraphExpander
    from pivorag.pipelines.hybrid import HybridPipeline

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
    expander = GraphExpander(driver=driver)
    return HybridPipeline(
        config=config,
        vector_retriever=retriever,
        graph_expander=expander,
    )


# ── Query loading ────────────────────────────────────────────────

def load_queries(
    query_set: str,
    queries_file: str | None = None,
    dataset: str | None = None,
    n_queries: int = 200,
) -> list[BenchmarkQuery]:
    """Load queries from JSON file or generate from a dataset adapter.

    Args:
        query_set: Name of the query set (e.g., "benign", "adversarial").
        queries_file: Optional explicit file path. Overrides query_set-based lookup.
        dataset: Dataset name to generate queries from (e.g., "enron", "edgar").
            When set, ignores query_set file lookup and uses the adapter.
        n_queries: Number of queries to generate per type when using a dataset adapter.
    """
    # If a non-synthetic dataset is specified, generate queries via adapter
    if dataset and dataset != "synthetic" and not queries_file:
        from pivorag.datasets import get_adapter
        adapter = get_adapter(dataset)
        if query_set == "adversarial":
            return adapter.generate_queries(n_benign=0, n_adversarial=n_queries)
        elif query_set == "benign":
            return adapter.generate_queries(n_benign=n_queries, n_adversarial=0)
        else:
            return adapter.generate_queries(
                n_benign=n_queries, n_adversarial=n_queries,
            )

    path = Path(queries_file) if queries_file else Path(f"data/queries/{query_set}.json")
    raw = json.loads(path.read_text())
    queries = []
    for q in raw:
        queries.append(BenchmarkQuery(
            query=q["text"],
            query_type=q.get("attack_type", "benign"),
            user_id=f"user_{q['query_id'].lower()}",
            user_tenant=q["tenant"],
            user_clearance=q["user_clearance"],
        ))
    return queries


def resolve_collection(dataset: str | None, chroma_collection: str) -> str:
    """Map a dataset name to the correct ChromaDB collection name."""
    if dataset and dataset != "synthetic":
        from pivorag.datasets import get_adapter
        return get_adapter(dataset).get_collection_name()
    return chroma_collection


# ── Detailed per-query analysis ──────────────────────────────────

def analyze_context(
    ctx: RetrievalContext,
    query_id: str = "",
) -> dict[str, Any]:
    """Produce detailed per-query analysis of a retrieval context."""
    all_items = ctx.chunks + ctx.graph_nodes
    cross_tenant = [
        item for item in all_items
        if item.get("tenant") and item["tenant"] != ctx.user_tenant
    ]
    over_clearance = [
        item for item in all_items
        if SensitivityTier(item.get("sensitivity", "PUBLIC")) > ctx.user_clearance
    ]
    # Count by tenant and sensitivity
    tenant_counts: dict[str, int] = {}
    sens_counts: dict[str, int] = {}
    for item in all_items:
        t = item.get("tenant", "unknown")
        s = item.get("sensitivity", "PUBLIC")
        tenant_counts[t] = tenant_counts.get(t, 0) + 1
        sens_counts[s] = sens_counts.get(s, 0) + 1

    return {
        "query_id": query_id,
        "query": ctx.query,
        "user_tenant": ctx.user_tenant,
        "user_clearance": ctx.user_clearance.value,
        "pipeline": ctx.pipeline_variant,
        "vector_chunks": len(ctx.chunks),
        "graph_nodes": len(ctx.graph_nodes),
        "total_items": len(all_items),
        "cross_tenant_items": len(cross_tenant),
        "over_clearance_items": len(over_clearance),
        "leakage_at_k": leakage_at_k(ctx),
        "severity_weighted_leakage": severity_weighted_leakage(ctx),
        "pivot_depth": pivot_depth(ctx),
        "latency_ms": round(ctx.latency_ms, 1),
        "tenant_distribution": tenant_counts,
        "sensitivity_distribution": sens_counts,
        "traversal_log": ctx.traversal_log,
    }


# ── Experiment execution ─────────────────────────────────────────

def run_experiment(
    variants: list[str],
    query_set: str,
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    output_dir: str,
    queries_file: str | None = None,
    bootstrap: bool = False,
    embed_model: str = "all-MiniLM-L6-v2",
    chroma_collection: str = "pivorag_chunks",
    dataset: str | None = None,
) -> dict[str, Any]:
    """Run all specified pipeline variants against a query set."""
    collection = resolve_collection(dataset, chroma_collection)
    queries = load_queries(query_set, queries_file=queries_file, dataset=dataset)
    click.echo(f"Loaded {len(queries)} {query_set} queries (collection: {collection})")

    results: dict[str, Any] = {}
    all_contexts: dict[str, list[RetrievalContext]] = {}

    for variant in variants:
        desc = PIPELINE_DEFS[variant].get("description", variant)
        click.echo(f"\n{'='*60}")
        click.echo(f"Running {variant}: {desc}")
        click.echo(f"{'='*60}")

        pipeline = create_pipeline(
            variant, chroma_host, chroma_port,
            neo4j_uri, neo4j_user, neo4j_pass,
            embed_model=embed_model,
            chroma_collection=collection,
        )

        runner = BenchmarkRunner(output_dir=output_dir)
        p1_contexts = all_contexts.get("P1")
        result = runner.run(
            pipeline, queries,
            vector_baseline_contexts=p1_contexts,
            compute_bootstrap=bootstrap,
        )

        # Store contexts for AF computation
        all_contexts[variant] = result.raw_contexts

        # Detailed per-query analysis with query IDs
        per_query = [
            analyze_context(ctx, query_id=queries[i].user_id)
            for i, ctx in enumerate(result.raw_contexts)
        ]

        results[variant] = {
            "security": result.security.to_dict(),
            "utility": result.utility.to_dict(),
            "per_query": per_query,
        }

        # Recompute AF variants if we have P1 baseline
        if variant != "P1" and p1_contexts:
            af = amplification_factor(result.raw_contexts, p1_contexts)
            af_eps = amplification_factor_epsilon(result.raw_contexts, p1_contexts)
            d_leak = delta_leakage(result.raw_contexts, p1_contexts)
            results[variant]["security"]["amplification_factor"] = af
            results[variant]["security"]["af_epsilon"] = af_eps
            results[variant]["security"]["delta_leakage"] = d_leak

        # PD distribution
        pd_dist = pivot_depth_distribution(result.raw_contexts)
        results[variant]["security"]["pd_distribution"] = pd_dist

        # Print summary
        sec = result.security
        click.echo(f"  RPR:          {sec.rpr:.3f}")
        click.echo(f"  Mean Leak:    {sec.mean_leakage:.2f}")
        click.echo(f"  Sev-W Leak:   {sec.mean_severity_weighted_leakage:.2f}")
        click.echo(f"  AF:           {sec.amplification_factor:.2f}")
        af_eps_val = results[variant]["security"].get("af_epsilon", 0)
        click.echo(f"  AF(eps):      {af_eps_val:.2f}")
        click.echo(f"  Mean PD:      {sec.mean_pivot_depth:.2f}")
        click.echo(f"  PD dist:      {pd_dist}")
        click.echo(f"  Leak Queries: {sec.queries_with_leakage}/{sec.total_queries}")
        click.echo(f"  p50 latency:  {result.utility.p50_latency_ms:.1f}ms")
        click.echo(f"  p95 latency:  {result.utility.p95_latency_ms:.1f}ms")
        click.echo(f"  Ctx size:     {result.utility.mean_context_size:.1f}")

        if bootstrap and sec.rpr_ci:
            click.echo(
                f"  RPR 95% CI:   [{sec.rpr_ci[1]:.3f}, {sec.rpr_ci[2]:.3f}]"
            )
        if bootstrap and sec.leakage_ci:
            click.echo(
                f"  Leak 95% CI:  [{sec.leakage_ci[1]:.2f}, {sec.leakage_ci[2]:.2f}]"
            )

        # Save individual result
        runner.save_results(result, label=query_set)

    return results


def print_comparison_table(results: dict[str, Any], query_set: str) -> None:
    """Print a formatted comparison table of all variants."""
    click.echo(f"\n{'='*80}")
    click.echo(f"  EXPERIMENT RESULTS — {query_set.upper()} QUERIES")
    click.echo(f"{'='*80}")
    click.echo(
        f"{'Variant':<8} {'RPR':>6} {'Leak':>6} {'AF':>7} {'PD':>6} "
        f"{'Leak/Q':>7} {'p50ms':>7} {'p95ms':>7} {'CtxSz':>6}"
    )
    click.echo("-" * 80)

    for variant, data in results.items():
        sec = data["security"]
        util = data["utility"]
        af_val = sec["amplification_factor"]
        af_str = "inf" if af_val == float("inf") else f"{af_val:.2f}"
        click.echo(
            f"{variant:<8} {sec['rpr']:>6.3f} {sec['mean_leakage']:>6.2f} "
            f"{af_str:>7} {sec['mean_pivot_depth']:>6.2f} "
            f"{sec['queries_with_leakage']}/{sec['total_queries']:>4} "
            f"{util['p50_latency_ms']:>7.1f} {util['p95_latency_ms']:>7.1f} "
            f"{util['mean_context_size']:>6.1f}"
        )

    click.echo("-" * 80)


def save_full_results(
    results: dict[str, Any],
    query_set: str,
    output_dir: str,
    dataset: str = "synthetic",
) -> Path:
    """Save the complete results to a single JSON file."""
    out = Path(output_dir) / "tables"
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out / f"experiment_{dataset}_{query_set}_{timestamp}.json"

    # Strip raw contexts (not JSON-serializable) from per_query
    serializable = {}
    for variant, data in results.items():
        serializable[variant] = {
            "security": data["security"],
            "utility": data["utility"],
            "per_query": data["per_query"],
        }

    output = {
        "experiment": f"baseline_{dataset}_{query_set}",
        "dataset": dataset,
        "timestamp": timestamp,
        "variants": serializable,
    }
    path.write_text(json.dumps(output, indent=2, default=str))
    click.echo(f"\nResults saved to {path}")
    return path


# ── CLI ──────────────────────────────────────────────────────────

@click.command()
@click.option("--baseline", is_flag=True, help="Run P1 vs P3 baseline comparison")
@click.option("--full", is_flag=True, help="Run full ablation (P1, P3-P8)")
@click.option(
    "--variants", "-v", multiple=True,
    help="Specific variants to run (e.g., -v P1 -v P3 -v P4)",
)
@click.option(
    "--queries", "-q", default="benign",
    type=click.Choice(["benign", "adversarial", "both"]),
    help="Query set to use",
)
@click.option("--queries-file", default=None, help="Explicit path to queries JSON file")
@click.option(
    "--dataset", "-d", default="synthetic",
    type=click.Choice(["synthetic", "enron", "edgar"]),
    help="Dataset to evaluate (determines collection and query source)",
)
@click.option("--bootstrap", is_flag=True, help="Compute bootstrap 95%% CIs")
@click.option("--chroma-host", default="localhost")
@click.option("--chroma-port", default=8000, type=int)
@click.option("--neo4j-uri", default="bolt://localhost:7687")
@click.option("--neo4j-user", default="neo4j")
@click.option("--neo4j-pass", default="pivorag_dev_2025")
@click.option("--output", "-o", default="results")
@click.option("--embed-model", default="all-MiniLM-L6-v2", help="Embedding model name")
@click.option("--chroma-collection", default="pivorag_chunks", help="ChromaDB collection")
def main(
    baseline: bool,
    full: bool,
    variants: tuple[str, ...],
    queries: str,
    queries_file: str | None,
    dataset: str,
    bootstrap: bool,
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    output: str,
    embed_model: str,
    chroma_collection: str,
) -> None:
    """Run PivoRAG experiments and measure retrieval pivot risk."""
    start = time.perf_counter()

    # Determine which variants to run
    if variants:
        variant_list = list(variants)
    elif full:
        variant_list = ["P1", "P3", "P4", "P5", "P6", "P7", "P8"]
    elif baseline:
        variant_list = ["P1", "P3"]
    else:
        click.echo("Specify --baseline, --full, or --variants. Use --help for details.")
        return

    # Always run P1 first (needed for AF computation)
    if "P1" not in variant_list:
        variant_list.insert(0, "P1")

    # Determine query sets
    query_sets = ["benign", "adversarial"] if queries == "both" else [queries]

    click.echo("PivoRAG Experiment Runner")
    click.echo(f"Dataset:  {dataset}")
    click.echo(f"Variants: {', '.join(variant_list)}")
    click.echo(f"Queries:  {', '.join(query_sets)}")
    if queries_file:
        click.echo(f"File:     {queries_file}")
    if bootstrap:
        click.echo("Bootstrap: enabled (10,000 resamples)")
    click.echo(f"Output:   {output}/")

    for qset in query_sets:
        results = run_experiment(
            variant_list, qset,
            chroma_host, chroma_port,
            neo4j_uri, neo4j_user, neo4j_pass,
            output,
            queries_file=queries_file,
            bootstrap=bootstrap,
            embed_model=embed_model,
            chroma_collection=chroma_collection,
            dataset=dataset,
        )
        print_comparison_table(results, qset)
        save_full_results(results, qset, output, dataset=dataset)

    elapsed = time.perf_counter() - start
    click.echo(f"\nTotal experiment time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
