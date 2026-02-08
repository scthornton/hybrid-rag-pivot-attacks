#!/usr/bin/env python3
"""Run adaptive attacker experiments (A5-A7) across datasets and pipelines.

Tests whether D1 (per-hop authZ) is sufficient under an adaptive
attacker, or whether D4 (trust weighting) is necessary.

Usage:
    python scripts/run_adaptive_attacks.py --dataset synthetic
    python scripts/run_adaptive_attacks.py --dataset enron --attacks A5 A6
    python scripts/run_adaptive_attacks.py --dataset edgar --forgery-rates 0.01 0.05 0.1
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click

from pivorag.attacks.entity_manipulation import EntityManipulationAttack
from pivorag.attacks.metadata_forgery import MetadataForgeryAttack
from pivorag.attacks.query_manipulation import QueryManipulationAttack

logger = logging.getLogger(__name__)

ADAPTIVE_ATTACKS = {
    "A5": MetadataForgeryAttack,
    "A6": EntityManipulationAttack,
    "A7": QueryManipulationAttack,
}


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
@click.option("--output", "-o", default="results", help="Output directory")
@click.option("--seed", default=42, type=int, help="Random seed")
def main(
    dataset: str,
    attacks: tuple[str, ...],
    forgery_rates: tuple[float, ...],
    budget: int,
    output: str,
    seed: int,
) -> None:
    """Run adaptive attacker experiments for PivoRAG."""
    logging.basicConfig(level=logging.INFO)

    output_dir = Path(output) / "tables"
    output_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Adaptive attacks: dataset={dataset}, attacks={list(attacks)}")
    click.echo(f"Injection budget: {budget}, seed: {seed}")

    results = []

    for attack_name in attacks:
        attack_cls = ADAPTIVE_ATTACKS[attack_name]
        click.echo(f"\n--- {attack_name}: {attack_cls.__name__} ---")

        if attack_name == "A5":
            for rate in forgery_rates:
                attack = attack_cls(injection_budget=budget, forgery_rate=rate)
                payloads = attack.generate_payloads(
                    ["test query about infrastructure"],
                )
                forged = sum(
                    1 for p in payloads if p.metadata.get("is_forged")
                )
                result = {
                    "attack": attack_name,
                    "dataset": dataset,
                    "forgery_rate": rate,
                    "payloads": len(payloads),
                    "forged_count": forged,
                    "honest_count": len(payloads) - forged,
                }
                results.append(result)
                click.echo(
                    f"  rate={rate:.0%}: {forged}/{len(payloads)} forged"
                )
        else:
            attack = attack_cls(injection_budget=budget)
            payloads = attack.generate_payloads(
                ["test query about infrastructure"],
            )
            result = {
                "attack": attack_name,
                "dataset": dataset,
                "payloads": len(payloads),
                "is_query_attack": attack_name == "A7",
            }
            results.append(result)
            click.echo(f"  Generated {len(payloads)} payloads")

    summary_path = output_dir / f"adaptive_attacks_{dataset}.json"
    summary_path.write_text(json.dumps(results, indent=2))
    click.echo(f"\nResults saved to {summary_path}")
    click.echo(
        "Note: Full evaluation requires live Neo4j + ChromaDB services."
    )


if __name__ == "__main__":
    main()
