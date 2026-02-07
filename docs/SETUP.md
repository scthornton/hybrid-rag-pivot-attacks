# Environment Setup Guide

Complete instructions for recreating the PivoRAG research environment from scratch. This guide covers local development, GCP infrastructure provisioning, and end-to-end verification.

---

## Prerequisites

### Required Software

| Software | Version | Purpose | Install |
|----------|---------|---------|---------|
| Python | >= 3.11 | Runtime | `brew install python@3.11` or [python.org](https://www.python.org/downloads/) |
| pip | >= 23.0 | Package manager | Bundled with Python |
| Git | >= 2.40 | Version control | `brew install git` |
| Terraform | >= 1.5.0 | Infrastructure as Code | `brew install terraform` |
| gcloud CLI | latest | GCP management | [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install) |
| Docker | >= 24.0 | Local Neo4j (optional) | [docker.com](https://docs.docker.com/get-docker/) |
| spaCy model | en_core_web_sm | NER pipeline | `python -m spacy download en_core_web_sm` |

### Required Accounts

- **GCP account** with billing enabled (for compute, storage, and Secret Manager)
- **Neo4j AuraDB account** at [console.neo4j.io](https://console.neo4j.io/) (free tier works for small-scale experiments)
- **GitHub access** to the repository

### Hardware Recommendations

- **Local development**: Any modern machine with 8GB+ RAM
- **GCP compute**: e2-standard-4 (4 vCPUs, 16 GB RAM) — configured in Terraform
- **Storage**: ~10 GB for ChromaDB data at `large` scale preset (100K documents)
- **GPU** (optional): Only needed if using `torch` for custom embedding models. Not required for default `all-MiniLM-L6-v2` via sentence-transformers

---

## Local Development Setup

### 1. Clone the Repository

```bash
# Using SSH (recommended — matches the project's git identity setup)
git clone git@github-scthornton:scthornton/hybrid-rag-pivot-attacks.git
cd hybrid-rag-pivot-attacks

# Or using HTTPS
git clone https://github.com/scthornton/hybrid-rag-pivot-attacks.git
cd hybrid-rag-pivot-attacks
```

### 2. Create a Virtual Environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate

# Verify Python version
python --version  # Should show 3.11.x or 3.12.x
```

### 3. Install the Package

```bash
# Install pivorag in editable mode with all dependencies
pip install -e ".[dev]"

# Download the spaCy NER model
python -m spacy download en_core_web_sm
```

This installs all dependencies defined in `pyproject.toml`:

**Core dependencies:**
- `chromadb>=0.5.0` — Vector store
- `neo4j>=5.20.0` — Graph database driver
- `sentence-transformers>=3.0.0` — Embedding models
- `spacy>=3.7.0` — NER and NLP
- `pydantic>=2.7.0`, `pydantic-settings>=2.3.0` — Config and data models
- `pyyaml>=6.0`, `python-dotenv>=1.0.0` — Config loading
- `numpy>=1.26.0`, `pandas>=2.2.0`, `scikit-learn>=1.5.0` — Data processing
- `networkx>=3.3` — Graph algorithms (offline analysis)
- `faker>=28.0.0` — Synthetic data generation
- `matplotlib>=3.9.0`, `seaborn>=0.13.0` — Visualization
- `click>=8.1.0` — CLI framework
- `tiktoken>=0.7.0` — Token-based chunk sizing

**Dev dependencies** (installed with `[dev]`):
- `pytest>=8.2.0`, `pytest-cov>=5.0.0`, `pytest-asyncio>=0.23.0` — Testing
- `ruff>=0.5.0` — Linting
- `mypy>=1.10.0` — Type checking
- `ipykernel>=6.29.0` — Jupyter notebook support

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env  # If .env.example exists, or create from scratch
```

**`.env` contents:**

```dotenv
# Neo4j AuraDB connection
# Get these from the Neo4j Aura console after creating your instance
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-aura-password-here

# ChromaDB connection
# Default: localhost for local development
# Change to GCE IP for cloud deployment
CHROMA_HOST=localhost
CHROMA_PORT=8000

# Embedding model
# Default model works on CPU without GPU
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

**Important:** The `.env` file is in `.gitignore` and must never be committed. Sensitive values (Neo4j URI, password) should be stored in GCP Secret Manager for production use.

### 5. Verify Installation

```bash
# Verify the package imports correctly
python -c "import pivorag; print('pivorag imported successfully')"

# Run the test suite
pytest tests/ -v

# Expected output: 28 passed, 3 skipped
# The 3 skips are integration tests that require live Neo4j/ChromaDB:
#   - test_vector.py::TestVectorIndex::test_placeholder
#   - test_pipelines.py::TestVectorOnlyPipeline::test_placeholder
#   - test_pipelines.py::TestHybridPipeline::test_placeholder

# Run the linter
ruff check src/

# Expected output: All checks passed!
```

---

## Local Services (for Development Without GCP)

You can run experiments locally by standing up ChromaDB and Neo4j in Docker. This is the recommended approach for development and small-scale testing.

### ChromaDB (Local)

ChromaDB runs as a lightweight HTTP server:

```bash
# Option 1: Run directly (if chromadb is installed via pip)
chroma run --host localhost --port 8000

# Option 2: Run via Docker
docker run -d \
  --name pivorag-chromadb \
  -p 8000:8000 \
  -v pivorag_chroma_data:/chroma/chroma \
  chromadb/chroma:latest

# Verify
curl http://localhost:8000/api/v1/heartbeat
# Should return: {"nanosecond heartbeat": ...}
```

### Neo4j (Local via Docker)

For local development, run Neo4j Community Edition in Docker instead of using AuraDB:

```bash
docker run -d \
  --name pivorag-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/localpassword \
  -v pivorag_neo4j_data:/data \
  neo4j:5-community

# Verify via browser: http://localhost:7474
# Or via CLI:
cypher-shell -u neo4j -p localpassword "RETURN 1 AS test"
```

Update your `.env` for local Neo4j:

```dotenv
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=localpassword
```

---

## GCP Infrastructure Provisioning

The full experiment environment runs on Google Cloud Platform. Infrastructure is managed via Terraform in `infra/terraform/`.

### Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                    GCP Project                   │
│                                                  │
│  ┌──────────────┐    ┌─────────────────────┐     │
│  │  GCE Instance │    │ Neo4j AuraDB        │     │
│  │  e2-standard-4│    │ (external, managed) │     │
│  │               │    │                     │     │
│  │  - ChromaDB   │    │  Graph storage      │     │
│  │  - Python env │    │  Cypher queries     │     │
│  │  - Experiment │    └─────────────────────┘     │
│  │    runner     │                                │
│  └──────┬───────┘    ┌─────────────────────┐     │
│         │            │ GCS Bucket           │     │
│         │            │ pivorag-artifacts    │     │
│         │            │  - data/             │     │
│         │            │  - results/          │     │
│         │            └─────────────────────┘     │
│         │                                        │
│  ┌──────┴───────┐    ┌─────────────────────┐     │
│  │ VPC Network   │    │ Secret Manager      │     │
│  │ pivorag-net   │    │  - neo4j-uri        │     │
│  │               │    │  - neo4j-password   │     │
│  └──────────────┘    └─────────────────────┘     │
└─────────────────────────────────────────────────┘
```

### Step 1: Authenticate with GCP

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### Step 2: Create the Terraform State Bucket

Terraform state is stored in a GCS bucket (configured in `infra/terraform/main.tf`):

```bash
gsutil mb -l us-central1 gs://pivorag-tfstate
gsutil versioning set on gs://pivorag-tfstate
```

### Step 3: Provision Neo4j AuraDB (Manual)

Neo4j AuraDB is not Terraform-managed — you provision it through the Neo4j console:

1. Go to [console.neo4j.io](https://console.neo4j.io/)
2. Create a new **AuraDB Free** or **AuraDB Professional** instance
3. **Save the generated password immediately** — it's shown only once
4. Note the connection URI (format: `neo4j+s://xxxxxxxx.databases.neo4j.io`)
5. Store credentials in GCP Secret Manager:

```bash
# Store Neo4j URI
echo -n "neo4j+s://xxxxxxxx.databases.neo4j.io" | \
  gcloud secrets create pivorag-neo4j-uri \
    --data-file=- \
    --replication-policy="automatic"

# Store Neo4j password
echo -n "your-password-here" | \
  gcloud secrets create pivorag-neo4j-password \
    --data-file=- \
    --replication-policy="automatic"
```

### Step 4: Create Terraform Variables File

Create `infra/terraform/terraform.tfvars`:

```hcl
project_id         = "your-gcp-project-id"
region             = "us-central1"
zone               = "us-central1-a"
environment        = "dev"
gce_machine_type   = "e2-standard-4"
gce_disk_size_gb   = 100
neo4j_aura_uri     = "neo4j+s://xxxxxxxx.databases.neo4j.io"
neo4j_aura_password = "your-aura-password"
allowed_ssh_cidrs  = ["YOUR_IP/32"]
```

**Important:** `terraform.tfvars` is in `.gitignore` and must never be committed.

### Step 5: Initialize and Apply Terraform

```bash
cd infra/terraform

# Initialize Terraform with the GCS backend
terraform init

# Preview what will be created
terraform plan

# Apply the infrastructure
terraform apply

# Note the outputs (GCE IP, bucket name, etc.)
terraform output
```

**Resources created by Terraform:**
- VPC network (`pivorag-net`) with firewall rules
- GCE instance (e2-standard-4, Ubuntu 22.04) with ChromaDB
- GCS bucket (`pivorag-artifacts-{env}`) for data and results
- IAM service account with least-privilege permissions
- Secret Manager references for Neo4j credentials

### Step 6: Configure the GCE Instance

SSH into the instance and set up the environment:

```bash
# SSH via gcloud
gcloud compute ssh pivorag-instance --zone=us-central1-a

# On the instance:
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip

# Clone the repo
git clone https://github.com/scthornton/hybrid-rag-pivot-attacks.git
cd hybrid-rag-pivot-attacks

# Set up venv and install
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_sm

# Configure .env with Secret Manager values
export NEO4J_URI=$(gcloud secrets versions access latest --secret=pivorag-neo4j-uri)
export NEO4J_PASSWORD=$(gcloud secrets versions access latest --secret=pivorag-neo4j-password)

# Start ChromaDB as a systemd service
sudo tee /etc/systemd/system/chromadb.service > /dev/null <<SYSTEMD
[Unit]
Description=ChromaDB Vector Store
After=network.target

[Service]
Type=simple
User=pivorag
WorkingDirectory=/opt/pivorag
ExecStart=/opt/pivorag/.venv/bin/chroma run --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SYSTEMD

sudo systemctl daemon-reload
sudo systemctl enable chromadb
sudo systemctl start chromadb
```

---

## Running Experiments

### Generate Synthetic Data

```bash
# Small scale (1,000 documents) — fast, for development
python scripts/make_synth_data.py --config configs/datasets/synthetic_enterprise.yaml --output data/raw

# Medium scale (10,000 documents) — for initial experiments
# Edit configs/datasets/synthetic_enterprise.yaml: preset: medium
python scripts/make_synth_data.py -c configs/datasets/synthetic_enterprise.yaml -o data/raw

# Large scale (100,000 documents) — for publication results
# Edit configs/datasets/synthetic_enterprise.yaml: preset: large
python scripts/make_synth_data.py -c configs/datasets/synthetic_enterprise.yaml -o data/raw
```

Output: `data/raw/synthetic_enterprise.json` and `data/raw/dataset_stats.json`

### Build Indexes

```bash
# Build vector (ChromaDB) and graph (Neo4j) indexes from generated data
python scripts/build_indexes.py --data data/raw/synthetic_enterprise.json

# Note: This script is currently a scaffold. Full implementation pending.
```

### Run Experiments

```bash
# Run all experiment pipelines (P1-P8)
bash scripts/run_all_experiments.sh

# Or run individual pipeline evaluations via the CLI
pivorag --config configs/pipelines/vector_only.yaml --queries data/queries/benign.json
pivorag --config configs/pipelines/hybrid_baseline.yaml --queries data/queries/benign.json
pivorag --config configs/pipelines/hybrid_defenses.yaml --queries data/queries/benign.json
```

### Export Results

```bash
# Export experiment results to publication-ready format
python scripts/export_results.py
```

---

## Verification Checklist

Run through this checklist after any fresh setup to confirm everything works:

```bash
# 1. Package import
python -c "import pivorag; print('OK: pivorag imports')"

# 2. Test suite
pytest tests/ -v
# Expected: 28 passed, 3 skipped

# 3. Linter
ruff check src/
# Expected: All checks passed

# 4. Terraform validation (from infra/terraform/)
cd infra/terraform && terraform validate && cd ../..
# Expected: Success! The configuration is valid.

# 5. spaCy model
python -c "import spacy; nlp = spacy.load('en_core_web_sm'); print('OK: spaCy model loaded')"

# 6. ChromaDB connectivity (if running)
curl -s http://localhost:8000/api/v1/heartbeat | python -m json.tool
# Expected: {"nanosecond heartbeat": ...}

# 7. Neo4j connectivity (if running)
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'localpassword'))
with driver.session() as s:
    print('OK:', s.run('RETURN 1 AS n').single()['n'])
driver.close()
"
```

---

## Troubleshooting

### Common Issues

**`ModuleNotFoundError: No module named 'pivorag'`**

You forgot to install the package in editable mode. Run:
```bash
pip install -e ".[dev]"
```
Make sure your virtual environment is activated: `source .venv/bin/activate`

**`ruff` reports `UP042` on Enum classes**

This means `class Foo(str, Enum)` should be `class Foo(StrEnum)`. Python 3.11+ provides `StrEnum` natively. Import from `enum`: `from enum import StrEnum`.

**`zip() without an explicit strict parameter` (B905)**

Ruff requires all `zip()` calls to include `strict=True` or `strict=False`. Add the parameter explicitly.

**Neo4j AuraDB connection timeout**

- Verify the URI format: must start with `neo4j+s://` (not `bolt://` for AuraDB)
- Check that your IP is allowlisted in the AuraDB console
- AuraDB free instances pause after inactivity — resume from the console

**ChromaDB `Connection refused`**

- Verify ChromaDB is running: `curl http://localhost:8000/api/v1/heartbeat`
- If using Docker: `docker ps` to check the container is running
- If using systemd: `sudo systemctl status chromadb`

**Terraform `Error acquiring state lock`**

Someone else may have a lock on the state. Wait, or if you're certain no one else is running:
```bash
terraform force-unlock LOCK_ID
```

**`empty string tenant` authorization bypass**

This is a known pattern in the codebase. The `TraversalPolicy.is_node_authorized()` method checks `node.tenant is None or node.tenant not in self.allowed_tenants` to catch both `None` and `""` (empty string) tenants. In Python, `""` is falsy, so naive checks like `if node.tenant and node.tenant not in allowed` will silently pass empty-string tenants as authorized. This was a real bug that was fixed.

---

## Directory Structure Reference

```
hybrid-rag-pivot-attacks/
├── configs/
│   ├── datasets/
│   │   ├── synthetic_enterprise.yaml    # Dataset generation config
│   │   └── sensitivity_tiers.yaml       # Tier definitions
│   ├── gcp/
│   │   └── project.yaml                 # GCP project settings (no secrets)
│   └── pipelines/
│       ├── vector_only.yaml             # P1 config
│       ├── graph_only.yaml              # P2 config
│       ├── hybrid_baseline.yaml         # P3 config
│       └── hybrid_defenses.yaml         # P4-P8 config with defense toggles
├── data/
│   ├── queries/
│   │   ├── benign.json                  # 10 benign test queries
│   │   └── adversarial.json             # 10 adversarial test queries
│   └── raw/                             # Generated synthetic data (gitignored)
├── docs/
│   ├── SETUP.md                         # This file
│   ├── ARCHITECTURE.md                  # System architecture reference
│   └── HANDOFF.md                       # Context window handoff document
├── infra/
│   └── terraform/
│       ├── main.tf                      # Provider and backend config
│       ├── variables.tf                 # Input variables
│       ├── outputs.tf                   # Output values
│       ├── network.tf                   # VPC and firewall
│       ├── gce.tf                       # Compute instance
│       ├── neo4j.tf                     # Neo4j secret references
│       ├── gcs.tf                       # Storage bucket
│       └── iam.tf                       # IAM and service accounts
├── notebooks/
│   ├── 01_explore_dataset.ipynb         # Dataset exploration
│   ├── 02_attack_analysis.ipynb         # Attack analysis
│   └── 03_results_plots.ipynb           # Publication figures
├── paper/
│   ├── main.tex                         # LaTeX paper source
│   └── references.bib                   # Bibliography
├── results/                             # Experiment outputs (gitignored)
├── scripts/
│   ├── make_synth_data.py               # Synthetic data generator
│   ├── build_indexes.py                 # Index builder (scaffold)
│   ├── run_all_experiments.sh           # Experiment runner
│   └── export_results.py               # Results exporter
├── src/pivorag/                         # Main package (39 .py files)
├── tests/                               # Test suite (9 files)
├── pyproject.toml                       # Package definition
├── README.md                            # Project overview
└── RESEARCH_COMPILATION.md              # Literature review (825 lines)
```
