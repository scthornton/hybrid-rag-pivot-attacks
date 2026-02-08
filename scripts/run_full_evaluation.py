#!/usr/bin/env python3
"""Master experiment runner: orchestrates all experiments with checkpointing.

Runs the complete evaluation suite for the USENIX Security 2026 paper:
1. Cross-dataset baseline (3 datasets x 8 pipelines)
2. Generation contamination (3 datasets x 3 LLMs)
3. Adaptive attacker (A5-A7 across datasets and pipelines)
4. Graph topology comparison (PD distribution across datasets)

Supports checkpointing so interrupted runs can resume.

Usage:
    python scripts/run_full_evaluation.py
    python scripts/run_full_evaluation.py --phase baseline
    python scripts/run_full_evaluation.py --phase generation --dataset enron
    python scripts/run_full_evaluation.py --resume
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = Path("configs/experiments/full_evaluation.yaml")
CHECKPOINT_DIR = Path("results/checkpoints")
PYTHON = sys.executable


def load_config(config_path: Path) -> dict[str, Any]:
    """Load experiment configuration from YAML."""
    with config_path.open() as f:
        return yaml.safe_load(f)


def save_checkpoint(phase: str, dataset: str, status: str) -> None:
    """Save a checkpoint for resume capability."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "phase": phase,
        "dataset": dataset,
        "status": status,
        "timestamp": datetime.now().isoformat(),
    }
    path = CHECKPOINT_DIR / f"{phase}_{dataset}.json"
    path.write_text(json.dumps(checkpoint, indent=2))
    logger.info("Checkpoint saved: %s/%s = %s", phase, dataset, status)


def check_checkpoint(phase: str, dataset: str) -> bool:
    """Check if a phase/dataset combo was already completed."""
    path = CHECKPOINT_DIR / f"{phase}_{dataset}.json"
    if not path.exists():
        return False
    checkpoint = json.loads(path.read_text())
    return checkpoint.get("status") == "completed"


def run_script(args: list[str], label: str) -> bool:
    """Run a subprocess and report success/failure."""
    click.echo(f"  $ {' '.join(args)}")
    result = subprocess.run(args, capture_output=False, text=True, timeout=3600)
    if result.returncode != 0:
        click.echo(f"  ERROR: {label} failed (exit code {result.returncode})")
        return False
    return True


def run_baseline(config: dict[str, Any], datasets: list[str], **conn) -> None:
    """Run cross-dataset baseline experiments."""
    baseline_cfg = config.get("baseline", {})
    pipelines = baseline_cfg.get("pipelines", [])
    n_queries = baseline_cfg.get("queries_per_dataset", 200)
    query_types = baseline_cfg.get("query_types", ["benign", "adversarial"])

    for dataset in datasets:
        if check_checkpoint("baseline", dataset):
            click.echo(f"  [skip] baseline/{dataset} already completed")
            continue

        click.echo(f"  Running baseline on {dataset}: "
                    f"{len(pipelines)} pipelines, {n_queries} queries")

        queries_flag = "both" if len(query_types) > 1 else query_types[0]
        variants = " ".join(f"-v {p}" for p in pipelines)

        success = run_script(
            [
                PYTHON, "scripts/run_experiments.py",
                "--dataset", dataset,
                "--queries", queries_flag,
                "--bootstrap",
                "--chroma-host", conn.get("chroma_host", "localhost"),
                "--chroma-port", str(conn.get("chroma_port", 8000)),
                "--neo4j-uri", conn.get("neo4j_uri", "bolt://localhost:7687"),
                "--neo4j-user", conn.get("neo4j_user", "neo4j"),
                "--neo4j-pass", conn.get("neo4j_pass", "pivorag_dev_2025"),
            ] + variants.split(),
            label=f"baseline/{dataset}",
        )
        if success:
            save_checkpoint("baseline", dataset, "completed")


def run_generation(config: dict[str, Any], datasets: list[str], **conn) -> None:
    """Run generation contamination experiments."""
    gen_cfg = config.get("generation", {})
    budget = gen_cfg.get("budget_usd", 50.0)

    for dataset in datasets:
        if check_checkpoint("generation", dataset):
            click.echo(f"  [skip] generation/{dataset} already completed")
            continue

        click.echo(f"  Running generation eval on {dataset}: budget=${budget:.2f}")

        success = run_script(
            [
                PYTHON, "scripts/run_generation_eval.py",
                "--dataset", dataset,
                "--llm", "all",
                "--budget", str(budget),
                "--chroma-host", conn.get("chroma_host", "localhost"),
                "--chroma-port", str(conn.get("chroma_port", 8000)),
                "--neo4j-uri", conn.get("neo4j_uri", "bolt://localhost:7687"),
                "--neo4j-user", conn.get("neo4j_user", "neo4j"),
                "--neo4j-pass", conn.get("neo4j_pass", "pivorag_dev_2025"),
            ],
            label=f"generation/{dataset}",
        )
        if success:
            save_checkpoint("generation", dataset, "completed")


def run_adaptive(config: dict[str, Any], datasets: list[str], **conn) -> None:
    """Run adaptive attacker experiments."""
    attack_cfg = config.get("adaptive_attacks", {})
    attacks = [a["name"] for a in attack_cfg.get("attacks", [])]
    pipelines = attack_cfg.get("target_pipelines", [])

    for dataset in datasets:
        if check_checkpoint("adaptive", dataset):
            click.echo(f"  [skip] adaptive/{dataset} already completed")
            continue

        click.echo(f"  Running adaptive attacks on {dataset}: "
                    f"{len(attacks)} attacks x {len(pipelines)} pipelines")

        attack_flags = []
        for a in attacks:
            # Map config names to CLI attack names
            if "A5" in a or "metadata" in a.lower():
                attack_flags.extend(["-a", "A5"])
            elif "A6" in a or "entity" in a.lower():
                attack_flags.extend(["-a", "A6"])
            elif "A7" in a or "query" in a.lower():
                attack_flags.extend(["-a", "A7"])

        pipeline_flags = []
        for p in pipelines:
            pipeline_flags.extend(["--target-pipelines", p])

        success = run_script(
            [
                PYTHON, "scripts/run_adaptive_attacks.py",
                "--dataset", dataset,
                "--chroma-host", conn.get("chroma_host", "localhost"),
                "--chroma-port", str(conn.get("chroma_port", 8000)),
                "--neo4j-uri", conn.get("neo4j_uri", "bolt://localhost:7687"),
                "--neo4j-user", conn.get("neo4j_user", "neo4j"),
                "--neo4j-pass", conn.get("neo4j_pass", "pivorag_dev_2025"),
            ] + attack_flags + pipeline_flags,
            label=f"adaptive/{dataset}",
        )
        if success:
            save_checkpoint("adaptive", dataset, "completed")


def run_topology(config: dict[str, Any], datasets: list[str], **conn) -> None:
    """Run graph topology comparison."""
    for dataset in datasets:
        if check_checkpoint("topology", dataset):
            click.echo(f"  [skip] topology/{dataset} already completed")
            continue

        click.echo(f"  Running topology analysis on {dataset}")

        success = run_script(
            [
                PYTHON, "scripts/run_sweep_experiments.py",
                "--traversal-sweep",
                "--connectivity-sweep",
                "--dataset", dataset,
                "--chroma-host", conn.get("chroma_host", "localhost"),
                "--chroma-port", str(conn.get("chroma_port", 8000)),
                "--neo4j-uri", conn.get("neo4j_uri", "bolt://localhost:7687"),
                "--neo4j-user", conn.get("neo4j_user", "neo4j"),
                "--neo4j-pass", conn.get("neo4j_pass", "pivorag_dev_2025"),
            ],
            label=f"topology/{dataset}",
        )
        if success:
            save_checkpoint("topology", dataset, "completed")


PHASES = {
    "baseline": run_baseline,
    "generation": run_generation,
    "adaptive": run_adaptive,
    "topology": run_topology,
}


@click.command()
@click.option("--config", "-c", default=str(DEFAULT_CONFIG),
              help="Path to experiment config YAML")
@click.option("--phase", "-p", default=None,
              type=click.Choice(list(PHASES.keys())),
              help="Run only a specific phase (default: all)")
@click.option("--dataset", "-d", default=None,
              type=click.Choice(["synthetic", "enron", "edgar"]),
              help="Run only a specific dataset (default: all)")
@click.option("--resume/--no-resume", default=True,
              help="Resume from checkpoints (default: True)")
@click.option("--clean", is_flag=True,
              help="Clear all checkpoints before running")
@click.option("--chroma-host", default="localhost")
@click.option("--chroma-port", default=8000, type=int)
@click.option("--neo4j-uri", default="bolt://localhost:7687")
@click.option("--neo4j-user", default="neo4j")
@click.option("--neo4j-pass", default="pivorag_dev_2025")
def main(
    config: str,
    phase: str | None,
    dataset: str | None,
    resume: bool,
    clean: bool,
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
) -> None:
    """Run the full PivoRAG evaluation suite."""
    logging.basicConfig(level=logging.INFO)
    start = time.perf_counter()

    cfg = load_config(Path(config))
    datasets = [dataset] if dataset else cfg.get("datasets", ["synthetic"])
    phases = [phase] if phase else list(PHASES.keys())

    if clean:
        import shutil
        if CHECKPOINT_DIR.exists():
            shutil.rmtree(CHECKPOINT_DIR)
        click.echo("Cleared all checkpoints.")

    if not resume:
        import shutil
        if CHECKPOINT_DIR.exists():
            shutil.rmtree(CHECKPOINT_DIR)

    conn = {
        "chroma_host": chroma_host,
        "chroma_port": chroma_port,
        "neo4j_uri": neo4j_uri,
        "neo4j_user": neo4j_user,
        "neo4j_pass": neo4j_pass,
    }

    click.echo("PivoRAG Full Evaluation Suite")
    click.echo(f"  Config: {config}")
    click.echo(f"  Datasets: {datasets}")
    click.echo(f"  Phases: {phases}")
    click.echo(f"  Resume: {resume}")
    click.echo()

    for p in phases:
        click.echo(f"=== Phase: {p} ===")
        PHASES[p](cfg, datasets, **conn)
        click.echo()

    elapsed = time.perf_counter() - start
    click.echo(f"Evaluation complete in {elapsed:.1f}s.")


if __name__ == "__main__":
    main()
