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


# ── New Reviewer-Response Outputs ───────────────────────────────

def generate_latex_latency_table(
    benign: dict, adversarial: dict, output_path: Path,
) -> None:
    """Generate LaTeX latency table: variant → mean/p50/p95 latency, ctx size, RPR."""
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Latency and context size across pipeline variants. "
        r"Latency is measured in milliseconds.}",
        r"\label{tab:latency}",
        r"\small",
        r"\begin{tabular}{l|ccc|c|c}",
        r"\toprule",
        r"\textbf{Variant} & \textbf{p50} & \textbf{p95} & \textbf{Mean}"
        r" & \textbf{Ctx Size} & \textbf{RPR} \\",
        r"\midrule",
        r"\multicolumn{6}{c}{\textit{Benign Queries}} \\",
        r"\midrule",
    ]

    for variant in VARIANT_ORDER:
        if variant not in benign:
            continue
        util = benign[variant]["utility"]
        sec = benign[variant]["security"]
        mean_lat = (util["p50_latency_ms"] + util["p95_latency_ms"]) / 2
        lines.append(
            f"  {VARIANT_LABELS.get(variant, variant)}"
            f" & {util['p50_latency_ms']:.1f}"
            f" & {util['p95_latency_ms']:.1f}"
            f" & {mean_lat:.1f}"
            f" & {util['mean_context_size']:.0f}"
            f" & {sec['rpr']:.3f} \\\\"
        )

    lines.extend([
        r"\midrule",
        r"\multicolumn{6}{c}{\textit{Adversarial Queries}} \\",
        r"\midrule",
    ])

    for variant in VARIANT_ORDER:
        if variant not in adversarial:
            continue
        util = adversarial[variant]["utility"]
        sec = adversarial[variant]["security"]
        mean_lat = (util["p50_latency_ms"] + util["p95_latency_ms"]) / 2
        lines.append(
            f"  {VARIANT_LABELS.get(variant, variant)}"
            f" & {util['p50_latency_ms']:.1f}"
            f" & {util['p95_latency_ms']:.1f}"
            f" & {mean_lat:.1f}"
            f" & {util['mean_context_size']:.0f}"
            f" & {sec['rpr']:.3f} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    output_path.write_text("\n".join(lines))
    click.echo(f"  LaTeX table: {output_path}")


def generate_latex_attack_heatmap_table(
    attack_data: dict, output_path: Path,
) -> None:
    """Generate LaTeX attack × pipeline heatmap table.

    Expects attack_data keyed by attack type (A1-A4), each containing
    pipeline variant results.
    """
    pipelines = ["P3", "P4", "P6", "P8"]
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{RPR under each attack type across pipeline variants. "
        r"Leakage@k shown in parentheses.}",
        r"\label{tab:attack-heatmap}",
        r"\small",
        r"\begin{tabular}{l|" + "c" * len(pipelines) + "}",
        r"\toprule",
        r"\textbf{Attack} & " + " & ".join(
            rf"\textbf{{{p}}}" for p in pipelines
        ) + r" \\",
        r"\midrule",
    ]

    for attack in ["A1", "A2", "A3", "A4"]:
        if attack not in attack_data:
            continue
        a = attack_data[attack]
        cells = []
        for pipe in pipelines:
            key = f"{pipe}_under_attack"
            if key in a:
                rpr = a[key].get("rpr", 0)
                leak = a[key].get("mean_leakage", 0)
                cells.append(f"{rpr:.2f} ({leak:.1f})")
            else:
                cells.append("--")
        lines.append(f"  {attack} & " + " & ".join(cells) + r" \\")

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    output_path.write_text("\n".join(lines))
    click.echo(f"  LaTeX table: {output_path}")


def plot_connectivity_sweep(
    sweep_data: dict, output_path: Path,
) -> None:
    """Line plot: shared-entity count → RPR for benign and adversarial.

    sweep_data: {bridge_count: {"benign": {rpr, leakage}, "adversarial": {rpr, leakage}}}
    """
    counts = sorted(sweep_data.keys(), key=int)
    b_rpr = [sweep_data[c]["benign"]["rpr"] for c in counts]
    a_rpr = [sweep_data[c]["adversarial"]["rpr"] for c in counts]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(counts, b_rpr, "o-", color="#3498DB", linewidth=2,
            markersize=8, label="Benign")
    ax.plot(counts, a_rpr, "s--", color="#E74C3C", linewidth=2,
            markersize=8, label="Adversarial")

    ax.set_xlabel("Number of Shared Bridge Entities", fontsize=12)
    ax.set_ylabel("Retrieval Pivot Risk (RPR)", fontsize=12)
    ax.set_title("RPR vs. Cross-Tenant Entity Connectivity",
                 fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.set_ylim(-0.05, 1.15)
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    click.echo(f"  Plot: {output_path}")


def plot_pd_distribution(
    adversarial: dict, output_path: Path,
) -> None:
    """Box plot of pivot depth distribution across pipeline variants."""
    variants = [v for v in VARIANT_ORDER if v in adversarial]

    all_depths = []
    variant_labels = []
    for v in variants:
        per_query = adversarial[v]["per_query"]
        for q in per_query:
            pd = q.get("pivot_depth", float("inf"))
            if pd != float("inf") and pd >= 0:
                all_depths.append(pd)
                variant_labels.append(VARIANT_LABELS.get(v, v))

    if not all_depths:
        click.echo("  Skipping PD distribution plot (no finite depths)")
        return

    fig, ax = plt.subplots(figsize=(10, 5))

    # Group by variant
    import pandas as pd
    df = pd.DataFrame({"Pivot Depth": all_depths, "Variant": variant_labels})
    sns.boxplot(data=df, x="Variant", y="Pivot Depth", ax=ax,
                palette=[VARIANT_COLORS.get(v, "#999999") for v in variants
                         if VARIANT_LABELS.get(v, v) in variant_labels])

    ax.set_ylabel("Pivot Depth (hops)", fontsize=12)
    ax.set_title("Pivot Depth Distribution by Pipeline Variant",
                 fontsize=14, fontweight="bold")
    plt.xticks(rotation=30, ha="right", fontsize=9)

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    click.echo(f"  Plot: {output_path}")


def plot_rpr_with_ci(
    benign: dict, adversarial: dict, output_path: Path,
) -> None:
    """Bar chart of RPR with bootstrap 95% CI error bars."""
    variants = [v for v in VARIANT_ORDER if v in benign and v in adversarial]
    labels = [VARIANT_LABELS.get(v, v) for v in variants]

    b_rpr = [benign[v]["security"]["rpr"] for v in variants]
    a_rpr = [adversarial[v]["security"]["rpr"] for v in variants]

    # Extract CIs if available
    b_err = []
    a_err = []
    has_ci = False
    for v in variants:
        b_ci = benign[v]["security"].get("rpr_ci")
        a_ci = adversarial[v]["security"].get("rpr_ci")
        if b_ci and len(b_ci) == 3:
            has_ci = True
            b_err.append([b_ci[0] - b_ci[1], b_ci[2] - b_ci[0]])
            a_err.append([a_ci[0] - a_ci[1], a_ci[2] - a_ci[0]])
        else:
            b_err.append([0, 0])
            a_err.append([0, 0])

    x = np.arange(len(variants))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))

    if has_ci:
        b_yerr = np.array(b_err).T
        a_yerr = np.array(a_err).T
        ax.bar(x - width / 2, b_rpr, width, label="Benign",
               color="#3498DB", alpha=0.85, yerr=b_yerr, capsize=4)
        ax.bar(x + width / 2, a_rpr, width, label="Adversarial",
               color="#E74C3C", alpha=0.85, yerr=a_yerr, capsize=4)
    else:
        ax.bar(x - width / 2, b_rpr, width, label="Benign",
               color="#3498DB", alpha=0.85)
        ax.bar(x + width / 2, a_rpr, width, label="Adversarial",
               color="#E74C3C", alpha=0.85)

    ax.set_ylabel("Retrieval Pivot Risk (RPR)", fontsize=12)
    title = "RPR Across Pipeline Variants"
    if has_ci:
        title += " (with 95% CI)"
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.legend(fontsize=10)
    ax.set_ylim(0, 1.15)

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    click.echo(f"  Plot: {output_path}")


def plot_traversal_sweep(
    sweep_data: list[dict], output_path: Path,
) -> None:
    """Pareto scatter: context_size × latency, colored by RPR.

    sweep_data: list of {depth, branching, total_nodes, rpr, leakage, ctx_size, latency_ms}
    """
    if not sweep_data:
        click.echo("  Skipping traversal sweep plot (no data)")
        return

    ctx_sizes = [d["ctx_size"] for d in sweep_data]
    latencies = [d["latency_ms"] for d in sweep_data]
    rprs = [d["rpr"] for d in sweep_data]

    fig, ax = plt.subplots(figsize=(8, 6))
    scatter = ax.scatter(ctx_sizes, latencies, c=rprs, cmap="RdYlGn_r",
                         s=100, edgecolor="black", linewidth=0.5, vmin=0, vmax=1)
    fig.colorbar(scatter, ax=ax, label="RPR")

    ax.set_xlabel("Context Size (items)", fontsize=12)
    ax.set_ylabel("Latency (ms)", fontsize=12)
    ax.set_title("Traversal Parameter Space: Context × Latency × RPR",
                 fontsize=14, fontweight="bold")

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    click.echo(f"  Plot: {output_path}")


def plot_mislabel_rate(
    mislabel_data: dict, output_path: Path,
) -> None:
    """Line plot: mislabel rate → RPR under D1 defense.

    mislabel_data: {rate_pct: {"rpr": float, "mean_leakage": float}}
    """
    if not mislabel_data:
        click.echo("  Skipping mislabel plot (no data)")
        return

    rates = sorted(mislabel_data.keys(), key=float)
    rprs = [mislabel_data[r]["rpr"] for r in rates]
    leakages = [mislabel_data[r]["mean_leakage"] for r in rates]

    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax2 = ax1.twinx()

    l1 = ax1.plot(rates, rprs, "o-", color="#E74C3C", linewidth=2,
                  markersize=8, label="RPR")
    l2 = ax2.plot(rates, leakages, "s--", color="#3498DB", linewidth=2,
                  markersize=8, label="Mean Leakage@k")

    ax1.set_xlabel("Mislabel Rate (%)", fontsize=12)
    ax1.set_ylabel("RPR", fontsize=12, color="#E74C3C")
    ax2.set_ylabel("Mean Leakage@k", fontsize=12, color="#3498DB")
    ax1.set_title("D1 Defense Under Metadata Mislabeling",
                  fontsize=14, fontweight="bold")

    lines = l1 + l2
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, fontsize=10, loc="upper left")

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    click.echo(f"  Plot: {output_path}")


# ── CSV Export ──────────────────────────────────────────────────

def export_csv(
    benign: dict, adversarial: dict, output_path: Path,
) -> None:
    """Export summary CSV for external analysis (extended with new metrics)."""
    variants = [v for v in VARIANT_ORDER if v in benign and v in adversarial]

    with output_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "variant", "query_set", "rpr", "mean_leakage",
            "amplification_factor", "af_epsilon", "delta_leakage",
            "severity_weighted_leakage", "mean_pivot_depth",
            "pd_min", "pd_median", "pd_max",
            "queries_with_leakage", "total_queries",
            "p50_latency_ms", "p95_latency_ms", "mean_context_size",
            "rpr_ci_low", "rpr_ci_high",
        ])
        for qset_name, data in [("benign", benign), ("adversarial", adversarial)]:
            for v in variants:
                sec = data[v]["security"]
                util = data[v]["utility"]
                pd_dist = sec.get("pd_distribution", {})
                rpr_ci = sec.get("rpr_ci")
                writer.writerow([
                    v, qset_name,
                    f"{sec['rpr']:.4f}",
                    f"{sec['mean_leakage']:.2f}",
                    f"{sec['amplification_factor']:.2f}",
                    f"{sec.get('af_epsilon', 0):.2f}",
                    f"{sec.get('delta_leakage', 0):.2f}",
                    f"{sec.get('mean_severity_weighted_leakage', 0):.2f}",
                    f"{sec['mean_pivot_depth']:.2f}",
                    f"{pd_dist.get('min', -1):.1f}",
                    f"{pd_dist.get('median', -1):.1f}",
                    f"{pd_dist.get('max', -1):.1f}",
                    sec["queries_with_leakage"],
                    sec["total_queries"],
                    f"{util['p50_latency_ms']:.1f}",
                    f"{util['p95_latency_ms']:.1f}",
                    f"{util['mean_context_size']:.1f}",
                    f"{rpr_ci[1]:.4f}" if rpr_ci else "",
                    f"{rpr_ci[2]:.4f}" if rpr_ci else "",
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
@click.option(
    "--sweep-results", type=click.Path(exists=True),
    help="Connectivity sweep results JSON",
)
@click.option(
    "--traversal-sweep", type=click.Path(exists=True),
    help="Traversal regime sweep results JSON",
)
@click.option(
    "--mislabel-results", type=click.Path(exists=True),
    help="Metadata mislabel stress test results JSON",
)
@click.option("--latest", is_flag=True, help="Auto-detect latest result files")
@click.option("--output", "-o", default="results", help="Output directory")
def main(
    benign: str | None,
    adversarial: str | None,
    attack_results: str | None,
    sweep_results: str | None,
    traversal_sweep: str | None,
    mislabel_results: str | None,
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
        sweep_candidates = sorted(results_dir.glob("connectivity_sweep_*.json"))
        sweep_path = sweep_candidates[-1] if sweep_candidates else None
        trav_candidates = sorted(results_dir.glob("traversal_sweep_*.json"))
        trav_path = trav_candidates[-1] if trav_candidates else None
        mis_candidates = sorted(results_dir.glob("mislabel_stress_*.json"))
        mis_path = mis_candidates[-1] if mis_candidates else None
    else:
        benign_path = Path(benign) if benign else None
        adv_path = Path(adversarial) if adversarial else None
        attack_path = Path(attack_results) if attack_results else None
        sweep_path = Path(sweep_results) if sweep_results else None
        trav_path = Path(traversal_sweep) if traversal_sweep else None
        mis_path = Path(mislabel_results) if mislabel_results else None

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
    generate_latex_defense_table(
        benign_data, adv_data, tables_dir / "defense_ablation.tex",
    )
    generate_latex_latency_table(
        benign_data, adv_data, tables_dir / "latency.tex",
    )

    if attack_path:
        click.echo(f"Loading attack results:       {attack_path.name}")
        attack_data = json.loads(attack_path.read_text())
        generate_latex_attack_table(attack_data, tables_dir / "attack_results.tex")
        generate_latex_attack_heatmap_table(
            attack_data, tables_dir / "attack_heatmap.tex",
        )

    # Plots
    click.echo("\n--- Plots ---")
    plot_rpr_comparison(benign_data, adv_data, plots_dir / "rpr_comparison.png")
    plot_rpr_with_ci(benign_data, adv_data, plots_dir / "rpr_with_ci.png")
    plot_leakage_distribution(adv_data, plots_dir / "leakage_distribution.png")
    plot_context_size_reduction(benign_data, adv_data, plots_dir / "context_size.png")
    plot_defense_heatmap(benign_data, adv_data, plots_dir / "defense_heatmap.png")
    plot_pd_distribution(adv_data, plots_dir / "pd_distribution.png")

    # Optional sweep plots
    if sweep_path:
        click.echo(f"Loading sweep results:        {sweep_path.name}")
        sweep_data = json.loads(sweep_path.read_text())
        plot_connectivity_sweep(sweep_data, plots_dir / "connectivity_sweep.png")

    if trav_path:
        click.echo(f"Loading traversal sweep:      {trav_path.name}")
        trav_data = json.loads(trav_path.read_text())
        plot_traversal_sweep(trav_data, plots_dir / "traversal_pareto.png")

    if mis_path:
        click.echo(f"Loading mislabel results:     {mis_path.name}")
        mis_data = json.loads(mis_path.read_text())
        plot_mislabel_rate(mis_data, plots_dir / "mislabel_rate.png")

    # CSV
    click.echo("\n--- CSV ---")
    export_csv(benign_data, adv_data, output_dir / "experiment_summary.csv")

    click.echo("\nExport complete.")


if __name__ == "__main__":
    main()
