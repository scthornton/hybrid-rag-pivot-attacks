#!/usr/bin/env python3
"""Download and prepare the Enron Email Corpus for pivorag experiments.

Downloads the Kaggle Enron email dataset, validates the CSV structure,
and reports statistics on tenant and sensitivity distribution.

Prerequisites:
    pip install kaggle
    Set KAGGLE_USERNAME and KAGGLE_KEY environment variables, or
    place kaggle.json in ~/.kaggle/

Usage:
    python scripts/ingest_enron.py
    python scripts/ingest_enron.py --output data/raw/enron --max-emails 50000
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import click


@click.command()
@click.option("--output", "-o", default="data/raw/enron", help="Output directory")
@click.option("--max-emails", default=50_000, type=int, help="Max emails to load for stats")
@click.option("--skip-download", is_flag=True, help="Skip download, just compute stats")
def main(output: str, max_emails: int, skip_download: bool) -> None:
    """Download and prepare the Enron email corpus."""
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "emails.csv"

    if not skip_download and not csv_path.exists():
        click.echo("Downloading Enron email dataset from Kaggle...")
        try:
            subprocess.run(
                [
                    sys.executable, "-m", "kaggle", "datasets", "download",
                    "-d", "wcukierski/enron-email-dataset",
                    "-p", str(output_dir),
                    "--unzip",
                ],
                check=True,
            )
        except FileNotFoundError as exc:
            click.echo(
                "kaggle CLI not found. Install with: pip install kaggle\n"
                "Then set KAGGLE_USERNAME and KAGGLE_KEY env vars.",
                err=True,
            )
            raise SystemExit(1) from exc
        except subprocess.CalledProcessError as exc:
            click.echo(f"Download failed: {exc}", err=True)
            raise SystemExit(1) from exc

    if not csv_path.exists():
        click.echo(f"Expected CSV at {csv_path} but not found.", err=True)
        raise SystemExit(1)

    click.echo(f"CSV found at {csv_path}")

    # Compute stats using the adapter
    from pivorag.datasets.enron import EnronEmailAdapter

    adapter = EnronEmailAdapter(
        data_dir=output_dir,
        max_emails=max_emails,
    )

    click.echo("Loading and parsing emails (this may take a few minutes)...")
    docs = adapter.load_documents()
    stats = adapter.get_stats(docs)

    stats_file = output_dir / "dataset_stats.json"
    stats_data = {
        "total_documents": stats.total_documents,
        "tenants": stats.tenants,
        "sensitivity_distribution": stats.sensitivity_distribution,
        "bridge_entity_count": stats.bridge_entity_count,
        "metadata": stats.metadata,
    }
    stats_file.write_text(json.dumps(stats_data, indent=2))

    click.echo(f"\nLoaded {stats.total_documents} emails")
    click.echo(f"Tenants: {stats.tenants}")
    click.echo(f"Sensitivity distribution: {json.dumps(stats.sensitivity_distribution, indent=2)}")
    click.echo(f"Bridge entities: {stats.bridge_entity_count}")
    click.echo(f"Stats saved to {stats_file}")


if __name__ == "__main__":
    main()
