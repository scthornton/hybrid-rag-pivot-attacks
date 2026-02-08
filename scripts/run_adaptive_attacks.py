#!/usr/bin/env python3
"""Run adaptive attacker experiments (A5-A7) across datasets and pipelines.

Tests whether D1 (per-hop authZ) is sufficient under an adaptive
attacker, or whether D4 (trust weighting) is necessary.

For A5 (metadata forgery), this is the critical test:
  - D1 alone FAILS because forged tenant labels pass authorization
  - D1+D4 holds because forged docs have low provenance scores

Usage:
    python scripts/run_adaptive_attacks.py --dataset synthetic
    python scripts/run_adaptive_attacks.py --dataset enron --attacks A5 A6
    python scripts/run_adaptive_attacks.py --dataset edgar --forgery-rates 0.01 0.05 0.1
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import click

from pivorag.attacks.entity_manipulation import EntityManipulationAttack
from pivorag.attacks.metadata_forgery import MetadataForgeryAttack
from pivorag.attacks.query_manipulation import QueryManipulationAttack
from pivorag.config import SensitivityTier
from pivorag.eval.metrics import leakage_at_k, pivot_depth

logger = logging.getLogger(__name__)

ADAPTIVE_ATTACKS = {
    "A5": MetadataForgeryAttack,
    "A6": EntityManipulationAttack,
    "A7": QueryManipulationAttack,
}


def create_pipeline(
    variant: str,
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    chroma_collection: str = "pivorag_chunks",
):
    """Create a pipeline instance connected to live services."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_experiments import build_pipeline_config

    from pivorag.vector.embed import EmbeddingModel
    from pivorag.vector.index import VectorIndex
    from pivorag.vector.retrieve import VectorRetriever

    config = build_pipeline_config(variant)
    model = EmbeddingModel("all-MiniLM-L6-v2")
    index = VectorIndex(
        host=chroma_host, port=chroma_port,
        collection_name=chroma_collection,
    )
    retriever = VectorRetriever(index=index, embedding_model=model)

    if variant == "P1":
        from pivorag.pipelines.vector_only import VectorOnlyPipeline
        return VectorOnlyPipeline(config=config, retriever=retriever)

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


def compute_metrics(contexts) -> dict[str, Any]:
    """Compute security metrics from a list of retrieval contexts."""
    total = len(contexts)
    leakages = [leakage_at_k(ctx) for ctx in contexts]
    depths = [pivot_depth(ctx) for ctx in contexts]
    queries_with_leak = sum(1 for leak in leakages if leak > 0)
    finite_depths = [d for d in depths if d != float("inf")]

    return {
        "rpr": queries_with_leak / max(total, 1),
        "mean_leakage": sum(leakages) / max(total, 1),
        "queries_with_leakage": queries_with_leak,
        "total_queries": total,
        "mean_pivot_depth": (
            sum(finite_depths) / len(finite_depths) if finite_depths else -1
        ),
    }


def inject_payloads_to_stores(
    payloads,
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    chroma_collection: str,
) -> dict[str, int]:
    """Inject attack payloads into vector and graph stores."""
    from pivorag.graph.build_graph import GraphBuilder
    from pivorag.graph.schema import GraphNode
    from pivorag.vector.embed import EmbeddingModel
    from pivorag.vector.index import VectorIndex

    model = EmbeddingModel("all-MiniLM-L6-v2")
    index = VectorIndex(
        host=chroma_host, port=chroma_port,
        collection_name=chroma_collection,
    )
    builder = GraphBuilder(
        uri=neo4j_uri, username=neo4j_user, password=neo4j_pass,
    )

    ids, embeddings, documents, metadatas = [], [], [], []
    for payload in payloads:
        chunk_id = f"injected_{payload.payload_id}"
        embedding = model.embed(payload.text).tolist()
        ids.append(chunk_id)
        embeddings.append(embedding)
        documents.append(payload.text)
        metadatas.append({
            "doc_id": f"injected_doc_{payload.payload_id}",
            "tenant": payload.metadata.get("forged_tenant", "acme_engineering"),
            "sensitivity": "PUBLIC",
            "trust_score": payload.metadata.get("provenance_score", 0.3),
            "provenance_score": payload.metadata.get("provenance_score", 0.3),
        })

    index.add_chunks(ids, embeddings, documents, metadatas)

    # Create graph nodes
    for payload in payloads:
        chunk_id = f"injected_{payload.payload_id}"
        builder.add_node(GraphNode(
            node_id=chunk_id,
            node_type="Chunk",
            tenant=payload.metadata.get("forged_tenant", "acme_engineering"),
            sensitivity="PUBLIC",
            provenance_score=payload.metadata.get("provenance_score", 0.3),
        ))

    builder.close()

    return {"chunks_injected": len(payloads)}


@click.command()
@click.option("--dataset", "-d", default="synthetic",
              type=click.Choice(["synthetic", "enron", "edgar"]),
              help="Dataset to evaluate")
@click.option("--attacks", "-a", default=["A5", "A6", "A7"],
              multiple=True, type=click.Choice(["A5", "A6", "A7"]),
              help="Which adaptive attacks to run")
@click.option("--forgery-rates", default=[0.01, 0.05, 0.1],
              multiple=True, type=float,
              help="Forgery rates for A5 metadata forgery")
@click.option("--budget", "-b", default=10, type=int,
              help="Injection budget per attack")
@click.option("--target-pipelines", default=["P3", "P4", "P7", "P8"],
              multiple=True, help="Pipelines to test attacks against")
@click.option("--output", "-o", default="results", help="Output directory")
@click.option("--seed", default=42, type=int, help="Random seed")
@click.option("--chroma-host", default="localhost")
@click.option("--chroma-port", default=8000, type=int)
@click.option("--neo4j-uri", default="bolt://localhost:7687")
@click.option("--neo4j-user", default="neo4j")
@click.option("--neo4j-pass", default="pivorag_dev_2025")
@click.option("--dry-run", is_flag=True,
              help="Generate payloads only, don't inject or measure")
def main(
    dataset: str,
    attacks: tuple[str, ...],
    forgery_rates: tuple[float, ...],
    budget: int,
    target_pipelines: tuple[str, ...],
    output: str,
    seed: int,
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    dry_run: bool,
) -> None:
    """Run adaptive attacker experiments for PivoRAG."""
    logging.basicConfig(level=logging.INFO)
    start = time.perf_counter()

    output_dir = Path(output) / "tables"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve collection from dataset
    if dataset != "synthetic":
        from pivorag.datasets import get_adapter
        collection = get_adapter(dataset).get_collection_name()
    else:
        collection = "pivorag_chunks"

    click.echo("PivoRAG Adaptive Attack Experiments")
    click.echo(f"  Dataset:    {dataset} (collection: {collection})")
    click.echo(f"  Attacks:    {list(attacks)}")
    click.echo(f"  Pipelines:  {list(target_pipelines)}")
    click.echo(f"  Budget:     {budget} payloads per attack")

    results = []

    for attack_name in attacks:
        attack_cls = ADAPTIVE_ATTACKS[attack_name]
        click.echo(f"\n{'='*60}")
        click.echo(f"Attack {attack_name}: {attack_cls.__name__}")
        click.echo(f"{'='*60}")

        if attack_name == "A5":
            for rate in forgery_rates:
                click.echo(f"\n  --- A5 forgery_rate={rate:.0%} ---")
                attack = attack_cls(injection_budget=budget, forgery_rate=rate)
                payloads = attack.generate_payloads(
                    ["test query about infrastructure"],
                )
                forged = sum(
                    1 for p in payloads if p.metadata.get("is_forged")
                )

                result_entry: dict[str, Any] = {
                    "attack": attack_name,
                    "dataset": dataset,
                    "forgery_rate": rate,
                    "payloads": len(payloads),
                    "forged_count": forged,
                    "honest_count": len(payloads) - forged,
                }

                if not dry_run:
                    # Inject and measure against each pipeline
                    inject_payloads_to_stores(
                        payloads, chroma_host, chroma_port,
                        neo4j_uri, neo4j_user, neo4j_pass, collection,
                    )
                    click.echo(f"    Injected {len(payloads)} payloads")

                    sys.path.insert(0, str(Path(__file__).resolve().parent))
                    from run_experiments import load_queries
                    queries = load_queries(
                        "adversarial", dataset=dataset, n_queries=100,
                    )

                    for variant in target_pipelines:
                        pipeline = create_pipeline(
                            variant, chroma_host, chroma_port,
                            neo4j_uri, neo4j_user, neo4j_pass,
                            chroma_collection=collection,
                        )
                        contexts = []
                        for q in queries:
                            ctx = pipeline.retrieve(
                                query=q.query,
                                user_id=q.user_id,
                                user_tenant=q.user_tenant,
                                user_clearance=SensitivityTier(q.user_clearance),
                            )
                            contexts.append(ctx)
                        metrics = compute_metrics(contexts)
                        result_entry[f"{variant}_rpr"] = metrics["rpr"]
                        result_entry[f"{variant}_leak"] = metrics["mean_leakage"]
                        click.echo(
                            f"    {variant}: RPR={metrics['rpr']:.3f}, "
                            f"Leak={metrics['mean_leakage']:.2f}"
                        )
                else:
                    click.echo(
                        f"    rate={rate:.0%}: {forged}/{len(payloads)} forged"
                    )

                results.append(result_entry)
        else:
            click.echo(f"\n  --- {attack_name} ---")
            attack = attack_cls(injection_budget=budget)
            payloads = attack.generate_payloads(
                ["test query about infrastructure"],
            )

            result_entry = {
                "attack": attack_name,
                "dataset": dataset,
                "payloads": len(payloads),
                "is_query_attack": attack_name == "A7",
            }

            if not dry_run and attack_name != "A7":
                inject_payloads_to_stores(
                    payloads, chroma_host, chroma_port,
                    neo4j_uri, neo4j_user, neo4j_pass, collection,
                )
                click.echo(f"    Injected {len(payloads)} payloads")

                sys.path.insert(0, str(Path(__file__).resolve().parent))
                from run_experiments import load_queries
                queries = load_queries(
                    "adversarial", dataset=dataset, n_queries=100,
                )

                for variant in target_pipelines:
                    pipeline = create_pipeline(
                        variant, chroma_host, chroma_port,
                        neo4j_uri, neo4j_user, neo4j_pass,
                        chroma_collection=collection,
                    )
                    contexts = []
                    for q in queries:
                        ctx = pipeline.retrieve(
                            query=q.query,
                            user_id=q.user_id,
                            user_tenant=q.user_tenant,
                            user_clearance=SensitivityTier(q.user_clearance),
                        )
                        contexts.append(ctx)
                    metrics = compute_metrics(contexts)
                    result_entry[f"{variant}_rpr"] = metrics["rpr"]
                    result_entry[f"{variant}_leak"] = metrics["mean_leakage"]
                    click.echo(
                        f"    {variant}: RPR={metrics['rpr']:.3f}, "
                        f"Leak={metrics['mean_leakage']:.2f}"
                    )
            else:
                click.echo(f"    Generated {len(payloads)} payloads")

            results.append(result_entry)

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = output_dir / f"adaptive_attacks_{dataset}_{timestamp}.json"
    summary_path.write_text(json.dumps(results, indent=2))
    click.echo(f"\nResults saved to {summary_path}")

    elapsed = time.perf_counter() - start
    click.echo(f"Total adaptive attack time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
