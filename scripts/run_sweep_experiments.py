#!/usr/bin/env python3
"""Run sweep experiments: connectivity sweep and traversal regime sweep.

E4: Connectivity sweep — vary bridge entity count, measure RPR.
E6: Traversal regime sweep — vary depth/branching/total_nodes.
E8: Metadata mislabel stress test.

Usage:
    python scripts/run_sweep_experiments.py --traversal-sweep
    python scripts/run_sweep_experiments.py --connectivity-sweep
    python scripts/run_sweep_experiments.py --mislabel-sweep
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
    SensitivityTier,
)
from pivorag.eval.metrics import leakage_at_k, pivot_depth


def load_queries(path: str) -> list[dict]:
    return json.loads(Path(path).read_text())


def run_queries_through_pipeline(
    variant: str,
    queries: list[dict],
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    graph_config_override: GraphConfig | None = None,
    defense_config_override: DefenseConfig | None = None,
):
    """Run queries through a pipeline, optionally with custom graph config."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_experiments import build_pipeline_config

    from pivorag.vector.embed import EmbeddingModel
    from pivorag.vector.index import VectorIndex
    from pivorag.vector.retrieve import VectorRetriever

    config = build_pipeline_config(variant)

    # Apply overrides
    if graph_config_override:
        config.graph = graph_config_override
    if defense_config_override:
        config.defenses = defense_config_override

    model = EmbeddingModel("all-MiniLM-L6-v2")
    index = VectorIndex(
        host=chroma_host, port=chroma_port,
        collection_name="pivorag_chunks",
    )
    retriever = VectorRetriever(index=index, embedding_model=model)

    if variant == "P1":
        from pivorag.pipelines.vector_only import VectorOnlyPipeline
        pipeline = VectorOnlyPipeline(config=config, retriever=retriever)
    else:
        from neo4j import GraphDatabase

        from pivorag.graph.expand import GraphExpander
        from pivorag.pipelines.hybrid import HybridPipeline

        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
        expander = GraphExpander(driver=driver)
        pipeline = HybridPipeline(
            config=config,
            vector_retriever=retriever,
            graph_expander=expander,
        )

    contexts = []
    for q in queries:
        ctx = pipeline.retrieve(
            query=q["text"],
            user_id=f"user_{q['query_id'].lower()}",
            user_tenant=q["tenant"],
            user_clearance=SensitivityTier(q["user_clearance"]),
        )
        contexts.append(ctx)
    return contexts


def compute_metrics(contexts) -> dict[str, Any]:
    total = len(contexts)
    leakages = [leakage_at_k(ctx) for ctx in contexts]
    queries_with_leak = sum(1 for leak in leakages if leak > 0)
    depths = [pivot_depth(ctx) for ctx in contexts]
    finite_depths = [d for d in depths if d != float("inf")]
    mean_ctx = sum(
        len(ctx.chunks) + len(ctx.graph_nodes) for ctx in contexts
    ) / max(total, 1)
    mean_lat = sum(ctx.latency_ms for ctx in contexts) / max(total, 1)

    return {
        "rpr": queries_with_leak / max(total, 1),
        "mean_leakage": sum(leakages) / max(total, 1),
        "queries_with_leakage": queries_with_leak,
        "total_queries": total,
        "mean_pivot_depth": (
            sum(finite_depths) / len(finite_depths) if finite_depths else -1
        ),
        "ctx_size": mean_ctx,
        "latency_ms": mean_lat,
    }


# ── E6: Traversal regime sweep ──────────────────────────────────

def run_traversal_sweep(
    queries: list[dict],
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
) -> list[dict]:
    """Sweep BFS parameters and measure RPR at each setting."""
    depths = [1, 2, 3]
    branchings = [5, 10, 25]
    total_nodes_list = [25, 50, 100]

    results = []
    combos = [
        (d, b, t)
        for d in depths
        for b in branchings
        for t in total_nodes_list
    ]
    click.echo(f"Traversal sweep: {len(combos)} combinations × {len(queries)} queries")

    for i, (d, b, t) in enumerate(combos):
        click.echo(f"  [{i + 1}/{len(combos)}] depth={d}, branching={b}, total={t}")
        graph_cfg = GraphConfig(
            enabled=True,
            max_hops=d,
            max_branching_factor=b,
            max_total_nodes=t,
            edge_types=[
                "CONTAINS", "MENTIONS", "BELONGS_TO",
                "DEPENDS_ON", "OWNED_BY", "DERIVED_FROM", "RELATED_TO",
            ],
        )
        contexts = run_queries_through_pipeline(
            "P3", queries,
            chroma_host, chroma_port,
            neo4j_uri, neo4j_user, neo4j_pass,
            graph_config_override=graph_cfg,
        )
        metrics = compute_metrics(contexts)
        result = {
            "depth": d,
            "branching": b,
            "total_nodes": t,
            **metrics,
        }
        results.append(result)
        click.echo(
            f"    RPR={metrics['rpr']:.3f}, Leak={metrics['mean_leakage']:.1f}, "
            f"Ctx={metrics['ctx_size']:.0f}, Lat={metrics['latency_ms']:.1f}ms"
        )

    return results


# ── E8: Mislabel stress test ────────────────────────────────────

def run_mislabel_sweep(
    queries: list[dict],
    rates: list[float],
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
) -> dict[str, dict]:
    """Randomly flip sensitivity labels on N% of nodes, then measure D1 RPR."""
    import random

    from neo4j import GraphDatabase

    results = {}

    for rate in rates:
        click.echo(f"\n  Mislabel rate: {rate}%")
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))

        # Get all node IDs with sensitivity labels
        with driver.session() as session:
            records = session.run(
                "MATCH (n) WHERE n.sensitivity IS NOT NULL "
                "RETURN n.node_id AS nid, n.sensitivity AS sens"
            ).data()

        total_nodes = len(records)
        n_flip = max(1, int(total_nodes * rate / 100))

        # Choose random nodes to flip
        random.seed(42)
        to_flip = random.sample(records, min(n_flip, total_nodes))

        # Flip labels (PUBLIC→RESTRICTED and vice versa)
        flip_map = {
            "PUBLIC": "RESTRICTED",
            "INTERNAL": "CONFIDENTIAL",
            "CONFIDENTIAL": "INTERNAL",
            "RESTRICTED": "PUBLIC",
        }

        with driver.session() as session:
            for record in to_flip:
                new_sens = flip_map.get(record["sens"], "PUBLIC")
                session.run(
                    "MATCH (n {node_id: $nid}) SET n.sensitivity = $sens",
                    nid=record["nid"], sens=new_sens,
                )

        click.echo(f"    Flipped {len(to_flip)}/{total_nodes} labels")

        # Run P4 (D1 defense) with corrupted labels
        contexts = run_queries_through_pipeline(
            "P4", queries,
            chroma_host, chroma_port,
            neo4j_uri, neo4j_user, neo4j_pass,
        )
        metrics = compute_metrics(contexts)
        results[str(rate)] = metrics
        click.echo(
            f"    P4 RPR={metrics['rpr']:.3f}, Leak={metrics['mean_leakage']:.2f}"
        )

        # Restore original labels
        with driver.session() as session:
            for record in to_flip:
                session.run(
                    "MATCH (n {node_id: $nid}) SET n.sensitivity = $sens",
                    nid=record["nid"], sens=record["sens"],
                )

        driver.close()

    return results


# ── E4: Connectivity sweep ─────────────────────────────────────

def run_connectivity_sweep(
    bridge_counts: list[int],
    queries: list[dict],
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
) -> list[dict]:
    """Sweep bridge entity count and measure RPR at each level.

    For each bridge count:
      1. Regenerate synthetic corpus with --bridge-count N
      2. Rebuild ChromaDB + Neo4j indexes
      3. Run queries through P1 (vector) and P3 (hybrid)
      4. Record RPR, Leakage@k, context size
    """
    import subprocess
    import sys

    python = sys.executable
    data_path = "data/raw/synthetic_enterprise.json"
    results = []

    for i, bc in enumerate(bridge_counts):
        click.echo(f"\n  [{i + 1}/{len(bridge_counts)}] bridge_count={bc}")

        # Step 1: Regenerate corpus
        click.echo(f"    Regenerating corpus with {bc} bridge entities...")
        cmd_gen = [
            python, "scripts/make_synth_data.py",
            "--scale", "medium",
            "--output", "data/raw",
            "--bridge-count", str(bc),
        ]
        result = subprocess.run(
            cmd_gen, capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            click.echo(f"    ERROR generating data: {result.stderr[:200]}")
            continue
        click.echo("    Data generated.")

        # Step 2: Rebuild indexes
        click.echo("    Rebuilding indexes...")
        cmd_build = [
            python, "scripts/build_indexes.py",
            "--data", data_path,
            "--chroma-host", chroma_host,
            "--chroma-port", str(chroma_port),
            "--neo4j-uri", neo4j_uri,
            "--neo4j-user", neo4j_user,
            "--neo4j-pass", neo4j_pass,
        ]
        result = subprocess.run(
            cmd_build, capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            click.echo(f"    ERROR building indexes: {result.stderr[:200]}")
            continue
        click.echo("    Indexes rebuilt.")

        # Step 3: Run P1 baseline
        click.echo("    Running P1 (vector-only)...")
        p1_contexts = run_queries_through_pipeline(
            "P1", queries,
            chroma_host, chroma_port,
            neo4j_uri, neo4j_user, neo4j_pass,
        )
        p1_metrics = compute_metrics(p1_contexts)

        # Step 4: Run P3 (undefended hybrid)
        click.echo("    Running P3 (hybrid, no defenses)...")
        p3_contexts = run_queries_through_pipeline(
            "P3", queries,
            chroma_host, chroma_port,
            neo4j_uri, neo4j_user, neo4j_pass,
        )
        p3_metrics = compute_metrics(p3_contexts)

        entry = {
            "bridge_count": bc,
            "p1_rpr": p1_metrics["rpr"],
            "p1_mean_leakage": p1_metrics["mean_leakage"],
            "p1_ctx_size": p1_metrics["ctx_size"],
            "p3_rpr": p3_metrics["rpr"],
            "p3_mean_leakage": p3_metrics["mean_leakage"],
            "p3_ctx_size": p3_metrics["ctx_size"],
            "p3_mean_pivot_depth": p3_metrics["mean_pivot_depth"],
            "p3_latency_ms": p3_metrics["latency_ms"],
        }
        results.append(entry)
        click.echo(
            f"    P1 RPR={p1_metrics['rpr']:.3f}, "
            f"P3 RPR={p3_metrics['rpr']:.3f}, "
            f"P3 Leak={p3_metrics['mean_leakage']:.1f}, "
            f"P3 Ctx={p3_metrics['ctx_size']:.0f}"
        )

    return results


# ── CLI ──────────────────────────────────────────────────────────

@click.command()
@click.option("--traversal-sweep", is_flag=True, help="Run E6: traversal regime sweep")
@click.option("--connectivity-sweep", is_flag=True, help="Run E4: bridge count sweep")
@click.option("--mislabel-sweep", is_flag=True, help="Run E8: metadata mislabel stress test")
@click.option(
    "--queries-file", default="data/queries/adversarial_500.json",
    help="Query file to use",
)
@click.option("--max-queries", default=100, type=int, help="Max queries per sweep point")
@click.option("--chroma-host", default="localhost")
@click.option("--chroma-port", default=8000, type=int)
@click.option("--neo4j-uri", default="bolt://localhost:7687")
@click.option("--neo4j-user", default="neo4j")
@click.option("--neo4j-pass", default="pivorag_dev_2025")
@click.option("--output", "-o", default="results")
def main(
    traversal_sweep: bool,
    connectivity_sweep: bool,
    mislabel_sweep: bool,
    queries_file: str,
    max_queries: int,
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    output: str,
) -> None:
    """Run sweep experiments for PivoRAG."""
    start = time.perf_counter()
    out_dir = Path(output) / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    queries = load_queries(queries_file)[:max_queries]
    click.echo(f"Loaded {len(queries)} queries from {queries_file}")

    if traversal_sweep:
        click.echo("\n=== E6: Traversal Regime Sweep ===")
        results = run_traversal_sweep(
            queries, chroma_host, chroma_port,
            neo4j_uri, neo4j_user, neo4j_pass,
        )
        path = out_dir / f"traversal_sweep_{timestamp}.json"
        path.write_text(json.dumps(results, indent=2, default=str))
        click.echo(f"\nSaved to {path}")

    if connectivity_sweep:
        click.echo("\n=== E4: Connectivity Sweep (Bridge Count) ===")
        bridge_counts = [0, 5, 10, 15, 25, 40]
        results = run_connectivity_sweep(
            bridge_counts, queries,
            chroma_host, chroma_port,
            neo4j_uri, neo4j_user, neo4j_pass,
        )
        path = out_dir / f"connectivity_sweep_{timestamp}.json"
        path.write_text(json.dumps(results, indent=2, default=str))
        click.echo(f"\nSaved to {path}")

    if mislabel_sweep:
        click.echo("\n=== E8: Metadata Mislabel Stress Test ===")
        rates = [0.1, 0.5, 1.0, 2.0, 5.0]
        results = run_mislabel_sweep(
            queries, rates,
            chroma_host, chroma_port,
            neo4j_uri, neo4j_user, neo4j_pass,
        )
        path = out_dir / f"mislabel_stress_{timestamp}.json"
        path.write_text(json.dumps(results, indent=2, default=str))
        click.echo(f"\nSaved to {path}")

    elapsed = time.perf_counter() - start
    click.echo(f"\nTotal sweep time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
