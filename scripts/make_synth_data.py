#!/usr/bin/env python3
"""Generate synthetic enterprise dataset for pivorag experiments.

Creates a multi-tenant enterprise knowledge base with:
- Documents across 4 domains (engineering, finance, HR, security)
- 4 sensitivity tiers (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED)
- 15 bridge entities that create cross-tenant graph paths
- Entity-rich document templates with ground truth annotations
- Reproducible output via fixed random seed

Usage:
    python scripts/make_synth_data.py --config configs/datasets/synthetic_enterprise.yaml
    python scripts/make_synth_data.py --scale small --output data/raw
    python scripts/make_synth_data.py --scale large --output data/raw --stats
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import click
import yaml
from faker import Faker

fake = Faker()

# ---------------------------------------------------------------------------
# Curated Entity Pools — realistic names that spaCy NER can actually extract
# ---------------------------------------------------------------------------

ENGINEERING_SYSTEMS = [
    "k8s-prod-cluster", "payment-gateway", "api-gateway", "data-pipeline",
    "auth-service", "notification-engine", "logging-stack", "ci-cd-runner",
    "cache-layer", "message-broker", "search-indexer", "cdn-edge",
]

ENGINEERING_TECHNOLOGIES = [
    "Kubernetes", "Docker", "PostgreSQL", "Redis", "Kafka",
    "Elasticsearch", "Terraform", "ArgoCD", "Prometheus", "Grafana",
    "NGINX", "RabbitMQ", "MongoDB", "Consul", "Vault",
]

ENGINEERING_PROJECTS = [
    "Project Alpha", "Project Bravo", "Platform Migration",
    "Microservices Refactor", "Zero-Downtime Deploy", "Observability Initiative",
]

FINANCE_VENDORS = [
    "Accenture", "Deloitte", "KPMG", "Ernst & Young",
    "McKinsey", "Boston Consulting Group", "Bain & Company",
    "Gartner", "Forrester", "IDC",
]

FINANCE_ACCOUNTS = [
    "Operating Budget Q3", "Capital Expenditure 2025", "R&D Allocation",
    "Cloud Infrastructure Spend", "SaaS License Pool", "Contingency Reserve",
]

FINANCE_REGULATIONS = [
    "SOX", "GAAP", "IFRS", "SEC Rule 10b-5",
    "Dodd-Frank Act", "Basel III", "FATCA",
]

HR_DEPARTMENTS = [
    "Engineering", "Product", "Design", "Data Science",
    "Sales", "Marketing", "Legal", "Finance", "Operations",
    "Customer Success", "Security", "DevOps",
]

HR_BENEFITS = [
    "401k matching", "health insurance", "stock options", "RSU vesting",
    "parental leave", "education stipend", "wellness program",
]

SECURITY_CVES = [
    "CVE-2025-41923", "CVE-2025-38104", "CVE-2025-29876",
    "CVE-2024-51032", "CVE-2024-44891", "CVE-2024-37652",
    "CVE-2025-15234", "CVE-2025-22789", "CVE-2025-33456",
]

SECURITY_TOOLS = [
    "Splunk SIEM", "CrowdStrike Falcon", "Tenable Nessus",
    "Burp Suite", "Metasploit", "Wireshark",
    "Snort IDS", "OSSEC", "Qualys", "SentinelOne",
]

SECURITY_FRAMEWORKS = [
    "NIST CSF", "MITRE ATT&CK", "CIS Controls",
    "ISO 27001", "PCI DSS", "OWASP Top 10",
]

# ---------------------------------------------------------------------------
# Bridge Entities — shared across tenants to create cross-boundary graph paths
# ---------------------------------------------------------------------------

BRIDGE_ENTITIES = {
    "shared_vendor": [
        {"name": "CloudCorp", "connects": ["acme_engineering", "globex_finance"],
         "mention_as": ["CloudCorp", "CloudCorp Inc", "CloudCorp Solutions"]},
        {"name": "DataSyncInc", "connects": ["acme_engineering", "globex_finance"],
         "mention_as": ["DataSync Inc", "DataSync", "DataSyncInc"]},
        {"name": "SecureNetLLC", "connects": ["acme_engineering", "globex_finance"],
         "mention_as": ["SecureNet LLC", "SecureNet", "SecureNetLLC"]},
    ],
    "shared_infrastructure": [
        {"name": "k8s-prod-cluster", "connects": ["acme_engineering", "umbrella_security"],
         "mention_as": ["k8s-prod-cluster", "production Kubernetes cluster", "k8s prod cluster"]},
        {"name": "splunk-siem", "connects": ["acme_engineering", "umbrella_security"],
         "mention_as": ["Splunk SIEM", "Splunk", "the SIEM platform"]},
        {"name": "auth-service", "connects": ["acme_engineering", "umbrella_security"],
         "mention_as": ["auth-service", "authentication service", "auth service"]},
    ],
    "shared_personnel": [
        {"name": "Maria Chen", "connects": ["initech_hr", "acme_engineering"],
         "mention_as": ["Maria Chen", "M. Chen", "Chen"]},
        {"name": "James Rodriguez", "connects": ["initech_hr", "acme_engineering"],
         "mention_as": ["James Rodriguez", "J. Rodriguez", "Rodriguez"]},
        {"name": "Aisha Patel", "connects": ["initech_hr", "acme_engineering"],
         "mention_as": ["Aisha Patel", "A. Patel", "Patel"]},
    ],
    "shared_compliance": [
        {"name": "SOC2-audit", "connects": ["globex_finance", "umbrella_security"],
         "mention_as": ["SOC 2 audit", "SOC2 audit", "SOC 2 Type II"]},
        {"name": "PCI-DSS-cert", "connects": ["globex_finance", "umbrella_security"],
         "mention_as": ["PCI DSS certification", "PCI DSS", "PCI compliance"]},
        {"name": "ISO27001", "connects": ["globex_finance", "umbrella_security"],
         "mention_as": ["ISO 27001", "ISO 27001 certification", "ISO27001"]},
    ],
    "shared_project": [
        {"name": "ProjectNexus", "connects": ["acme_engineering", "globex_finance", "initech_hr"],
         "mention_as": ["Project Nexus", "ProjectNexus", "Nexus initiative"]},
        {"name": "ProjectHorizon",
         "connects": ["acme_engineering", "globex_finance", "initech_hr"],
         "mention_as": ["Project Horizon", "ProjectHorizon", "Horizon program"]},
        {"name": "ProjectArcade",
         "connects": ["acme_engineering", "globex_finance", "initech_hr"],
         "mention_as": ["Project Arcade", "ProjectArcade", "Arcade initiative"]},
    ],
}

# Flatten for quick lookup
ALL_BRIDGE_ENTITIES: list[dict] = []
for bridge_type, entities in BRIDGE_ENTITIES.items():
    for entity in entities:
        ALL_BRIDGE_ENTITIES.append({**entity, "type": bridge_type})


# Extra bridge entity pools for counts > 15
EXTRA_VENDOR_NAMES = [
    "TechVault", "InfraPrime", "NetScale", "CloudBridge",
    "DataForge", "CyberShield", "QuantumOps", "NexaFlow",
    "CoreSync", "VaultEdge", "StreamLine", "PlatformX",
    "OmniStack", "GridLock", "ByteForce",
]

EXTRA_INFRA_NAMES = [
    "monitoring-hub", "backup-controller", "dns-resolver",
    "vpn-gateway", "load-balancer-v2", "secrets-vault",
    "artifact-registry", "feature-flag-service", "rate-limiter",
    "identity-provider", "config-server", "audit-logger",
]

EXTRA_PERSONNEL_NAMES = [
    "Daniel Park", "Nadia Petrova", "Raj Kapoor",
    "Samantha Lee", "Omar Hassan", "Priya Sharma",
    "Thomas Müller", "Yuki Tanaka", "Liam O'Connor",
    "Sofia Reyes", "Chen Wei", "Anna Kowalski",
]

EXTRA_COMPLIANCE_NAMES = [
    "HIPAA-audit", "FedRAMP-cert", "GDPR-program",
    "CCPA-compliance", "NIST-800-53", "SOX-certification",
]

EXTRA_PROJECT_NAMES = [
    "ProjectZenith", "ProjectMercury", "ProjectOdyssey",
    "ProjectVanguard", "ProjectCatalyst", "ProjectEclipse",
]


def _generate_extra_bridges(count: int) -> list[dict]:
    """Generate additional bridge entities beyond the base 15.

    Cycles through extra pools (vendor, infra, personnel, compliance, project)
    to produce cross-tenant bridge entities programmatically.
    """
    tenant_pairs = [
        ("acme_engineering", "globex_finance"),
        ("acme_engineering", "umbrella_security"),
        ("initech_hr", "acme_engineering"),
        ("globex_finance", "umbrella_security"),
        ("acme_engineering", "globex_finance", "initech_hr"),
    ]

    extra_pools = [
        ("shared_vendor", EXTRA_VENDOR_NAMES),
        ("shared_infrastructure", EXTRA_INFRA_NAMES),
        ("shared_personnel", EXTRA_PERSONNEL_NAMES),
        ("shared_compliance", EXTRA_COMPLIANCE_NAMES),
        ("shared_project", EXTRA_PROJECT_NAMES),
    ]

    extras = []
    pool_idx = 0
    name_idx_per_pool = {bt: 0 for bt, _ in extra_pools}

    for i in range(count):
        bridge_type, pool = extra_pools[pool_idx % len(extra_pools)]
        name_idx = name_idx_per_pool[bridge_type]
        if name_idx >= len(pool):
            pool_idx += 1
            continue
        name = pool[name_idx]
        name_idx_per_pool[bridge_type] = name_idx + 1

        connects = list(tenant_pairs[i % len(tenant_pairs)])
        mention_variants = [name, name.replace("-", " "), name.replace("-", "_")]

        extras.append({
            "name": name,
            "type": bridge_type,
            "connects": connects,
            "mention_as": mention_variants,
        })
        pool_idx += 1

    return extras


def get_bridge_entities(bridge_count: int | None = None) -> list[dict]:
    """Get the bridge entity list, optionally limited or extended.

    - None or 15: use the default 15 bridge entities
    - 0-14: take first N from the default list
    - 16-40+: default 15 + programmatically generated extras
    """
    if bridge_count is None:
        return list(ALL_BRIDGE_ENTITIES)

    if bridge_count <= len(ALL_BRIDGE_ENTITIES):
        return ALL_BRIDGE_ENTITIES[:bridge_count]

    extra_needed = bridge_count - len(ALL_BRIDGE_ENTITIES)
    extras = _generate_extra_bridges(extra_needed)
    return list(ALL_BRIDGE_ENTITIES) + extras

# ---------------------------------------------------------------------------
# Named employees — consistent across documents for graph connectivity
# ---------------------------------------------------------------------------

NAMED_EMPLOYEES = [
    {"name": "Maria Chen", "dept": "Engineering", "role": "Staff Engineer",
     "tenant": "acme_engineering"},
    {"name": "James Rodriguez", "dept": "Engineering", "role": "Engineering Manager",
     "tenant": "acme_engineering"},
    {"name": "Aisha Patel", "dept": "Data Science", "role": "Senior Data Scientist",
     "tenant": "acme_engineering"},
    {"name": "David Kim", "dept": "Finance", "role": "Financial Analyst",
     "tenant": "globex_finance"},
    {"name": "Sarah Thompson", "dept": "Finance", "role": "VP of Finance",
     "tenant": "globex_finance"},
    {"name": "Michael O'Brien", "dept": "Security", "role": "Security Engineer",
     "tenant": "umbrella_security"},
    {"name": "Lisa Zhang", "dept": "Security", "role": "CISO",
     "tenant": "umbrella_security"},
    {"name": "Robert Johnson", "dept": "HR", "role": "HR Director",
     "tenant": "initech_hr"},
    {"name": "Emily Davis", "dept": "HR", "role": "Compensation Analyst",
     "tenant": "initech_hr"},
    {"name": "Carlos Mendez", "dept": "Product", "role": "Product Manager",
     "tenant": "acme_engineering"},
]


# ---------------------------------------------------------------------------
# Document Templates — entity-rich, designed for NER extraction
# ---------------------------------------------------------------------------

@dataclass
class GeneratedDoc:
    """A generated document with ground truth annotations."""
    doc_id: str
    title: str
    text: str
    domain: str
    doc_type: str
    tenant: str
    sensitivity: str
    source: str
    provenance_score: float
    entities_mentioned: list[str] = field(default_factory=list)
    bridge_entities: list[str] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "text": self.text,
            "domain": self.domain,
            "doc_type": self.doc_type,
            "tenant": self.tenant,
            "sensitivity": self.sensitivity,
            "source": self.source,
            "provenance_score": self.provenance_score,
            "entities_mentioned": self.entities_mentioned,
            "bridge_entities": self.bridge_entities,
            "relations": self.relations,
        }


def _pick(pool: list, n: int = 1) -> list:
    """Pick n random items from a pool without replacement (or with if pool too small)."""
    if len(pool) <= n:
        return list(pool)
    return random.sample(pool, n)


def _employee_for_tenant(tenant: str) -> dict:
    """Get a named employee for a tenant, or fall back to a random one."""
    matches = [e for e in NAMED_EMPLOYEES if e["tenant"] == tenant]
    if matches:
        return random.choice(matches)
    return random.choice(NAMED_EMPLOYEES)


def _bridge_for_tenant(tenant: str) -> list[dict]:
    """Get bridge entities that connect to a given tenant."""
    return [b for b in ALL_BRIDGE_ENTITIES if tenant in b["connects"]]


# ---------------------------------------------------------------------------
# Engineering document generators
# ---------------------------------------------------------------------------

def gen_engineering_runbook(tenant: str, sensitivity: str) -> GeneratedDoc:
    system = random.choice(ENGINEERING_SYSTEMS)
    tech = _pick(ENGINEERING_TECHNOLOGIES, 2)
    owner = _employee_for_tenant(tenant)
    project = random.choice(ENGINEERING_PROJECTS)

    title = f"Runbook: {system} Operations"
    text = (
        f"Runbook: {system} Operations\n\n"
        f"System: {system}\n"
        f"Owner: {owner['name']} ({owner['role']})\n"
        f"Project: {project}\n\n"
        f"The {system} service is deployed on {tech[0]} and monitored via {tech[1]}. "
        f"{owner['name']} is the primary on-call contact for this system. "
        f"This service is part of {project} and handles critical request routing. "
        f"In case of failure, check the {tech[0]} dashboard first, then review "
        f"the {tech[1]} metrics for anomalies. "
        f"Escalation path: {owner['name']} → Engineering Manager → VP Engineering. "
        f"Recovery time objective is 15 minutes for production incidents."
    )

    entities = [system, owner["name"], project] + tech
    relations = [
        {"source": system, "target": tech[0], "type": "DEPENDS_ON"},
        {"source": system, "target": owner["name"], "type": "OWNED_BY"},
        {"source": system, "target": project, "type": "BELONGS_TO"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="engineering", doc_type="runbook",
        tenant=tenant, sensitivity=sensitivity, source="engineering_wiki",
        provenance_score=round(random.uniform(0.8, 1.0), 2),
        entities_mentioned=entities, relations=relations,
    )


def gen_engineering_architecture(tenant: str, sensitivity: str) -> GeneratedDoc:
    systems = _pick(ENGINEERING_SYSTEMS, 3)
    techs = _pick(ENGINEERING_TECHNOLOGIES, 3)
    project = random.choice(ENGINEERING_PROJECTS)
    owner = _employee_for_tenant(tenant)

    title = f"Architecture: {project}"
    text = (
        f"Architecture Document: {project}\n\n"
        f"Author: {owner['name']}\n"
        f"Components: {systems[0]}, {systems[1]}, {systems[2]}\n\n"
        f"The {project} architecture consists of three main components. "
        f"The {systems[0]} handles incoming requests and routes them to {systems[1]} "
        f"for processing. Results are cached in {systems[2]} for low-latency retrieval. "
        f"The stack runs on {techs[0]} with {techs[1]} for state management "
        f"and {techs[2]} for observability. "
        f"{owner['name']} designed this architecture to support horizontal scaling "
        f"across multiple availability zones."
    )

    entities = systems + techs + [project, owner["name"]]
    relations = [
        {"source": systems[0], "target": systems[1], "type": "DEPENDS_ON"},
        {"source": systems[1], "target": systems[2], "type": "DEPENDS_ON"},
        {"source": project, "target": systems[0], "type": "CONTAINS"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="engineering", doc_type="architecture_doc",
        tenant=tenant, sensitivity=sensitivity, source="engineering_wiki",
        provenance_score=round(random.uniform(0.85, 1.0), 2),
        entities_mentioned=entities, relations=relations,
    )


def gen_engineering_api_doc(tenant: str, sensitivity: str) -> GeneratedDoc:
    system = random.choice(ENGINEERING_SYSTEMS)
    techs = _pick(ENGINEERING_TECHNOLOGIES, 2)
    owner = _employee_for_tenant(tenant)

    endpoint = f"/api/v1/{system.replace('-', '/')}"
    title = f"API Documentation: {system}"
    text = (
        f"API Documentation: {system}\n\n"
        f"Endpoint: {endpoint}\n"
        f"Maintainer: {owner['name']}\n\n"
        f"The {system} exposes a RESTful API for downstream consumers. "
        f"Authentication is handled via JWT tokens issued by auth-service. "
        f"Rate limiting is enforced at 1000 requests per minute per client. "
        f"The API is built on {techs[0]} with {techs[1]} for data persistence. "
        f"Contact {owner['name']} for API key provisioning or access issues."
    )

    entities = [system, owner["name"], "auth-service"] + techs
    relations = [
        {"source": system, "target": "auth-service", "type": "DEPENDS_ON"},
        {"source": system, "target": techs[1], "type": "DEPENDS_ON"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="engineering", doc_type="api_doc",
        tenant=tenant, sensitivity=sensitivity, source="engineering_wiki",
        provenance_score=round(random.uniform(0.8, 0.95), 2),
        entities_mentioned=entities, relations=relations,
    )


# ---------------------------------------------------------------------------
# Finance document generators
# ---------------------------------------------------------------------------

def gen_finance_budget(tenant: str, sensitivity: str) -> GeneratedDoc:
    account = random.choice(FINANCE_ACCOUNTS)
    amount = random.randint(100_000, 10_000_000)
    quarter = f"Q{random.randint(1, 4)} 2025"
    analyst = _employee_for_tenant(tenant)
    regulation = random.choice(FINANCE_REGULATIONS)

    title = f"Budget Report: {account}"
    text = (
        f"Budget Report: {account}\n\n"
        f"Total: ${amount:,}\n"
        f"Period: {quarter}\n"
        f"Prepared by: {analyst['name']}\n\n"
        f"This budget covers {account} for {quarter}. "
        f"The allocation of ${amount:,} reflects a 12% increase over the prior period. "
        f"Major line items include cloud infrastructure ($"
        f"{amount // 3:,}), personnel (${amount // 4:,}), "
        f"and vendor contracts (${amount // 6:,}). "
        f"All expenditures comply with {regulation} requirements. "
        f"{analyst['name']} approved this budget after review with the finance committee."
    )

    entities = [account, analyst["name"], regulation, quarter]
    relations = [
        {"source": account, "target": analyst["name"], "type": "OWNED_BY"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="finance", doc_type="budget",
        tenant=tenant, sensitivity=sensitivity, source="finance_system",
        provenance_score=round(random.uniform(0.85, 1.0), 2),
        entities_mentioned=entities, relations=relations,
    )


def gen_finance_contract(tenant: str, sensitivity: str) -> GeneratedDoc:
    vendor = random.choice(FINANCE_VENDORS)
    amount = random.randint(50_000, 5_000_000)
    approver = _employee_for_tenant(tenant)
    regulation = random.choice(FINANCE_REGULATIONS)

    title = f"Contract: {vendor} Services Agreement"
    text = (
        f"Contract: {vendor} Services Agreement\n\n"
        f"Vendor: {vendor}\n"
        f"Value: ${amount:,}\n"
        f"Approved by: {approver['name']}\n\n"
        f"This agreement with {vendor} covers professional services "
        f"for the fiscal year 2025. The total contract value is ${amount:,} "
        f"with quarterly payment milestones. {vendor} will provide consulting "
        f"and implementation services for our cloud migration initiative. "
        f"The contract includes SLA guarantees of 99.9% uptime "
        f"and compliance with {regulation}. "
        f"{approver['name']} negotiated favorable terms including a 15% volume discount."
    )

    entities = [vendor, approver["name"], regulation]
    relations = [
        {"source": vendor, "target": approver["name"], "type": "OWNED_BY"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="finance", doc_type="contract",
        tenant=tenant, sensitivity=sensitivity, source="finance_system",
        provenance_score=round(random.uniform(0.9, 1.0), 2),
        entities_mentioned=entities, relations=relations,
    )


def gen_finance_audit(tenant: str, sensitivity: str) -> GeneratedDoc:
    regulation = random.choice(FINANCE_REGULATIONS)
    auditor = random.choice(FINANCE_VENDORS[:4])  # Big 4 only
    analyst = _employee_for_tenant(tenant)

    title = f"Audit Report: {regulation} Compliance"
    text = (
        f"Audit Report: {regulation} Compliance Review\n\n"
        f"Auditor: {auditor}\n"
        f"Internal Lead: {analyst['name']}\n\n"
        f"This report summarizes the {regulation} compliance audit conducted by {auditor}. "
        f"The audit covered 14 control areas and identified 3 minor findings "
        f"and 0 critical deficiencies. {analyst['name']} coordinated the internal "
        f"response and remediation plan. All findings have been addressed "
        f"with corrective actions scheduled for completion within 90 days. "
        f"The overall compliance posture is rated as Strong."
    )

    entities = [regulation, auditor, analyst["name"]]
    relations = [
        {"source": regulation, "target": auditor, "type": "RELATED_TO"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="finance", doc_type="audit_report",
        tenant=tenant, sensitivity=sensitivity, source="finance_system",
        provenance_score=round(random.uniform(0.9, 1.0), 2),
        entities_mentioned=entities, relations=relations,
    )


# ---------------------------------------------------------------------------
# HR document generators
# ---------------------------------------------------------------------------

def gen_hr_policy(tenant: str, sensitivity: str) -> GeneratedDoc:
    dept = random.choice(HR_DEPARTMENTS)
    benefit = random.choice(HR_BENEFITS)
    author = _employee_for_tenant(tenant)

    title = f"HR Policy: {dept} Department Guidelines"
    text = (
        f"HR Policy: {dept} Department Guidelines\n\n"
        f"Effective: 2025-01-01\n"
        f"Author: {author['name']} ({author['role']})\n\n"
        f"This policy governs employment practices within the {dept} department. "
        f"All {dept} team members are eligible for {benefit} as part of the "
        f"standard compensation package. Performance reviews occur quarterly "
        f"with annual compensation adjustments. {author['name']} is responsible "
        f"for policy interpretation and exception requests. "
        f"Remote work arrangements require manager approval and must comply "
        f"with the corporate information security policy."
    )

    entities = [dept, author["name"], benefit]
    relations = [
        {"source": dept, "target": author["name"], "type": "OWNED_BY"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="hr", doc_type="policy",
        tenant=tenant, sensitivity=sensitivity, source="hr_system",
        provenance_score=round(random.uniform(0.9, 1.0), 2),
        entities_mentioned=entities, relations=relations,
    )


def gen_hr_employee_record(tenant: str, sensitivity: str) -> GeneratedDoc:
    employee = random.choice(NAMED_EMPLOYEES)
    salary = random.randint(80_000, 350_000)
    benefit = random.choice(HR_BENEFITS)
    manager = _employee_for_tenant(tenant)

    title = f"Employee Record: {employee['name']}"
    text = (
        f"Employee Record: {employee['name']}\n\n"
        f"Department: {employee['dept']}\n"
        f"Role: {employee['role']}\n"
        f"Manager: {manager['name']}\n\n"
        f"{employee['name']} joined the {employee['dept']} department as a "
        f"{employee['role']}. Current compensation is ${salary:,} annually "
        f"with {benefit} and standard equity package. Performance rating: Exceeds "
        f"Expectations. {employee['name']} reports to {manager['name']} and is "
        f"responsible for key deliverables within the team. "
        f"Next review date: 2025-06-15."
    )

    entities = [employee["name"], employee["dept"], employee["role"], manager["name"]]
    relations = [
        {"source": employee["name"], "target": employee["dept"], "type": "BELONGS_TO"},
        {"source": employee["name"], "target": manager["name"], "type": "OWNED_BY"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="hr", doc_type="employee_record",
        tenant=tenant, sensitivity=sensitivity, source="hr_system",
        provenance_score=round(random.uniform(0.9, 1.0), 2),
        entities_mentioned=entities, relations=relations,
    )


def gen_hr_compensation(tenant: str, sensitivity: str) -> GeneratedDoc:
    dept = random.choice(HR_DEPARTMENTS)
    analyst = _employee_for_tenant(tenant)
    benefit = random.choice(HR_BENEFITS)

    title = f"Compensation Analysis: {dept}"
    text = (
        f"Compensation Analysis: {dept} Department\n\n"
        f"Prepared by: {analyst['name']}\n\n"
        f"This analysis covers salary bands and total compensation for the {dept} "
        f"department. Median base salary is $142,000 with a total compensation "
        f"range of $120,000 to $280,000 depending on level. "
        f"The {benefit} component adds approximately 18% to total compensation. "
        f"{analyst['name']} recommends a 5% market adjustment for senior roles "
        f"to maintain competitive positioning. "
        f"Attrition risk is moderate for the {dept} team based on market analysis."
    )

    entities = [dept, analyst["name"], benefit]
    relations = [
        {"source": dept, "target": analyst["name"], "type": "RELATED_TO"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="hr", doc_type="compensation",
        tenant=tenant, sensitivity=sensitivity, source="hr_system",
        provenance_score=round(random.uniform(0.9, 1.0), 2),
        entities_mentioned=entities, relations=relations,
    )


# ---------------------------------------------------------------------------
# Security document generators
# ---------------------------------------------------------------------------

def gen_security_vuln_assessment(tenant: str, sensitivity: str) -> GeneratedDoc:
    cve = random.choice(SECURITY_CVES)
    system = random.choice(ENGINEERING_SYSTEMS)
    tool = random.choice(SECURITY_TOOLS)
    analyst = _employee_for_tenant(tenant)
    severity = random.choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"])

    title = f"Vulnerability Assessment: {cve}"
    text = (
        f"Vulnerability Assessment: {cve}\n\n"
        f"CVE: {cve}\n"
        f"Severity: {severity}\n"
        f"Affected System: {system}\n"
        f"Discovered by: {analyst['name']} using {tool}\n\n"
        f"Assessment of {cve} affecting {system}. This vulnerability was identified "
        f"during routine scanning with {tool}. The {severity} severity rating reflects "
        f"the potential for remote code execution on the {system} service. "
        f"{analyst['name']} has confirmed the vulnerability is exploitable in the "
        f"current production configuration. "
        f"Recommended remediation: patch to latest version within "
        f"{'24 hours' if severity == 'CRITICAL' else '30 days'}."
    )

    entities = [cve, system, tool, analyst["name"], severity]
    relations = [
        {"source": cve, "target": system, "type": "RELATED_TO"},
        {"source": cve, "target": analyst["name"], "type": "OWNED_BY"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="security", doc_type="vuln_assessment",
        tenant=tenant, sensitivity=sensitivity, source="security_system",
        provenance_score=round(random.uniform(0.85, 1.0), 2),
        entities_mentioned=entities, relations=relations,
    )


def gen_security_incident(tenant: str, sensitivity: str) -> GeneratedDoc:
    system = random.choice(ENGINEERING_SYSTEMS)
    tool = random.choice(SECURITY_TOOLS)
    analyst = _employee_for_tenant(tenant)
    framework = random.choice(SECURITY_FRAMEWORKS)
    impact = random.choice(["Low", "Medium", "High", "Critical"])

    title = f"Incident Report: {system} Security Event"
    text = (
        f"Incident Report: {system} Security Event\n\n"
        f"Date: 2025-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}\n"
        f"Impact: {impact}\n"
        f"Lead Responder: {analyst['name']}\n\n"
        f"Security incident detected on {system} by {tool}. "
        f"The incident involved unauthorized access attempts against the {system} "
        f"management interface. {analyst['name']} led the incident response "
        f"following {framework} guidelines. "
        f"Root cause: misconfigured access control on the {system} admin endpoint. "
        f"No data exfiltration confirmed. Remediation completed within 4 hours. "
        f"Post-incident review scheduled for next week."
    )

    entities = [system, tool, analyst["name"], framework]
    relations = [
        {"source": system, "target": analyst["name"], "type": "RELATED_TO"},
        {"source": system, "target": framework, "type": "RELATED_TO"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="security", doc_type="incident_report",
        tenant=tenant, sensitivity=sensitivity, source="security_system",
        provenance_score=round(random.uniform(0.85, 1.0), 2),
        entities_mentioned=entities, relations=relations,
    )


def gen_security_pentest(tenant: str, sensitivity: str) -> GeneratedDoc:
    system = random.choice(ENGINEERING_SYSTEMS)
    tools = _pick(SECURITY_TOOLS, 2)
    analyst = _employee_for_tenant(tenant)
    framework = random.choice(SECURITY_FRAMEWORKS)

    title = f"Pentest Report: {system}"
    text = (
        f"Penetration Test Report: {system}\n\n"
        f"Target: {system}\n"
        f"Tester: {analyst['name']}\n"
        f"Framework: {framework}\n\n"
        f"Penetration test of {system} using {tools[0]} and {tools[1]}. "
        f"Testing followed {framework} methodology across 8 attack categories. "
        f"Findings: 2 high-severity, 5 medium-severity, 12 low-severity issues. "
        f"The most critical finding involves an authentication bypass on the "
        f"{system} API that allows privilege escalation. "
        f"{analyst['name']} recommends immediate remediation of the 2 high-severity "
        f"findings and a follow-up retest within 60 days."
    )

    entities = [system, analyst["name"], framework] + tools
    relations = [
        {"source": system, "target": framework, "type": "RELATED_TO"},
        {"source": system, "target": analyst["name"], "type": "RELATED_TO"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain="security", doc_type="pentest",
        tenant=tenant, sensitivity=sensitivity, source="security_system",
        provenance_score=round(random.uniform(0.9, 1.0), 2),
        entities_mentioned=entities, relations=relations,
    )


# ---------------------------------------------------------------------------
# Bridge Entity Document Generators — documents that create cross-tenant paths
# ---------------------------------------------------------------------------

def gen_bridge_document(bridge: dict, tenant: str, sensitivity: str) -> GeneratedDoc:
    """Generate a document that mentions a bridge entity in a given tenant context."""
    bridge_name = bridge["name"]
    bridge_type = bridge["type"]
    mention = random.choice(bridge["mention_as"])
    owner = _employee_for_tenant(tenant)

    if bridge_type == "shared_vendor":
        title = f"Vendor Reference: {bridge_name}"
        text = (
            f"Reference to {mention} in {tenant.replace('_', ' ')} context.\n\n"
            f"Our team works with {mention} on ongoing infrastructure projects. "
            f"{mention} provides critical services including cloud hosting, "
            f"data synchronization, and security consulting. "
            f"{owner['name']} is the primary liaison with {mention}. "
            f"The current contract with {mention} runs through December 2025."
        )
        doc_type = "vendor_reference"

    elif bridge_type == "shared_infrastructure":
        title = f"Infrastructure: {bridge_name}"
        text = (
            f"Infrastructure documentation for {mention}.\n\n"
            f"The {mention} is a shared platform used across multiple teams. "
            f"This system processes approximately 50,000 requests per minute "
            f"and is monitored by the security operations center. "
            f"{owner['name']} has administrative access to {mention}. "
            f"Change requests must be approved by both engineering and security teams."
        )
        doc_type = "infrastructure_doc"

    elif bridge_type == "shared_personnel":
        title = f"Staff Reference: {bridge_name}"
        text = (
            f"Personnel reference for {mention}.\n\n"
            f"{mention} works across department boundaries on critical projects. "
            f"Their responsibilities span both technical implementation and "
            f"strategic planning. {mention} has been with the organization for "
            f"3 years and holds security clearance for cross-functional work. "
            f"Reporting relationship: {mention} → {owner['name']}."
        )
        doc_type = "personnel_reference"

    elif bridge_type == "shared_compliance":
        title = f"Compliance: {bridge_name}"
        text = (
            f"Compliance documentation for {mention}.\n\n"
            f"The {mention} program is jointly managed by finance and security teams. "
            f"Current certification status: Active. "
            f"Last assessment date: 2025-01-15. "
            f"Next renewal: 2026-01-15. "
            f"{owner['name']} is the designated compliance officer for {mention}. "
            f"All departments must maintain evidence of compliance controls."
        )
        doc_type = "compliance_doc"

    else:  # shared_project
        title = f"Project: {bridge_name}"
        text = (
            f"Project overview for {mention}.\n\n"
            f"The {mention} spans engineering, finance, and HR departments. "
            f"Current status: Active. Budget: $2.5M. Timeline: 18 months. "
            f"{owner['name']} serves as the project lead for the {tenant.replace('_', ' ')} "
            f"workstream. The {mention} aims to modernize internal tooling "
            f"and improve cross-functional collaboration. "
            f"Weekly status meetings every Thursday at 10am."
        )
        doc_type = "project_doc"

    entities = [bridge_name, owner["name"]]
    bridge_entities = [bridge_name]
    relations = [
        {"source": bridge_name, "target": owner["name"], "type": "RELATED_TO"},
    ]

    return GeneratedDoc(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        title=title, text=text, domain=tenant.split("_")[-1],
        doc_type=doc_type,
        tenant=tenant, sensitivity=sensitivity, source=f"{tenant}_system",
        provenance_score=round(random.uniform(0.7, 0.9), 2),
        entities_mentioned=entities, bridge_entities=bridge_entities,
        relations=relations,
    )


# ---------------------------------------------------------------------------
# Document Generation Dispatcher
# ---------------------------------------------------------------------------

GENERATORS = {
    "engineering": {
        "runbook": gen_engineering_runbook,
        "architecture_doc": gen_engineering_architecture,
        "api_doc": gen_engineering_api_doc,
    },
    "finance": {
        "budget": gen_finance_budget,
        "contract": gen_finance_contract,
        "audit_report": gen_finance_audit,
    },
    "hr": {
        "policy": gen_hr_policy,
        "employee_record": gen_hr_employee_record,
        "compensation": gen_hr_compensation,
    },
    "security": {
        "vuln_assessment": gen_security_vuln_assessment,
        "incident_report": gen_security_incident,
        "pentest": gen_security_pentest,
    },
}

DOMAIN_TO_TENANT = {
    "engineering": "acme_engineering",
    "finance": "globex_finance",
    "hr": "initech_hr",
    "security": "umbrella_security",
}


def assign_sensitivity(tiers: list[dict]) -> str:
    """Assign a sensitivity tier based on configured fractions."""
    roll = random.random()
    cumulative = 0.0
    for tier in tiers:
        cumulative += tier.get("fraction", 0.25)
        if roll <= cumulative:
            return tier["name"]
    return "PUBLIC"


def generate_dataset(
    cfg: dict,
    bridge_count: int | None = None,
) -> list[dict]:
    """Generate the full synthetic dataset from config.

    Args:
        cfg: Dataset configuration dictionary.
        bridge_count: Number of bridge entities to include.
            None = use all 15 default. 0 = no bridges. >15 = generate extras.
    """
    dataset_cfg = cfg.get("dataset", cfg)
    scale_cfg = dataset_cfg.get("scale", {})
    preset = scale_cfg.get("preset", "small")
    presets = scale_cfg.get("presets", {})
    params = presets.get(preset, {"total_documents": 1000})
    total_docs = params["total_documents"]

    tiers = dataset_cfg.get("sensitivity_tiers", [
        {"name": "PUBLIC", "fraction": 0.40},
        {"name": "INTERNAL", "fraction": 0.30},
        {"name": "CONFIDENTIAL", "fraction": 0.20},
        {"name": "RESTRICTED", "fraction": 0.10},
    ])

    # Get the bridge entity list (may be truncated or extended)
    active_bridges = get_bridge_entities(bridge_count)

    domains = list(GENERATORS.keys())
    documents: list[GeneratedDoc] = []

    # Reserve ~10% of documents for bridge entity docs
    bridge_doc_count = max(total_docs // 10, len(active_bridges) * 2) if active_bridges else 0
    regular_doc_count = total_docs - bridge_doc_count

    # Generate regular domain documents
    for i in range(regular_doc_count):
        domain = domains[i % len(domains)]
        tenant = DOMAIN_TO_TENANT[domain]
        sensitivity = assign_sensitivity(tiers)
        doc_types = list(GENERATORS[domain].keys())
        doc_type = random.choice(doc_types)
        generator = GENERATORS[domain][doc_type]
        doc = generator(tenant, sensitivity)
        documents.append(doc)

    # Generate bridge entity documents
    # Each bridge entity gets at least 2 documents (one per connected tenant)
    bridge_docs_generated = 0
    for bridge in active_bridges:
        for tenant in bridge["connects"]:
            if bridge_docs_generated >= bridge_doc_count:
                break
            # Bridge docs are mostly INTERNAL/PUBLIC to be easily accessible
            sensitivity = random.choice(["PUBLIC", "INTERNAL"])
            doc = gen_bridge_document(bridge, tenant, sensitivity)
            documents.append(doc)
            bridge_docs_generated += 1

    # Fill remaining bridge slots with random bridge docs
    while bridge_docs_generated < bridge_doc_count and active_bridges:
        bridge = random.choice(active_bridges)
        tenant = random.choice(bridge["connects"])
        sensitivity = random.choice(["PUBLIC", "INTERNAL"])
        doc = gen_bridge_document(bridge, tenant, sensitivity)
        documents.append(doc)
        bridge_docs_generated += 1

    # Shuffle for realism
    random.shuffle(documents)

    return [doc.to_dict() for doc in documents]


def compute_stats(documents: list[dict]) -> dict:
    """Compute dataset statistics."""
    stats = {
        "total_documents": len(documents),
        "by_domain": {},
        "by_sensitivity": {},
        "by_tenant": {},
        "by_doc_type": {},
        "bridge_entity_coverage": {},
        "total_entities_mentioned": 0,
        "total_bridge_documents": 0,
        "avg_entities_per_doc": 0.0,
    }

    entity_count = 0
    for doc in documents:
        domain = doc["domain"]
        sensitivity = doc["sensitivity"]
        tenant = doc["tenant"]
        doc_type = doc["doc_type"]

        stats["by_domain"][domain] = stats["by_domain"].get(domain, 0) + 1
        stats["by_sensitivity"][sensitivity] = stats["by_sensitivity"].get(sensitivity, 0) + 1
        stats["by_tenant"][tenant] = stats["by_tenant"].get(tenant, 0) + 1
        stats["by_doc_type"][doc_type] = stats["by_doc_type"].get(doc_type, 0) + 1

        entities = doc.get("entities_mentioned", [])
        entity_count += len(entities)

        bridge_ents = doc.get("bridge_entities", [])
        if bridge_ents:
            stats["total_bridge_documents"] += 1
            for be in bridge_ents:
                stats["bridge_entity_coverage"][be] = (
                    stats["bridge_entity_coverage"].get(be, 0) + 1
                )

    stats["total_entities_mentioned"] = entity_count
    stats["avg_entities_per_doc"] = round(entity_count / max(len(documents), 1), 2)

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--config", "-c", default="configs/datasets/synthetic_enterprise.yaml",
              help="Path to dataset config YAML")
@click.option("--output", "-o", default="data/raw", help="Output directory")
@click.option("--scale", "-s", default=None,
              help="Override scale preset (small, medium, large)")
@click.option("--seed", default=42, type=int, help="Random seed for reproducibility")
@click.option("--stats/--no-stats", default=True, help="Print statistics after generation")
@click.option("--bridge-count", default=None, type=int,
              help="Number of bridge entities (0=none, 15=default, >15=generate extras)")
def main(
    config: str,
    output: str,
    scale: str | None,
    seed: int,
    stats: bool,
    bridge_count: int | None,
) -> None:
    """Generate synthetic enterprise dataset for PivoRAG experiments."""
    # Set seeds for reproducibility
    random.seed(seed)
    Faker.seed(seed)

    # Load config
    cfg = yaml.safe_load(Path(config).read_text())

    # Override scale if specified on command line
    if scale:
        cfg.setdefault("dataset", cfg).setdefault("scale", {})["preset"] = scale

    dataset_cfg = cfg.get("dataset", cfg)
    preset = dataset_cfg.get("scale", {}).get("preset", "small")
    presets = dataset_cfg.get("scale", {}).get("presets", {})
    total_docs = presets.get(preset, {}).get("total_documents", 1000)

    bc_label = f", bridge_count={bridge_count}" if bridge_count is not None else ""
    click.echo(f"Generating {total_docs} documents (preset: {preset}, seed: {seed}{bc_label})")

    # Generate documents
    documents = generate_dataset(cfg, bridge_count=bridge_count)

    # Save output
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "synthetic_enterprise.json"
    output_file.write_text(json.dumps(documents, indent=2))
    click.echo(f"Saved {len(documents)} documents to {output_file}")

    # Compute and save stats
    doc_stats = compute_stats(documents)
    doc_stats["preset"] = preset
    doc_stats["seed"] = seed

    stats_file = output_dir / "dataset_stats.json"
    stats_file.write_text(json.dumps(doc_stats, indent=2))
    click.echo(f"Stats saved to {stats_file}")

    if stats:
        click.echo("\n--- Dataset Statistics ---")
        click.echo(f"Total documents: {doc_stats['total_documents']}")
        click.echo(f"Average entities per doc: {doc_stats['avg_entities_per_doc']}")
        click.echo(f"Bridge entity documents: {doc_stats['total_bridge_documents']}")
        click.echo(f"\nBy domain: {json.dumps(doc_stats['by_domain'], indent=2)}")
        click.echo(f"\nBy sensitivity: {json.dumps(doc_stats['by_sensitivity'], indent=2)}")
        click.echo(f"\nBy tenant: {json.dumps(doc_stats['by_tenant'], indent=2)}")
        click.echo(
            f"\nBridge coverage: {json.dumps(doc_stats['bridge_entity_coverage'], indent=2)}"
        )


if __name__ == "__main__":
    main()
