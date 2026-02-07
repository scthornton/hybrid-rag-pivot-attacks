#!/usr/bin/env python3
"""Export experiment results to publication-ready tables and plots.

Loads JSON results from experiment runs and generates:
- LaTeX tables for the paper (defense ablation, attack comparison)
- Matplotlib/seaborn plots (RPR bars, leakage distribution, context size)
- CSV summary for external analysis

Usage:
    python scripts/export_results.py --benign results/tables/experiment_benign_*.json \
                                     --adversarial results/tables/experiment_adversarial_*.json

    # Or auto-detect latest results:
    python scripts/export_results.py --latest
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import click
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

matplotlib.use("Agg")  # Non-interactive backend for file output

# ── Variant display metadata ────────────────────────────────────

VARIANT_LABELS = {
    "P1": "P1 (Vector-only)",
    "P3": "P3 (Hybrid)",
    "P4": "P4 (+D1)",
    "P5": "P5 (+D1,D2)",
    "P6": "P6 (+D1-D3)",
    "P7": "P7 (+D1-D4)",
    "P8": "P8 (All)",
}

VARIANT_ORDER = ["P1", "P3", "P4", "P5", "P6", "P7", "P8"]

# Color palette: red for vulnerable, green gradient for defended
VARIANT_COLORS = {
    "P1": "#4A90D9",   # Blue — baseline
    "P3": "#E74C3C",   # Red — vulnerable
    "P4": "#27AE60",   # Green — defended
    "P5": "#2ECC71",
    "P6": "#58D68D",
    "P7": "#82E0AA",
    "P8": "#A9DFBF",
}


def load_experiment(path: Path) -> dict:
    """Load a single experiment JSON file."""
    raw = json.loads(path.read_text())
    return raw["variants"]


def find_latest(results_dir: Path, query_set: str) -> Path | None:
    """Find the most recent experiment file for a query set."""
    candidates = sorted(results_dir.glob(f"experiment_{query_set}_*.json"))
    return candidates[-1] if candidates else None


# ── LaTeX Table Generation ──────────────────────────────────────

def generate_latex_defense_table(
    benign: dict, adversarial: dict, output_path: Path,
) -> None:
    """Generate LaTeX table for defense ablation results (Table 1 in paper)."""
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Defense ablation: security metrics across pipeline variants. "
        r"RPR = Retrieval Pivot Risk, Leak = mean Leakage@k, "
        r"PD = Pivot Depth (hops), Ctx = mean context size.}",
        r"\label{tab:defense-ablation}",
        r"\small",
        r"\begin{tabular}{l|cccc|cccc}",
        r"\toprule",
        r" & \multicolumn{4}{c|}{\textbf{Benign Queries}}"
        r" & \multicolumn{4}{c}{\textbf{Adversarial Queries}} \\",
        r"\textbf{Variant} & RPR & Leak & PD & Ctx"
        r" & RPR & Leak & PD & Ctx \\",
        r"\midrule",
    ]

    for variant in VARIANT_ORDER:
        if variant not in benign or variant not in adversarial:
            continue
        b_sec = benign[variant]["security"]
        a_sec = adversarial[variant]["security"]
        b_util = benign[variant]["utility"]
        a_util = adversarial[variant]["utility"]

        b_pd = _fmt_pd(b_sec["mean_pivot_depth"])
        a_pd = _fmt_pd(a_sec["mean_pivot_depth"])

        label = VARIANT_LABELS.get(variant, variant)
        lines.append(
            f"  {label} & {b_sec['rpr']:.3f} & {b_sec['mean_leakage']:.1f}"
            f" & {b_pd} & {b_util['mean_context_size']:.0f}"
            f" & {a_sec['rpr']:.3f} & {a_sec['mean_leakage']:.1f}"
            f" & {a_pd} & {a_util['mean_context_size']:.0f} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    output_path.write_text("\n".join(lines))
    click.echo(f"  LaTeX table: {output_path}")


def generate_latex_attack_table(attack_data: dict, output_path: Path) -> None:
    """Generate LaTeX table for attack experiment results (Table 2 in paper)."""
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Attack experiment results. AF = Amplification Factor "
        r"relative to clean P3 baseline.}",
        r"\label{tab:attack-results}",
        r"\small",
        r"\begin{tabular}{l|ccc|cc}",
        r"\toprule",
        r"\textbf{Attack} & \textbf{Payloads} & \textbf{Chunks} & \textbf{Entities}"
        r" & \textbf{P3 RPR} & \textbf{P4 RPR} \\",
        r"\midrule",
    ]

    for attack_name in ["A1", "A2", "A3", "A4"]:
        if attack_name not in attack_data:
            continue
        a = attack_data[attack_name]
        inj = a.get("injection_stats", {})
        p3 = a.get("P3_under_attack", {})
        p4 = a.get("P4_under_attack", {})
        lines.append(
            f"  {attack_name} & {a.get('payloads', 0)}"
            f" & {inj.get('chunks_injected', 0)}"
            f" & {inj.get('entities_resolved', 0)}"
            f" & {p3.get('rpr', 0):.3f}"
            f" & {p4.get('rpr', 0):.3f} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    output_path.write_text("\n".join(lines))
    click.echo(f"  LaTeX table: {output_path}")


def _fmt_pd(pd_val: float) -> str:
    """Format pivot depth for LaTeX: -1 becomes '--'."""
    if pd_val < 0:
        return "--"
    return f"{pd_val:.1f}"


# ── Plot Generation ─────────────────────────────────────────────

def plot_rpr_comparison(
    benign: dict, adversarial: dict, output_path: Path,
) -> None:
    """Bar chart comparing RPR across variants for benign vs adversarial."""
    variants = [v for v in VARIANT_ORDER if v in benign and v in adversarial]
    labels = [VARIANT_LABELS.get(v, v) for v in variants]
    b_rpr = [benign[v]["security"]["rpr"] for v in variants]
    a_rpr = [adversarial[v]["security"]["rpr"] for v in variants]

    x = np.arange(len(variants))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    bars_b = ax.bar(x - width / 2, b_rpr, width, label="Benign", color="#3498DB", alpha=0.85)
    bars_a = ax.bar(x + width / 2, a_rpr, width, label="Adversarial", color="#E74C3C", alpha=0.85)

    ax.set_ylabel("Retrieval Pivot Risk (RPR)", fontsize=12)
    ax.set_title("RPR Across Pipeline Variants", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.legend(fontsize=10)
    ax.set_ylim(0, 1.15)
    ax.axhline(y=0, color="gray", linewidth=0.5)

    # Value labels on bars
    for bar_group in [bars_b, bars_a]:
        for bar in bar_group:
            height = bar.get_height()
            if height > 0:
                ax.annotate(
                    f"{height:.2f}",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8,
                )

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    click.echo(f"  Plot: {output_path}")


def plot_leakage_distribution(
    adversarial: dict, output_path: Path,
) -> None:
    """Box/violin plot of per-query leakage distribution for P3."""
    if "P3" not in adversarial:
        return

    per_query = adversarial["P3"]["per_query"]
    leakages = [q["leakage_at_k"] for q in per_query]
    depths = [q["pivot_depth"] for q in per_query]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    # Leakage distribution
    ax1.bar(range(len(leakages)), leakages, color="#E74C3C", alpha=0.8)
    ax1.set_xlabel("Query Index", fontsize=11)
    ax1.set_ylabel("Leakage@k", fontsize=11)
    ax1.set_title("P3 Per-Query Leakage (Adversarial)", fontsize=12, fontweight="bold")
    ax1.axhline(y=np.mean(leakages), color="black", linestyle="--",
                linewidth=1, label=f"Mean: {np.mean(leakages):.1f}")
    ax1.legend(fontsize=9)

    # Pivot depth distribution (show finite values only)
    finite_depths = [d for d in depths if d != float("inf") and d > 0]
    if finite_depths:
        ax2.hist(finite_depths, bins=range(0, max(finite_depths) + 2),
                 color="#E74C3C", alpha=0.8, edgecolor="white")
        ax2.set_xlabel("Pivot Depth (hops)", fontsize=11)
        ax2.set_ylabel("Query Count", fontsize=11)
        ax2.set_title("P3 Pivot Depth Distribution", fontsize=12, fontweight="bold")
    else:
        ax2.text(0.5, 0.5, "No leakage", ha="center", va="center", transform=ax2.transAxes)

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    click.echo(f"  Plot: {output_path}")


def plot_context_size_reduction(
    benign: dict, adversarial: dict, output_path: Path,
) -> None:
    """Line chart showing how defenses progressively reduce context size."""
    variants = [v for v in VARIANT_ORDER if v in benign and v in adversarial]
    labels = [VARIANT_LABELS.get(v, v) for v in variants]
    b_ctx = [benign[v]["utility"]["mean_context_size"] for v in variants]
    a_ctx = [adversarial[v]["utility"]["mean_context_size"] for v in variants]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(labels, b_ctx, "o-", color="#3498DB", linewidth=2, markersize=8, label="Benign")
    ax.plot(labels, a_ctx, "s--", color="#E74C3C", linewidth=2, markersize=8, label="Adversarial")

    ax.set_ylabel("Mean Context Size (items)", fontsize=12)
    ax.set_title("Context Size Across Defense Configurations", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    plt.xticks(rotation=30, ha="right", fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    # Annotate key data points
    for i, (b, a) in enumerate(zip(b_ctx, a_ctx, strict=False)):
        ax.annotate(f"{b:.0f}", (i, b), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8, color="#3498DB")
        ax.annotate(f"{a:.0f}", (i, a), textcoords="offset points",
                    xytext=(0, -12), ha="center", fontsize=8, color="#E74C3C")

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    click.echo(f"  Plot: {output_path}")


def plot_defense_heatmap(
    benign: dict, adversarial: dict, output_path: Path,
) -> None:
    """Heatmap of security metrics across variants and query types."""
    variants = [v for v in VARIANT_ORDER if v in benign and v in adversarial]
    metrics = ["RPR", "Mean Leak", "Context Size"]

    data_b = []
    data_a = []
    for v in variants:
        b_s = benign[v]["security"]
        a_s = adversarial[v]["security"]
        b_u = benign[v]["utility"]
        a_u = adversarial[v]["utility"]
        data_b.append([b_s["rpr"], b_s["mean_leakage"], b_u["mean_context_size"]])
        data_a.append([a_s["rpr"], a_s["mean_leakage"], a_u["mean_context_size"]])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    labels = [VARIANT_LABELS.get(v, v) for v in variants]

    sns.heatmap(np.array(data_b), ax=ax1, annot=True, fmt=".2f",
                xticklabels=metrics, yticklabels=labels,
                cmap="RdYlGn_r", vmin=0)
    ax1.set_title("Benign Queries", fontsize=12, fontweight="bold")

    sns.heatmap(np.array(data_a), ax=ax2, annot=True, fmt=".2f",
                xticklabels=metrics, yticklabels=labels,
                cmap="RdYlGn_r", vmin=0)
    ax2.set_title("Adversarial Queries", fontsize=12, fontweight="bold")

    fig.suptitle("Security Metrics Heatmap", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    click.echo(f"  Plot: {output_path}")


# ── CSV Export ──────────────────────────────────────────────────

def export_csv(
    benign: dict, adversarial: dict, output_path: Path,
) -> None:
    """Export summary CSV for external analysis."""
    variants = [v for v in VARIANT_ORDER if v in benign and v in adversarial]

    with output_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "variant", "query_set", "rpr", "mean_leakage",
            "amplification_factor", "mean_pivot_depth",
            "queries_with_leakage", "total_queries",
            "p50_latency_ms", "p95_latency_ms", "mean_context_size",
        ])
        for qset_name, data in [("benign", benign), ("adversarial", adversarial)]:
            for v in variants:
                sec = data[v]["security"]
                util = data[v]["utility"]
                writer.writerow([
                    v, qset_name,
                    f"{sec['rpr']:.4f}",
                    f"{sec['mean_leakage']:.2f}",
                    f"{sec['amplification_factor']:.2f}",
                    f"{sec['mean_pivot_depth']:.2f}",
                    sec["queries_with_leakage"],
                    sec["total_queries"],
                    f"{util['p50_latency_ms']:.1f}",
                    f"{util['p95_latency_ms']:.1f}",
                    f"{util['mean_context_size']:.1f}",
                ])

    click.echo(f"  CSV: {output_path}")


# ── CLI ─────────────────────────────────────────────────────────

@click.command()
@click.option("--benign", "-b", type=click.Path(exists=True), help="Benign results JSON")
@click.option("--adversarial", "-a", type=click.Path(exists=True), help="Adversarial results JSON")
@click.option(
    "--attack-results", type=click.Path(exists=True),
    help="Attack experiment results JSON",
)
@click.option("--latest", is_flag=True, help="Auto-detect latest result files")
@click.option("--output", "-o", default="results", help="Output directory")
def main(
    benign: str | None,
    adversarial: str | None,
    attack_results: str | None,
    latest: bool,
    output: str,
) -> None:
    """Export experiment results to publication-ready tables and plots."""
    output_dir = Path(output)
    tables_dir = output_dir / "latex"
    plots_dir = output_dir / "plots"
    tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    results_dir = output_dir / "tables"

    # Auto-detect latest results
    if latest:
        benign_path = find_latest(results_dir, "benign")
        adv_path = find_latest(results_dir, "adversarial")
        attack_candidates = sorted(results_dir.glob("attack_experiments_*.json"))
        attack_path = attack_candidates[-1] if attack_candidates else None
    else:
        benign_path = Path(benign) if benign else None
        adv_path = Path(adversarial) if adversarial else None
        attack_path = Path(attack_results) if attack_results else None

    if not benign_path or not adv_path:
        click.echo("Error: Need both benign and adversarial results.")
        click.echo("Use --latest to auto-detect or specify paths with -b and -a.")
        return

    click.echo(f"Loading benign results:      {benign_path.name}")
    click.echo(f"Loading adversarial results:  {adv_path.name}")
    benign_data = load_experiment(benign_path)
    adv_data = load_experiment(adv_path)

    click.echo(f"\nGenerating outputs to {output_dir}/")

    # LaTeX tables
    click.echo("\n--- LaTeX Tables ---")
    generate_latex_defense_table(benign_data, adv_data, tables_dir / "defense_ablation.tex")

    if attack_path:
        click.echo(f"Loading attack results:       {attack_path.name}")
        attack_data = json.loads(attack_path.read_text())
        generate_latex_attack_table(attack_data, tables_dir / "attack_results.tex")

    # Plots
    click.echo("\n--- Plots ---")
    plot_rpr_comparison(benign_data, adv_data, plots_dir / "rpr_comparison.png")
    plot_leakage_distribution(adv_data, plots_dir / "leakage_distribution.png")
    plot_context_size_reduction(benign_data, adv_data, plots_dir / "context_size.png")
    plot_defense_heatmap(benign_data, adv_data, plots_dir / "defense_heatmap.png")

    # CSV
    click.echo("\n--- CSV ---")
    export_csv(benign_data, adv_data, output_dir / "experiment_summary.csv")

    click.echo("\nExport complete.")


if __name__ == "__main__":
    main()
