#!/usr/bin/env python3
"""E3: Organic leakage study — categorize leakage by bridge entity type.

Analyzes existing P3 experiment results (no injection) to determine which
categories of shared entities (bridge types) contribute most to cross-tenant
and over-clearance leakage.

Bridge categories from make_synth_data.py:
  - shared_vendor: CloudCorp, DataSyncInc, SecureNetLLC
  - shared_infrastructure: k8s-prod-cluster, splunk-siem, auth-service
  - shared_personnel: Maria Chen, James Rodriguez, Aisha Patel
  - shared_compliance: SOC2-audit, PCI-DSS-cert, ISO27001
  - shared_project: ProjectNexus, ProjectHorizon, ProjectArcade

Usage:
    python scripts/analyze_organic_leakage.py
    python scripts/analyze_organic_leakage.py \
        --experiment-file results/tables/experiment_benign.json
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import click

# ── Bridge entity signatures ──────────────────────────────────
# Canonical names from make_synth_data.py → patterns to match against
# entity IDs (format: ent_{canonical}_{LABEL}).

BRIDGE_SIGNATURES: dict[str, list[str]] = {
    "shared_vendor": [
        "cloudcorp", "datasync", "securenet",
    ],
    "shared_infrastructure": [
        "k8s", "splunk", "auth-service", "auth_service",
    ],
    "shared_personnel": [
        "maria_chen", "maria chen", "james_rodriguez", "james rodriguez",
        "aisha_patel", "aisha patel",
    ],
    "shared_compliance": [
        "soc2", "soc_2", "soc 2", "pci_dss", "pci-dss", "pci dss",
        "iso27001", "iso_27001", "iso 27001",
    ],
    "shared_project": [
        "projectnexus", "project_nexus", "project nexus",
        "projecthorizon", "project_horizon", "project horizon",
        "projectarcade", "project_arcade", "project arcade",
    ],
}


def classify_entity(entity_id: str) -> str | None:
    """Classify an entity ID into a bridge category, or None if not a bridge."""
    eid_lower = entity_id.lower()
    for category, signatures in BRIDGE_SIGNATURES.items():
        for sig in signatures:
            if sig in eid_lower:
                return category
    return None


def analyze_query(per_query_entry: dict) -> dict:
    """Analyze a single query's organic leakage path.

    Returns dict with:
      - has_leakage: bool
      - leakage_count: int
      - bridge_categories: list of bridge types found at hop 1
      - hop1_entities: list of entity IDs at hop 1
      - hop1_bridge_entities: list of (entity_id, category) tuples
    """
    leakage = per_query_entry.get("leakage_at_k", 0)
    traversal_log = per_query_entry.get("traversal_log", [])

    # Find graph_expansion step with node_depths
    node_depths = {}
    for step in traversal_log:
        if step.get("step") == "graph_expansion" and "node_depths" in step:
            node_depths = step["node_depths"]
            break

    # Identify hop-1 entity nodes (these are the pivot nodes)
    hop1_entities = [
        nid for nid, depth in node_depths.items()
        if depth == 1 and nid.startswith("ent_")
    ]

    # Classify each hop-1 entity
    bridge_entities = []
    bridge_categories = []
    for eid in hop1_entities:
        cat = classify_entity(eid)
        if cat:
            bridge_entities.append((eid, cat))
            bridge_categories.append(cat)

    return {
        "query_id": per_query_entry.get("query_id", ""),
        "query": per_query_entry.get("query", ""),
        "user_tenant": per_query_entry.get("user_tenant", ""),
        "has_leakage": leakage > 0,
        "leakage_count": leakage,
        "severity_weighted_leakage": per_query_entry.get("severity_weighted_leakage", 0),
        "cross_tenant_items": per_query_entry.get("cross_tenant_items", 0),
        "over_clearance_items": per_query_entry.get("over_clearance_items", 0),
        "hop1_entity_count": len(hop1_entities),
        "hop1_bridge_count": len(bridge_entities),
        "bridge_categories": bridge_categories,
        "bridge_entities": bridge_entities,
        "hop1_entities": hop1_entities,
    }


def run_analysis(experiment_file: str) -> dict:
    """Run E3 organic leakage analysis on a single experiment file."""
    data = json.loads(Path(experiment_file).read_text())

    # We only care about P3 (undefended hybrid) for organic leakage
    if "P3" not in data.get("variants", {}):
        click.echo(f"No P3 data in {experiment_file}")
        return {}

    p3 = data["variants"]["P3"]
    per_query = p3.get("per_query", [])

    click.echo(f"Analyzing {len(per_query)} P3 queries from {experiment_file}")

    # Analyze each query
    analyses = [analyze_query(pq) for pq in per_query]

    # Summary statistics
    total = len(analyses)
    leaking = [a for a in analyses if a["has_leakage"]]
    clean = [a for a in analyses if not a["has_leakage"]]

    # Bridge category breakdown (across all leaking queries)
    category_counts = Counter()
    category_leakage = defaultdict(float)  # total leakage attributed to each category
    for a in leaking:
        for cat in set(a["bridge_categories"]):  # unique categories per query
            category_counts[cat] += 1
        # Attribute leakage proportionally to bridge categories
        if a["bridge_categories"]:
            per_cat = a["leakage_count"] / len(set(a["bridge_categories"]))
            for cat in set(a["bridge_categories"]):
                category_leakage[cat] += per_cat

    # Queries with NO bridge entity at hop 1 but still have leakage
    # (leakage via non-bridge entities like MONEY, DATE, etc.)
    leaking_no_bridge = [a for a in leaking if not a["bridge_categories"]]
    leaking_with_bridge = [a for a in leaking if a["bridge_categories"]]

    # Bridge coverage analysis
    total_leakage = sum(a["leakage_count"] for a in leaking)

    # Hop-1 entity type analysis (all leaking queries)
    hop1_types = Counter()
    for a in leaking:
        for eid in a["hop1_entities"]:
            # Extract NER label from entity ID (last segment after final _)
            parts = eid.split("_")
            if len(parts) >= 2:
                label = parts[-1].upper()
                hop1_types[label] += 1

    results = {
        "experiment_file": str(experiment_file),
        "total_queries": total,
        "leaking_queries": len(leaking),
        "clean_queries": len(clean),
        "rpr": len(leaking) / total if total > 0 else 0.0,
        "total_leakage_items": total_leakage,
        "mean_leakage_per_query": total_leakage / total if total > 0 else 0.0,
        "mean_leakage_per_leaking_query": (
            total_leakage / len(leaking) if leaking else 0.0
        ),
        "bridge_category_breakdown": {
            "queries_with_bridge_in_path": len(leaking_with_bridge),
            "queries_without_bridge_in_path": len(leaking_no_bridge),
            "category_query_counts": dict(category_counts.most_common()),
            "category_attributed_leakage": {
                k: round(v, 1) for k, v in sorted(
                    category_leakage.items(), key=lambda x: -x[1]
                )
            },
        },
        "hop1_ner_type_distribution": dict(hop1_types.most_common()),
        "per_tenant_leakage": _per_tenant_stats(analyses),
    }

    return results


def _per_tenant_stats(analyses: list[dict]) -> dict:
    """Compute leakage stats per user tenant."""
    by_tenant = defaultdict(list)
    for a in analyses:
        by_tenant[a["user_tenant"]].append(a)

    stats = {}
    for tenant, items in sorted(by_tenant.items()):
        leaking = [a for a in items if a["has_leakage"]]
        total_leak = sum(a["leakage_count"] for a in leaking)
        cats = Counter()
        for a in leaking:
            for cat in set(a["bridge_categories"]):
                cats[cat] += 1
        stats[tenant] = {
            "total_queries": len(items),
            "leaking_queries": len(leaking),
            "rpr": round(len(leaking) / len(items), 3) if items else 0.0,
            "total_leakage": total_leak,
            "bridge_categories": dict(cats.most_common()),
        }
    return stats


def print_summary(results: dict, label: str = "") -> None:
    """Print a human-readable summary of E3 results."""
    click.echo(f"\n{'='*70}")
    click.echo(f"  E3: ORGANIC LEAKAGE ANALYSIS — {label.upper()}")
    click.echo(f"{'='*70}")

    click.echo(f"\nTotal queries:  {results['total_queries']}")
    click.echo(f"Leaking:        {results['leaking_queries']} ({results['rpr']:.1%})")
    click.echo(f"Clean:          {results['clean_queries']}")
    click.echo(f"Total leaked items: {results['total_leakage_items']}")
    click.echo(
        f"Mean leak/query:    {results['mean_leakage_per_query']:.2f} "
        f"(per leaking: {results['mean_leakage_per_leaking_query']:.2f})"
    )

    bd = results["bridge_category_breakdown"]
    click.echo("\n--- Bridge Category Breakdown ---")
    click.echo(
        f"Queries with bridge entity in path:    {bd['queries_with_bridge_in_path']}"
    )
    click.echo(
        f"Queries without bridge entity in path: {bd['queries_without_bridge_in_path']}"
    )

    click.echo("\nCategory query involvement (how many leaking queries involve each):")
    for cat, count in bd["category_query_counts"].items():
        pct = count / results["leaking_queries"] * 100 if results["leaking_queries"] else 0
        click.echo(f"  {cat:<25} {count:>4} queries ({pct:>5.1f}%)")

    click.echo("\nAttributed leakage by category:")
    for cat, leak in bd["category_attributed_leakage"].items():
        pct = leak / results["total_leakage_items"] * 100 if results["total_leakage_items"] else 0
        click.echo(f"  {cat:<25} {leak:>7.1f} items ({pct:>5.1f}%)")

    click.echo("\n--- Hop-1 Entity NER Types ---")
    for label, count in results["hop1_ner_type_distribution"].items():
        click.echo(f"  {label:<15} {count:>5}")

    click.echo("\n--- Per-Tenant Leakage ---")
    for tenant, stats in results["per_tenant_leakage"].items():
        click.echo(
            f"  {tenant:<25} RPR={stats['rpr']:.3f}  "
            f"leak={stats['total_leakage']:>4}  "
            f"bridges={stats['bridge_categories']}"
        )


@click.command()
@click.option(
    "--experiment-file", "-f",
    multiple=True,
    help="Experiment result JSON files to analyze. If none given, uses latest.",
)
@click.option("--output", "-o", default="results", help="Output directory")
def main(experiment_file: tuple[str, ...], output: str) -> None:
    """E3: Analyze organic leakage paths in undefended hybrid pipeline."""
    # Find experiment files
    if experiment_file:
        files = list(experiment_file)
    else:
        # Find latest benign and adversarial experiment files
        tables_dir = Path(output) / "tables"
        benign_files = sorted(tables_dir.glob("experiment_benign_*.json"))
        adversarial_files = sorted(tables_dir.glob("experiment_adversarial_*.json"))
        files = []
        if benign_files:
            files.append(str(benign_files[-1]))
        if adversarial_files:
            files.append(str(adversarial_files[-1]))

    if not files:
        click.echo("No experiment files found. Run experiments first.")
        return

    all_results = {}
    for f in files:
        label = "benign" if "benign" in f else "adversarial" if "adversarial" in f else "unknown"
        results = run_analysis(f)
        if results:
            all_results[label] = results
            print_summary(results, label)

    # Save combined results
    out_dir = Path(output) / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"organic_leakage_{timestamp}.json"
    out_path.write_text(json.dumps(all_results, indent=2, default=str))
    click.echo(f"\nResults saved to {out_path}")

    # Generate LaTeX table
    _generate_latex(all_results, Path(output) / "latex")


def _generate_latex(results: dict, latex_dir: Path) -> None:
    """Generate LaTeX table for organic leakage breakdown."""
    latex_dir.mkdir(parents=True, exist_ok=True)

    categories = [
        "shared_vendor", "shared_infrastructure", "shared_personnel",
        "shared_compliance", "shared_project",
    ]
    cat_labels = {
        "shared_vendor": "Vendor",
        "shared_infrastructure": "Infrastructure",
        "shared_personnel": "Personnel",
        "shared_compliance": "Compliance",
        "shared_project": "Project",
    }

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Organic leakage breakdown by bridge entity category under P3 (no injection). "
        r"Query involvement shows the fraction of leaking queries where that bridge type "
        r"appears at hop 1 in the traversal path.}",
        r"\label{tab:organic-leakage}",
        r"\small",
        r"\begin{tabular}{l|rr|rr}",
        r"\toprule",
        r"\textbf{Bridge Category} & \multicolumn{2}{c|}{\textbf{Benign}} "
        r"& \multicolumn{2}{c}{\textbf{Adversarial}} \\",
        r" & Queries & Leak & Queries & Leak \\",
        r"\midrule",
    ]

    benign = results.get("benign", {})
    adversarial = results.get("adversarial", {})

    for cat in categories:
        label = cat_labels[cat]
        b_queries = benign.get("bridge_category_breakdown", {}).get(
            "category_query_counts", {}
        ).get(cat, 0)
        b_leak = benign.get("bridge_category_breakdown", {}).get(
            "category_attributed_leakage", {}
        ).get(cat, 0.0)
        a_queries = adversarial.get("bridge_category_breakdown", {}).get(
            "category_query_counts", {}
        ).get(cat, 0)
        a_leak = adversarial.get("bridge_category_breakdown", {}).get(
            "category_attributed_leakage", {}
        ).get(cat, 0.0)
        lines.append(
            f"  {label} & {b_queries} & {b_leak:.0f} "
            f"& {a_queries} & {a_leak:.0f} \\\\"
        )

    # Totals
    b_total_q = benign.get("leaking_queries", 0)
    b_total_l = benign.get("total_leakage_items", 0)
    a_total_q = adversarial.get("leaking_queries", 0)
    a_total_l = adversarial.get("total_leakage_items", 0)
    lines.extend([
        r"\midrule",
        f"  Total & {b_total_q} & {b_total_l} & {a_total_q} & {a_total_l} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    path = latex_dir / "organic_leakage.tex"
    path.write_text("\n".join(lines) + "\n")
    click.echo(f"LaTeX table saved to {path}")


if __name__ == "__main__":
    main()
