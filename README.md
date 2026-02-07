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

| Metric | Definition |
|--------|-----------|
| **RPR** | Probability that graph expansion reaches unauthorized sensitive nodes |
| **AF** | Amplification Factor: hybrid leakage / vector-only leakage |
| **PD** | Pivot Depth: min hops from seed to first sensitive node |
| **Leakage@k** | Count of sensitive items in top-k context |

## Attack Taxonomy

| Attack | Mechanism | Entry Point |
|--------|-----------|-------------|
| **A1: Seed Steering** | Centroid poisoning to control which chunks become graph seeds | Vector store |
| **A2: Entity Anchor** | Inject chunks mentioning entities near sensitive neighborhoods | Entity linking |
| **A3: Neighborhood Flood** | Inflate degree around sensitive nodes to attract expansion | Graph topology |
| **A4: Bridge Node** | Create cross-tenant entity connections for unauthorized traversal | Graph structure |

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
├── src/pivorag/          # Core package
│   ├── ingestion/        # Chunking, NER, provenance, sensitivity labeling
│   ├── vector/           # Embedding, ChromaDB indexing, auth-aware retrieval
│   ├── graph/            # Neo4j schema, graph building, expansion, policy
│   ├── pipelines/        # P1 (vector), P2 (graph), P3-P8 (hybrid + defenses)
│   ├── attacks/          # A1-A4 implementations
│   ├── defenses/         # D1-D5 implementations
│   └── eval/             # RPR/AF/PD/Leakage@k metrics, benchmarking, CLI
├── configs/              # Pipeline, dataset, and GCP configuration (YAML)
├── infra/terraform/      # GCP infrastructure (GCE + Neo4j AuraDB + GCS)
├── data/queries/         # Benign and adversarial query sets
├── scripts/              # Data generation, index building, experiment runner
├── tests/                # Unit tests for all components
├── notebooks/            # Exploration, attack analysis, publication plots
├── paper/                # LaTeX paper skeleton + references.bib
└── RESEARCH_COMPILATION.md  # Consolidated research (42 papers, 8 gaps)
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

- **Compute:** GCE e2-standard-4 (Ubuntu 22.04, 100GB SSD)
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

## Research Context

This project addresses a **completely unfilled gap** in the literature. No published work studies cross-store privilege escalation in hybrid vector+graph RAG systems. The closest work:

- **GRAGPoison** (IEEE S&P 2026) — graph-only poisoning, 98% ASR
- **PoisonedRAG** (USENIX Security 2025) — vector-only poisoning, 90% ASR
- **RAGCrawler** (Jan 2026) — KG-guided extraction, 84.4% corpus coverage

See `RESEARCH_COMPILATION.md` for the full literature survey (42 papers, 8 identified gaps).

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
