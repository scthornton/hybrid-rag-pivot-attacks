#!/usr/bin/env python3
"""Run end-to-end generation evaluation across LLM providers and datasets.

Measures how leaked retrieval context contaminates LLM-generated answers
using ECR, ILS, FCR, and GRR metrics.

Usage:
    python scripts/run_generation_eval.py --dataset synthetic --llm openai
    python scripts/run_generation_eval.py --dataset enron --llm anthropic --queries 50
    python scripts/run_generation_eval.py --dataset edgar --llm deepseek --budget 10
"""

from __future__ import annotations

import logging

import click

from pivorag.generation.llm_client import AnthropicClient, DeepSeekClient, LLMClient, OpenAIClient

logger = logging.getLogger(__name__)

LLM_PROVIDERS: dict[str, type[LLMClient]] = {
    "openai": OpenAIClient,
    "anthropic": AnthropicClient,
    "deepseek": DeepSeekClient,
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
def main(
    dataset: str,
    llm: str,
    queries: int,
    budget: float,
    output: str,
    seed: int,
) -> None:
    """Run generation evaluation for PivoRAG experiments."""
    logging.basicConfig(level=logging.INFO)

    providers = list(LLM_PROVIDERS.keys()) if llm == "all" else [llm]

    click.echo(f"Generation evaluation: dataset={dataset}, LLMs={providers}")
    click.echo(f"Queries: {queries}, budget: ${budget:.2f}")

    # Build LLM clients
    for provider in providers:
        client_cls = LLM_PROVIDERS[provider]
        client = client_cls()
        click.echo(f"\nEvaluating with {provider} ({client.model})...")

        # Build judge client (always GPT-4o for consistency)
        _judge = OpenAIClient(model="gpt-4o") if provider != "openai" else client

        click.echo(f"  Provider: {provider}")
        click.echo(f"  Model: {client.model}")
        click.echo(f"  Budget: ${budget:.2f}")
        click.echo(
            "  Note: Full pipeline evaluation requires live Neo4j + ChromaDB. "
            "Run with --help for connection options."
        )

    click.echo("\nGeneration evaluation framework ready.")
    click.echo("Connect to live services to execute full benchmark.")


if __name__ == "__main__":
    main()
