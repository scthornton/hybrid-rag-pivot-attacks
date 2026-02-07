#!/usr/bin/env python3
"""Generate synthetic enterprise dataset for pivorag experiments.

Creates a multi-tenant enterprise knowledge base with:
- Documents across 4 domains (engineering, finance, HR, security)
- 4 sensitivity tiers (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED)
- Bridge entities that create cross-tenant paths
- Realistic document templates using Faker

Usage:
    python scripts/make_synth_data.py --config configs/datasets/synthetic_enterprise.yaml
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import click
import yaml
from faker import Faker

fake = Faker()
Faker.seed(42)


DOMAIN_TEMPLATES = {
    "engineering": {
        "runbook": "Runbook: {title}\n\nSystem: {system}\nOwner: {owner}\n\n{content}",
        "architecture_doc": "Architecture: {title}\n\nComponents: {components}\n\n{content}",
        "code_doc": "API Documentation: {title}\n\nEndpoint: {endpoint}\n\n{content}",
    },
    "finance": {
        "budget": "Budget Report: {title}\n\nTotal: ${amount}\nPeriod: {period}\n\n{content}",
        "contract": "Contract: {title}\n\nVendor: {vendor}\nValue: ${amount}\n\n{content}",
    },
    "hr": {
        "policy": "HR Policy: {title}\n\nEffective: {date}\n\n{content}",
        "employee_record": "Employee: {name}\nDepartment: {dept}\nRole: {role}\n\n{content}",
    },
    "security": {
        "vuln_assessment": "Vulnerability Assessment: {title}\n\nCVE: {cve}\nSeverity: {severity}\n\n{content}",
        "incident_report": "Incident Report: {title}\n\nDate: {date}\nImpact: {impact}\n\n{content}",
    },
}


def generate_document(domain: str, doc_type: str, tenant: str, sensitivity: str) -> dict:
    """Generate a single synthetic document."""
    template = DOMAIN_TEMPLATES.get(domain, {}).get(doc_type, "{content}")
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"

    content = fake.paragraph(nb_sentences=8)
    text = template.format(
        title=fake.catch_phrase(),
        system=fake.word().capitalize() + "Service",
        owner=fake.name(),
        content=content,
        components=", ".join(fake.words(nb=4)),
        endpoint=f"/api/v1/{fake.word()}",
        amount=fake.random_int(min=10000, max=5000000),
        period=f"Q{fake.random_int(min=1, max=4)} {fake.year()}",
        vendor=fake.company(),
        date=fake.date_this_year().isoformat(),
        name=fake.name(),
        dept=fake.job(),
        role=fake.job(),
        cve=f"CVE-{fake.year()}-{fake.random_int(min=10000, max=99999)}",
        severity=fake.random_element(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
        impact=fake.random_element(["Low", "Medium", "High", "Critical"]),
    )

    return {
        "doc_id": doc_id,
        "title": fake.catch_phrase(),
        "text": text,
        "domain": domain,
        "doc_type": doc_type,
        "tenant": tenant,
        "sensitivity": sensitivity,
        "source": f"{domain}_system",
        "provenance_score": round(fake.pyfloat(min_value=0.5, max_value=1.0), 2),
    }


@click.command()
@click.option("--config", "-c", default="configs/datasets/synthetic_enterprise.yaml")
@click.option("--output", "-o", default="data/raw")
def main(config: str, output: str) -> None:
    """Generate synthetic enterprise dataset."""
    cfg = yaml.safe_load(Path(config).read_text())
    dataset_cfg = cfg.get("dataset", cfg)
    scale_cfg = dataset_cfg.get("scale", {})
    preset = scale_cfg.get("preset", "small")
    presets = scale_cfg.get("presets", {})
    params = presets.get(preset, {"total_documents": 1000})

    total_docs = params["total_documents"]
    click.echo(f"Generating {total_docs} documents (preset: {preset})")

    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    domains = dataset_cfg.get("domains", {})
    tiers = dataset_cfg.get("sensitivity_tiers", [])

    documents = []
    for i in range(total_docs):
        domain_name = list(domains.keys())[i % len(domains)]
        domain_cfg = domains[domain_name]
        doc_type = fake.random_element(list(DOMAIN_TEMPLATES.get(domain_name, {}).keys()) or ["doc"])
        tenant = domain_cfg.get("tenant", domain_name)

        # Assign sensitivity based on configured fractions
        tier_roll = fake.random.random()
        cumulative = 0.0
        sensitivity = "PUBLIC"
        for tier in tiers:
            cumulative += tier.get("fraction", 0.25)
            if tier_roll <= cumulative:
                sensitivity = tier["name"]
                break

        doc = generate_document(domain_name, doc_type, tenant, sensitivity)
        documents.append(doc)

    # Save documents
    output_file = output_dir / "synthetic_enterprise.json"
    output_file.write_text(json.dumps(documents, indent=2))
    click.echo(f"Saved {len(documents)} documents to {output_file}")

    # Save statistics
    stats = {
        "total_documents": len(documents),
        "preset": preset,
        "by_domain": {},
        "by_sensitivity": {},
        "by_tenant": {},
    }
    for doc in documents:
        stats["by_domain"][doc["domain"]] = stats["by_domain"].get(doc["domain"], 0) + 1
        stats["by_sensitivity"][doc["sensitivity"]] = stats["by_sensitivity"].get(doc["sensitivity"], 0) + 1
        stats["by_tenant"][doc["tenant"]] = stats["by_tenant"].get(doc["tenant"], 0) + 1

    stats_file = output_dir / "dataset_stats.json"
    stats_file.write_text(json.dumps(stats, indent=2))
    click.echo(f"Stats saved to {stats_file}")


if __name__ == "__main__":
    main()
