#!/usr/bin/env python3
"""Run end-to-end generation evaluation across LLM providers and datasets.

Measures how leaked retrieval context contaminates LLM-generated answers
using ECR, ILS, FCR, and GRR metrics.

For each query:
  1. Retrieve with P3 (undefended hybrid) and P4 (defended, D1 only)
  2. Identify leaked items = P3 context − P4 context
  3. Generate answers with selected LLMs on both contexts
  4. Compute ECR, ILS, FCR, GRR per (query, LLM) pair

Usage:
    python scripts/run_generation_eval.py --dataset synthetic --llm openai
    python scripts/run_generation_eval.py --dataset enron --llm all --queries 50
    python scripts/run_generation_eval.py --dataset edgar --llm deepseek --budget 10
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
import numpy as np

from pivorag.config import SensitivityTier
from pivorag.eval.generation_metrics import (
    GenerationMetrics,
    entity_contamination_rate,
    factual_contamination_rate,
    generation_refusal_rate,
    information_leakage_score,
)
from pivorag.generation.context_assembler import assemble_prompt
from pivorag.generation.llm_client import (
    AnthropicClient,
    DeepSeekClient,
    LLMClient,
    OpenAIClient,
)

logger = logging.getLogger(__name__)

LLM_PROVIDERS: dict[str, type[LLMClient]] = {
    "openai": OpenAIClient,
    "anthropic": AnthropicClient,
    "deepseek": DeepSeekClient,
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


def identify_leaked_items(p3_ctx, p4_ctx) -> list[dict]:
    """Find items in P3 context that are NOT in P4 context (the leaked set)."""
    p4_ids = {
        item.get("node_id", item.get("chunk_id", ""))
        for item in p4_ctx.chunks + p4_ctx.graph_nodes
    }
    leaked = []
    for item in p3_ctx.chunks + p3_ctx.graph_nodes:
        item_id = item.get("node_id", item.get("chunk_id", ""))
        if item_id and item_id not in p4_ids:
            leaked.append(item)
    return leaked


def extract_entities_from_items(items: list[dict]) -> list[str]:
    """Extract entity names from leaked items."""
    entities = set()
    for item in items:
        # Entity nodes have canonical_name or node_type=Entity
        name = item.get("canonical_name", "")
        if name:
            entities.add(name)
        # Chunks may reference entities in metadata
        for ent in item.get("entities", []):
            if isinstance(ent, str):
                entities.add(ent)
            elif isinstance(ent, dict):
                entities.add(ent.get("name", ""))
    return [e for e in entities if e]


def extract_text_from_items(items: list[dict]) -> list[str]:
    """Extract text content from context items."""
    texts = []
    for item in items:
        text = item.get("text", item.get("properties", {}).get("text", ""))
        if text:
            texts.append(text)
    return texts


def evaluate_single_query(
    query_text: str,
    user_tenant: str,
    user_clearance: str,
    p3_pipeline,
    p4_pipeline,
    llm_client: LLMClient,
    judge_client: LLMClient,
    embed_model,
    budget_remaining: float,
) -> dict[str, Any] | None:
    """Run generation evaluation for a single query.

    Returns None if budget is exhausted.
    """
    if budget_remaining <= 0:
        return None

    # Retrieve with P3 (undefended) and P4 (defended)
    p3_ctx = p3_pipeline.retrieve(
        query=query_text,
        user_id="eval_user",
        user_tenant=user_tenant,
        user_clearance=SensitivityTier(user_clearance),
    )
    p4_ctx = p4_pipeline.retrieve(
        query=query_text,
        user_id="eval_user",
        user_tenant=user_tenant,
        user_clearance=SensitivityTier(user_clearance),
    )

    # Identify leaked items
    leaked_items = identify_leaked_items(p3_ctx, p4_ctx)
    if not leaked_items:
        return {
            "query": query_text,
            "leaked_count": 0,
            "metrics": GenerationMetrics().to_dict(),
            "skipped": "no_leakage",
        }

    leaked_entities = extract_entities_from_items(leaked_items)
    leaked_texts = extract_text_from_items(leaked_items)

    # Generate answers with both contexts
    p3_system, p3_user = assemble_prompt(p3_ctx)
    p4_system, p4_user = assemble_prompt(p4_ctx)

    contaminated_result = llm_client.generate(p3_user, system=p3_system)
    clean_result = llm_client.generate(p4_user, system=p4_system)

    contaminated_answer = contaminated_result.text
    clean_answer = clean_result.text
    cost_so_far = contaminated_result.cost_usd + clean_result.cost_usd

    # ECR
    ecr = entity_contamination_rate(contaminated_answer, leaked_entities)

    # ILS
    answer_emb = embed_model.embed(contaminated_answer)
    leaked_embs = [embed_model.embed(t) for t in leaked_texts[:10]]
    ils = information_leakage_score(answer_emb, leaked_embs)

    # FCR (uses judge, costs tokens)
    fcr = factual_contamination_rate(
        query_text, contaminated_answer, clean_answer,
        leaked_texts, judge_client,
    )
    cost_so_far += judge_client.total_cost_usd  # approximate

    # GRR
    grr = generation_refusal_rate(contaminated_answer, clean_answer)

    return {
        "query": query_text,
        "leaked_count": len(leaked_items),
        "leaked_entity_count": len(leaked_entities),
        "metrics": GenerationMetrics(
            ecr=ecr, ils=ils, fcr=fcr, grr=grr,
        ).to_dict(),
        "cost_usd": cost_so_far,
    }


@click.command()
@click.option("--dataset", "-d", default="synthetic",
              type=click.Choice(["synthetic", "enron", "edgar"]),
              help="Dataset to evaluate")
@click.option("--llm", "-l", default="openai",
              type=click.Choice(["openai", "anthropic", "deepseek", "all"]),
              help="LLM provider (or 'all' for all three)")
@click.option("--queries", "-q", default=200, type=int,
              help="Number of queries to evaluate")
@click.option("--budget", default=50.0, type=float,
              help="Maximum budget in USD across all providers")
@click.option("--output", "-o", default="results", help="Output directory")
@click.option("--seed", default=42, type=int, help="Random seed")
@click.option("--chroma-host", default="localhost")
@click.option("--chroma-port", default=8000, type=int)
@click.option("--neo4j-uri", default="bolt://localhost:7687")
@click.option("--neo4j-user", default="neo4j")
@click.option("--neo4j-pass", default="pivorag_dev_2025")
@click.option("--dry-run", is_flag=True,
              help="Print config only, don't connect to services")
def main(
    dataset: str,
    llm: str,
    queries: int,
    budget: float,
    output: str,
    seed: int,
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    dry_run: bool,
) -> None:
    """Run generation evaluation for PivoRAG experiments."""
    logging.basicConfig(level=logging.INFO)
    start = time.perf_counter()

    providers = list(LLM_PROVIDERS.keys()) if llm == "all" else [llm]

    # Resolve collection from dataset
    if dataset != "synthetic":
        from pivorag.datasets import get_adapter
        collection = get_adapter(dataset).get_collection_name()
    else:
        collection = "pivorag_chunks"

    click.echo("PivoRAG Generation Evaluation")
    click.echo(f"  Dataset:    {dataset} (collection: {collection})")
    click.echo(f"  LLMs:       {providers}")
    click.echo(f"  Queries:    {queries}")
    click.echo(f"  Budget:     ${budget:.2f}")

    if dry_run:
        for provider in providers:
            client = LLM_PROVIDERS[provider]()
            click.echo(f"\n  {provider}: model={client.model}")
        click.echo("\nDry run complete. Add live service flags to execute.")
        return

    # Load queries
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_experiments import load_queries
    benchmark_queries = load_queries("benign", dataset=dataset, n_queries=queries)
    click.echo(f"  Loaded {len(benchmark_queries)} queries")

    # Create pipelines (P3 undefended, P4 defended)
    p3_pipeline = create_pipeline(
        "P3", chroma_host, chroma_port,
        neo4j_uri, neo4j_user, neo4j_pass,
        chroma_collection=collection,
    )
    p4_pipeline = create_pipeline(
        "P4", chroma_host, chroma_port,
        neo4j_uri, neo4j_user, neo4j_pass,
        chroma_collection=collection,
    )

    # Embedding model for ILS computation
    from pivorag.vector.embed import EmbeddingModel
    embed_model = EmbeddingModel("all-MiniLM-L6-v2")

    output_dir = Path(output) / "tables"
    output_dir.mkdir(parents=True, exist_ok=True)

    for provider in providers:
        client_cls = LLM_PROVIDERS[provider]
        client = client_cls()
        judge = OpenAIClient(model="gpt-4o") if provider != "openai" else client

        click.echo(f"\n{'='*60}")
        click.echo(f"Evaluating with {provider} ({client.model})")
        click.echo(f"{'='*60}")

        budget_remaining = budget / len(providers)
        results_per_query: list[dict] = []

        for i, bq in enumerate(benchmark_queries):
            if budget_remaining <= 0:
                click.echo(f"  Budget exhausted after {i} queries")
                break

            result = evaluate_single_query(
                query_text=bq.query,
                user_tenant=bq.user_tenant,
                user_clearance=bq.user_clearance,
                p3_pipeline=p3_pipeline,
                p4_pipeline=p4_pipeline,
                llm_client=client,
                judge_client=judge,
                embed_model=embed_model,
                budget_remaining=budget_remaining,
            )
            if result is None:
                break

            results_per_query.append(result)
            cost = result.get("cost_usd", 0)
            budget_remaining -= cost

            if (i + 1) % 20 == 0:
                click.echo(
                    f"  [{i + 1}/{len(benchmark_queries)}] "
                    f"budget remaining: ${budget_remaining:.2f}"
                )

        # Aggregate metrics
        metrics_list = [
            r["metrics"] for r in results_per_query
            if r.get("skipped") is None
        ]
        if metrics_list:
            mean_ecr = np.mean([m["ecr"] for m in metrics_list])
            mean_ils = np.mean([m["ils"] for m in metrics_list])
            mean_fcr = np.mean([m["fcr"] for m in metrics_list])
            mean_grr = np.mean([m["grr"] for m in metrics_list])
        else:
            mean_ecr = mean_ils = mean_fcr = mean_grr = 0.0

        summary = {
            "provider": provider,
            "model": client.model,
            "dataset": dataset,
            "total_queries": len(results_per_query),
            "queries_with_leakage": sum(
                1 for r in results_per_query if r.get("skipped") is None
            ),
            "mean_ecr": float(mean_ecr),
            "mean_ils": float(mean_ils),
            "mean_fcr": float(mean_fcr),
            "mean_grr": float(mean_grr),
            "total_cost_usd": client.total_cost_usd,
        }

        click.echo(f"\n  Results for {provider}:")
        click.echo(f"    ECR: {mean_ecr:.3f}")
        click.echo(f"    ILS: {mean_ils:.3f}")
        click.echo(f"    FCR: {mean_fcr:.3f}")
        click.echo(f"    GRR: {mean_grr:.3f}")
        click.echo(f"    Cost: ${client.total_cost_usd:.2f}")

        # Save per-provider results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = output_dir / f"generation_{dataset}_{provider}_{timestamp}.json"
        path.write_text(json.dumps({
            "summary": summary,
            "per_query": results_per_query,
        }, indent=2, default=str))
        click.echo(f"    Saved to {path}")

    elapsed = time.perf_counter() - start
    click.echo(f"\nTotal generation eval time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
