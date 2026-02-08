# PivoRAG: Retrieval Pivot Attacks in Hybrid RAG

> **Measuring and Mitigating Amplified Leakage from Vector Seeds to Graph Expansion**

Research framework for studying **Retrieval Pivot Risk (RPR)** — a security vulnerability in hybrid RAG pipelines where vector-retrieved "seed" chunks pivot through entity linking into sensitive knowledge graph neighborhoods, creating data leakage absent in single-store retrieval.

## The Problem

Hybrid RAG pipelines combine vector similarity search with knowledge graph expansion for multi-hop reasoning. This creates a critical security boundary:

```
Query → Vector Search → [Entity Linking] → Graph Expansion → Merge → LLM
                              ↑
                     PIVOT POINT: vector auth ≠ graph auth
```

A user authorized to retrieve PUBLIC engineering docs via vector search can unknowingly trigger graph expansion into RESTRICTED security credentials — because **graph traversal inherits no authorization from the vector stage**.

## Key Metrics

### Retrieval Security Metrics

| Metric | Definition |
|--------|-----------|
| **RPR** | Probability that graph expansion reaches unauthorized sensitive nodes |
| **AF** | Amplification Factor: hybrid leakage / vector-only leakage |
| **PD** | Pivot Depth: min hops from seed to first sensitive node |
| **Leakage@k** | Count of sensitive items in top-k context |

### Generation Contamination Metrics

| Metric | Definition |
|--------|-----------|
| **ECR** | Entity Contamination Rate: fraction of leaked entities surfaced in answer |
| **ILS** | Information Leakage Score: embedding similarity to leaked chunks |
| **FCR** | Factual Contamination Rate: LLM-as-judge detects leaked facts |
| **GRR** | Generation Refusal Rate: whether model ignored leaked context |

## Attack Taxonomy

### Non-Adaptive Attacks (A1-A4)

| Attack | Mechanism | Entry Point |
|--------|-----------|-------------|
| **A1: Seed Steering** | Centroid poisoning to control which chunks become graph seeds | Vector store |
| **A2: Entity Anchor** | Inject chunks mentioning entities near sensitive neighborhoods | Entity linking |
| **A3: Neighborhood Flood** | Inflate degree around sensitive nodes to attract expansion | Graph topology |
| **A4: Bridge Node** | Create cross-tenant entity connections for unauthorized traversal | Graph structure |

### Adaptive Attacks (A5-A7)

| Attack | Mechanism | Entry Point |
|--------|-----------|-------------|
| **A5: Metadata Forgery** | Forge tenant labels to bypass D1 authorization | Graph metadata |
| **A6: Entity Manipulation** | OSINT entity names to force NER collision with target subgraph | Entity linker |
| **A7: Query Manipulation** | Entity-laden queries to steer expansion (no injection needed) | Query processing |

## Defense Suite

| Defense | Stage | Mechanism |
|---------|-------|-----------|
| **D1: Per-Hop AuthZ** | Expansion | Check tenant/sensitivity at every graph hop |
| **D2: Edge Allowlist** | Expansion | Restrict traversable edge types by query class |
| **D3: Budgeted Traversal** | Expansion | Hard caps on hops, branching, total nodes |
| **D4: Trust Weighting** | Expansion | Provenance-weighted expansion priority |
| **D5: Merge Filter** | Post-merge | Policy filter + rerank before LLM context |

## Repository Structure

```
hybrid-rag/
├── src/pivorag/          # Core package (52 .py files)
│   ├── ingestion/        # Chunking, NER, provenance, sensitivity labeling
│   ├── datasets/         # DatasetAdapter ABC + Enron, EDGAR, Synthetic adapters
│   ├── vector/           # Embedding, ChromaDB indexing, auth-aware retrieval
│   ├── graph/            # Neo4j schema, graph building, expansion, policy
│   ├── pipelines/        # P1 (vector), P2 (graph), P3-P8 (hybrid + defenses)
│   ├── attacks/          # A1-A4 (non-adaptive) + A5-A7 (adaptive) attacks
│   ├── defenses/         # D1-D5 implementations
│   ├── generation/       # LLM client abstraction (OpenAI, Anthropic, DeepSeek)
│   └── eval/             # Security metrics, generation metrics, benchmarking
├── configs/              # Pipeline, dataset, experiment, and GCP configs (YAML)
├── infra/terraform/      # GCP infrastructure (GCE + Neo4j AuraDB + GCS + Secrets)
├── data/queries/         # Benign and adversarial query sets
├── scripts/              # Data generation, ingestion, experiment runners
├── tests/                # 255 tests across 11 files
├── notebooks/            # Exploration, attack analysis, publication plots
├── paper/                # LaTeX paper + references.bib
└── docker-compose.yml    # Local Neo4j + ChromaDB
```

## Quick Start

### Prerequisites

- Python 3.11+
- Neo4j AuraDB instance (or local Neo4j)
- ChromaDB server (or local)

### Installation

```bash
git clone https://github.com/scthornton/hybrid-rag.git
cd hybrid-rag
pip install -e ".[dev]"
python -m spacy download en_core_web_sm
```

### Generate Synthetic Data

```bash
python scripts/make_synth_data.py --scale small --output data/raw/
```

### Build Indexes

```bash
# Requires running ChromaDB and Neo4j instances
python scripts/build_indexes.py --data data/raw/synthetic_enterprise.json
```

### Run Experiments

```bash
# Single pipeline evaluation
pivorag run --config configs/pipelines/hybrid_baseline.yaml \
            --queries data/queries/benign.json \
            --output results/

# Full experiment suite
bash scripts/run_all_experiments.sh
```

### Run Tests

```bash
pytest tests/ -v
```

## GCP Infrastructure

The experiment environment runs on Google Cloud Platform:

- **Compute:** GCE e2-standard-8 (Ubuntu 22.04, 100GB SSD)
- **Vector Store:** ChromaDB on GCE instance
- **Graph Store:** Neo4j AuraDB (managed)
- **Storage:** GCS bucket for data and results

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your GCP project settings
terraform init && terraform plan && terraform apply
```

## Pipeline Variants

| ID | Config | Description |
|----|--------|-------------|
| P1 | `vector_only.yaml` | Vector-only RAG (baseline) |
| P2 | `graph_only.yaml` | Graph-only retrieval |
| P3 | `hybrid_baseline.yaml` | Hybrid RAG, no defenses |
| P4-P7 | Individual defense configs | Hybrid + single defense |
| P8 | `hybrid_defenses.yaml` | Hybrid + all defenses (D1-D5) |

## Configuration

All pipeline behavior is controlled via YAML configs. See `configs/pipelines/` for examples.

Key settings in `hybrid_baseline.yaml`:
```yaml
vector:
  model: all-MiniLM-L6-v2
  top_k: 10
graph:
  max_hops: 3
  max_branching: 15
  expansion_algorithm: bfs
```

Environment variables (`.env`):
```bash
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_PASSWORD=your-password
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

## Datasets

| Dataset | Corpus Size | Tenants | Bridge Entities | Source |
|---------|-------------|---------|-----------------|--------|
| **Synthetic** | 1K-100K docs | 4 (eng, fin, hr, sec) | 40 (designed) | Generated |
| **Enron Email** | 50K emails | 5 (trading, legal, finance, energy, exec) | Natural (cross-dept executives) | Kaggle/FERC |
| **SEC EDGAR** | 10-K filings | 4 sectors (tech, fin, health, energy) | Natural (board members, auditors) | EDGAR API |

## Research Context

This project addresses a **completely unfilled gap** in the literature. No published work studies cross-store privilege escalation in hybrid vector+graph RAG systems. The closest work:

- **GRAGPoison** (IEEE S&P 2026) — graph-only poisoning, 98% ASR
- **PoisonedRAG** (USENIX Security 2025) — vector-only poisoning, 90% ASR
- **RAGCrawler** (Jan 2026) — KG-guided extraction, 84.4% corpus coverage

## Citation

```bibtex
@inproceedings{thornton2026pivorag,
  title     = {Retrieval Pivot Attacks in Hybrid {RAG}: Measuring and
               Mitigating Amplified Leakage from Vector Seeds to
               Graph Expansion},
  author    = {Thornton, Scott},
  year      = {2026},
  note      = {In preparation},
}
```

## License

Apache 2.0. See [LICENSE](LICENSE).

## Author

**Scott Thornton** — [perfecXion.ai](https://perfecxion.ai) — scthornton@gmail.com
