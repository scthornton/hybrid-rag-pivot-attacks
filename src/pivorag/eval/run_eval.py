"""CLI entry point for running pivorag experiments.

Usage:
    pivorag --config configs/pipelines/hybrid_baseline.yaml --queries data/queries/benign.json
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from pivorag.config import load_pipeline_config


@click.group()
def cli() -> None:
    """PivoRAG: Retrieval Pivot Attack evaluation framework."""


@cli.command()
@click.option("--config", "-c", required=True, help="Pipeline config YAML path")
@click.option("--queries", "-q", required=True, help="Query set JSON path")
@click.option("--output", "-o", default="results", help="Output directory")
@click.option("--label", "-l", default="", help="Experiment label")
def run(config: str, queries: str, output: str, label: str) -> None:
    """Run a benchmark evaluation with a given pipeline config."""
    click.echo(f"Loading pipeline config: {config}")
    pipeline_config = load_pipeline_config(config)
    click.echo(f"Pipeline: {pipeline_config.name} ({pipeline_config.variant})")

    click.echo(f"Loading queries: {queries}")
    query_data = json.loads(Path(queries).read_text())
    click.echo(f"Loaded {len(query_data)} queries")

    # Pipeline assembly and execution will be implemented here
    click.echo("Pipeline execution not yet implemented — scaffold only.")
    click.echo(f"Results would be saved to: {output}/")


@cli.command()
def info() -> None:
    """Show information about available pipeline variants and attacks."""
    click.echo("Pipeline Variants:")
    click.echo("  P1: vector_only    — Vector similarity search only")
    click.echo("  P2: graph_only     — Graph traversal only")
    click.echo("  P3: hybrid_baseline — Vector→Graph, no defenses")
    click.echo("  P4-P8: hybrid_defended — With D1-D5 defense combinations")
    click.echo()
    click.echo("Attacks:")
    click.echo("  A1: seed_steering       — Centroid poisoning")
    click.echo("  A2: entity_anchor       — Entity anchor injection")
    click.echo("  A3: neighborhood_flood  — Graph gravity flooding")
    click.echo("  A4: bridge_node         — Cross-boundary bridges")
    click.echo()
    click.echo("Metrics:")
    click.echo("  RPR:        Retrieval Pivot Risk (probability)")
    click.echo("  Leakage@k:  Sensitive items in top-k context")
    click.echo("  AF:         Amplification Factor (hybrid / vector)")
    click.echo("  PD:         Pivot Depth (hops to sensitive node)")


if __name__ == "__main__":
    cli()
