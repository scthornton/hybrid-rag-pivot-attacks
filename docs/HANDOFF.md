# Context Window Handoff Document

Use this document when starting a new Claude Code session on this project. It contains everything a fresh context window needs to become productive immediately.

**Last updated:** 2026-02-07

---

## Project Identity

| Field | Value |
|-------|-------|
| **Package name** | `pivorag` |
| **Version** | 0.1.0 |
| **Repository** | `git@github-scthornton:scthornton/hybrid-rag-pivot-attacks.git` |
| **Git identity** | `scthornton` / `scthornton@gmail.com` |
| **SSH alias** | `github-scthornton` (configured in `~/.ssh/config`) |
| **Branch** | `main` |
| **Python** | >= 3.11 (uses `StrEnum`, `from __future__ import annotations`) |
| **Paper target** | IEEE S&P 2027 / USENIX Security 2026 |
| **Paper title** | "Retrieval Pivot Attacks in Hybrid RAG: Measuring and Mitigating Amplified Leakage from Vector Seeds to Graph Expansion" |

---

## Current Status

### What's Done

- **Full project scaffold**: 91 files across 39 Python source files, 9 test files, 7 config files, 8 Terraform files, 3 notebooks, 2 query sets, LaTeX paper skeleton, README, docs
- **Package installs and imports**: `pip install -e ".[dev]"` works, `import pivorag` works
- **Test suite**: 52 tests pass, 1 skipped (hybrid placeholder) — with Docker running
- **Lint clean**: `ruff check src/ tests/ scripts/` passes with zero warnings
- **Terraform valid**: `terraform validate` passes
- **Research compilation**: 825-line literature review (42 papers, 8 gaps) in `RESEARCH_COMPILATION.md`
- **Pipeline implementations**: P1 (vector-only), P2 (graph-only), P3-P8 (hybrid) are complete
- **Defense implementations**: D1-D5 are implemented in `graph/policy.py` and `pipelines/hybrid.py`
- **Security metrics**: RPR, Leakage@k, AF, PD are implemented in `eval/metrics.py`
- **Utility metrics**: Accuracy, citation support, latency percentiles in `eval/utility.py`
- **Graph schema**: Full Pydantic models for Document, Chunk, Entity, System, Project, GraphNode, GraphEdge
- **Ingestion pipeline**: Chunker, EntityExtractor, RelationExtractor, SensitivityLabeler, ProvenanceScorer all have working interfaces
- **Comprehensive docs**: `docs/SETUP.md`, `docs/ARCHITECTURE.md`, this file
- **Synthetic data generator**: `scripts/make_synth_data.py` — curated entity pools, 15 bridge entities, 12 domain-specific generators, ground truth annotations (1000 docs, 4.09 avg entities/doc, 100 bridge docs)
- **Index builder**: `scripts/build_indexes.py` — 8-step pipeline with two-pass relation extraction (GT + pattern-based). Live-tested: 1000 docs → 785 entities → 7386 relations → ChromaDB 1000 chunks + Neo4j 2785 nodes, 15514 edges
- **All four attacks implemented**: A1 (seed_steering), A2 (entity_anchor), A3 (neighborhood_flood), A4 (bridge_node) — all have `generate_payloads()` and `inject()` with 15 tests
- **Relation extraction enhanced**: Two-pass approach (GT resolution + pattern-based). Types: RELATED_TO 44.1%, OWNED_BY 15.4%, DEPENDS_ON 6.5%, BELONGS_TO 12.0%, plus GT relations
- **Docker Compose**: `docker-compose.yml` for local Neo4j 5.15 + ChromaDB (latest), `.env.local` template
- **Integration tests**: Auto-detect running services, 52 pass with Docker, skip gracefully when Docker not running
- **Experiment runner**: `scripts/run_experiments.py` — baseline + full ablation (P1-P8), benign + adversarial queries, JSON results output
- **Attack experiment runner**: `scripts/run_attack_experiments.py` — inject A1-A4, measure leakage amplification, defense robustness
- **Baseline experiments complete**: P1 vs P3 vs P4-P8 on benign and adversarial queries. Results saved in `results/tables/`
- **Attack experiments complete**: A1-A4 against P3 and P4, defense robustness confirmed
- **Pivot depth metric**: Proper per-node hop distance tracking via `apoc.path.spanningTree`. PD=2.0 for all P3 leakage (chunk→entity→chunk mechanism)
- **Export pipeline**: `scripts/export_results.py` generates LaTeX tables, matplotlib plots (4 figures), seaborn heatmaps, and CSV summaries
- **Results notebook**: `notebooks/03_results_plots.ipynb` — 6 publication-ready figures with analysis. Outputs to `results/plots/` as PNG + PDF

### Experimental Results Summary (with Pivot Depth)

| Variant | RPR (benign) | RPR (adversarial) | Mean Leakage | PD | Context Size |
|---------|-------------|-------------------|-------------|-----|-------------|
| **P1** (vector-only) | 0.000 | 0.000 | 0.00 | -- | 10.0 |
| **P3** (hybrid, no defenses) | 0.800 | **1.000** | **20.50** | **2.0** | 110.0 |
| **P4** (D1: per-hop AuthZ) | 0.000 | 0.000 | 0.00 | -- | 50-57 |
| **P5** (D1+D2) | 0.000 | 0.000 | 0.00 | -- | 53-57 |
| **P6** (D1+D2+D3) | 0.000 | 0.000 | 0.00 | -- | 28-29 |
| **P7** (D1+D2+D3+D4) | 0.000 | 0.000 | 0.00 | -- | 26-27 |
| **P8** (all defenses) | 0.000 | 0.000 | 0.00 | -- | 19-23 |

**Key findings:**
1. P3 (undefended hybrid) leaks on 80-100% of queries — the vulnerability is architectural
2. All leakage occurs at exactly 2 hops (PD=2.0): chunk → shared entity → unauthorized chunk
3. D1 (per-hop authorization) alone eliminates all leakage
4. Progressive defenses D2-D5 reduce context size (57 → 19) without improving RPR
5. All four attacks (A1-A4) fail to bypass D1 — defense is robust under attack
6. Leakage comes from both cross-tenant traversal AND intra-tenant sensitivity escalation
7. AF = ∞ (vector-only has zero leakage, so any hybrid leakage is infinite amplification)

### What's NOT Done Yet

- **Entity linker** — Not yet implemented as a standalone component (hybrid pipeline has a fallback that uses chunk_ids)
- **Paper content** — LaTeX skeleton exists but sections need experimental results filled in

---

## Implementation Status Matrix

| Module | File | Status | Notes |
|--------|------|--------|-------|
| **Config** | `config.py` | ✅ Complete | PipelineConfig, EnvSettings, YAML loader |
| **Chunker** | `ingestion/chunker.py` | ✅ Complete | TokenChunker with tiktoken |
| **Entity Extract** | `ingestion/entity_extract.py` | ✅ Complete | spaCy NER wrapper |
| **Relation Extract** | `ingestion/relation_extract.py` | ✅ Complete | Pattern-based typing (5 relation types + fallback) |
| **Sensitivity** | `ingestion/sensitivity.py` | ✅ Complete | Rule-based labeler |
| **Provenance** | `ingestion/provenance.py` | ✅ Complete | Trust scoring by source type |
| **Embeddings** | `vector/embed.py` | ✅ Complete | sentence-transformers wrapper |
| **Vector Index** | `vector/index.py` | ✅ Complete | ChromaDB collection management |
| **Vector Retrieve** | `vector/retrieve.py` | ✅ Complete | Similarity search with auth prefilter |
| **Graph Schema** | `graph/schema.py` | ✅ Complete | All Pydantic models |
| **Graph Builder** | `graph/build_graph.py` | ✅ Complete | Neo4j graph construction |
| **Graph Expander** | `graph/expand.py` | ✅ Complete | BFS expansion |
| **Graph Policy** | `graph/policy.py` | ✅ Complete | TraversalPolicy, EdgeAllowlist, TraversalBudget |
| **Vector Pipeline** | `pipelines/vector_only.py` | ✅ Complete | P1 |
| **Graph Pipeline** | `pipelines/graph_only.py` | ✅ Complete | P2 |
| **Hybrid Pipeline** | `pipelines/hybrid.py` | ✅ Complete | P3-P8 with full defense stack |
| **A1 Seed Steering** | `attacks/seed_steering.py` | ✅ Complete | Pivot entities, steering templates, vector injection |
| **A2 Entity Anchor** | `attacks/entity_anchor.py` | ✅ Complete | Dense entity mentions (3+/chunk), graph edge creation |
| **A3 Neighborhood Flood** | `attacks/neighborhood_flood.py` | ✅ Complete | Degree inflation, supporting entities, cross-links |
| **A4 Bridge Node** | `attacks/bridge_node.py` | ✅ Complete | Cross-tenant bridges, both-side entity placement |
| **D1 Per-hop AuthZ** | `defenses/per_hop_authz.py` | ✅ Complete | |
| **D2 Edge Allowlist** | `defenses/edge_allowlist.py` | ✅ Complete | |
| **D3 Budgets** | `defenses/budgets.py` | ✅ Complete | |
| **D4 Trust Weighting** | `defenses/trust_weighting.py` | ✅ Complete | |
| **D5 Merge Filter** | `defenses/merge_filter.py` | ✅ Complete | |
| **Security Metrics** | `eval/metrics.py` | ✅ Complete | RPR, Leakage@k, AF, PD |
| **Utility Metrics** | `eval/utility.py` | ✅ Complete | Accuracy, citation support, latency |
| **Benchmark** | `eval/benchmark.py` | ✅ Complete | Orchestration framework |
| **CLI** | `eval/run_eval.py` | ✅ Complete | Click-based pivorag CLI |
| **Synth Data Gen** | `scripts/make_synth_data.py` | ✅ Complete | 12 generators, 15 bridge entities, ground truth annotations |
| **Index Builder** | `scripts/build_indexes.py` | ✅ Complete | 8-step pipeline, --dry-run, --skip-embed flags |

---

## Key Code Patterns

Follow these patterns when writing new code in this project:

### 1. `from __future__ import annotations`

Every Python file starts with this import. It enables PEP 604 union syntax (`str | None`) and forward references without quoting.

### 2. `StrEnum` (not `str, Enum`)

Python 3.11+ provides `StrEnum` natively. Always use:
```python
from enum import StrEnum

class SensitivityTier(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
```

Never use the old `class Foo(str, Enum)` pattern — ruff rule UP042 will flag it.

### 3. `zip()` requires `strict=` parameter

Ruff rule B905 requires all `zip()` calls to include `strict=True` or `strict=False`:
```python
for a, b in zip(list_a, list_b, strict=False):
```

### 4. Tenant authorization — watch for empty strings

The `""` empty string is falsy in Python. Naive checks like `if node.tenant and node.tenant not in allowed` silently pass empty-string tenants. Always use:
```python
node.tenant is None or node.tenant not in self.allowed_tenants
```
This catches both `None` and `""`.

### 5. Pydantic models everywhere

All data structures use Pydantic `BaseModel`:
- `Document`, `Chunk`, `Entity`, `GraphNode`, `GraphEdge` in `graph/schema.py`
- `PipelineConfig`, `VectorConfig`, `GraphConfig`, `DefenseConfig` in `config.py`
- `EnvSettings` uses `pydantic-settings` for `.env` loading

### 6. Configuration via YAML + environment

Pipeline configs load from YAML files in `configs/pipelines/`. Secrets load from `.env` via `EnvSettings`. Never put secrets in YAML or commit `.env`.

### 7. Ruff configuration

```toml
[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM"]
```

Rules: pycodestyle (E), pyflakes (F), isort (I), naming (N), warnings (W), pyupgrade (UP), bugbear (B), simplify (SIM).

---

## Known Bugs and Gotchas

1. **Empty-string tenant bypass** — Fixed in `graph/policy.py`. The `bridge_node` fixture in `conftest.py` has `tenant=""` (multi-tenant node). The authorization check now properly catches this.

2. **Ruff auto-fix can create new violations** — `ruff check --fix` sometimes combines branches (SIM114) into lines that exceed 100 chars (E501). When this happens, manually rewrite to extract named variables instead of relying on auto-fix.

3. **Integration tests require live services** — 3 tests are marked `@pytest.mark.skip` because they need running ChromaDB and Neo4j. To run them: start local services, remove the skip markers, run `pytest tests/ -v`.

4. **`pivot_depth()` is a placeholder** — Returns `1` for any sensitive node found. The full implementation needs per-node hop distance tracking in the traversal log. This is noted in the code with a comment.

5. **Relation extraction now pattern-based** — `RelationExtractor` uses lexical patterns to assign typed relations (DEPENDS_ON, OWNED_BY, BELONGS_TO, CONTAINS, DERIVED_FROM). Falls back to RELATED_TO at 0.4 confidence when no pattern matches (~38% of relations).

6. **Bridge entities now generated** — `make_synth_data.py` injects 15 bridge entities across 5 types, with ~100 bridge documents per 1000-doc corpus. Coverage verified in `data/raw/dataset_stats.json`.

---

## Test Suite

### Running Tests

```bash
pytest tests/ -v                    # Full suite
pytest tests/ -v -m "not slow"      # Skip slow tests
pytest tests/ -v -m "not integration" # Skip integration tests
pytest tests/test_metrics.py -v     # Single module
```

### Test Files

| File | Tests | Status |
|------|-------|--------|
| `test_ingestion.py` | Chunker, sensitivity labeling, relation extraction (12 tests) | All pass |
| `test_vector.py` | Embeddings (3 pass), VectorIndex + auth retrieval (2 skip w/o Docker) | 3 pass, 2 skipped |
| `test_graph.py` | Graph schema, policy authorization, edge allowlist, traversal budget | All pass |
| `test_pipelines.py` | P1 retrieval + cross-tenant leakage (2 skip w/o Docker), hybrid placeholder | 3 skipped |
| `test_attacks.py` | A1-A4 payload generation, entity placement, cross-tenant validation (15 tests) | All pass |
| `test_defenses.py` | Defense mechanism tests | All pass |
| `test_metrics.py` | RPR, Leakage@k, AF, PD computation | All pass |

### Key Fixtures (in `conftest.py`)

- `sample_document` — INTERNAL doc in acme_engineering
- `sample_chunk` — INTERNAL chunk from doc_001
- `sample_entities` — project_alpha (ORG) and kubernetes (TECH)
- `sensitive_node` — RESTRICTED credential in umbrella_security
- `bridge_node` — INTERNAL entity with `tenant=""` (multi-tenant)
- `sample_pipeline_config` — Minimal PipelineConfig for testing

---

## Critical Files to Read First

When starting a new session, read these files in order to get oriented:

1. **`docs/HANDOFF.md`** — This file. Project status and patterns.
2. **`src/pivorag/config.py`** — Configuration models. Understand SensitivityTier, PipelineConfig, DefenseConfig.
3. **`src/pivorag/graph/schema.py`** — Data models. Document, Chunk, Entity, GraphNode, GraphEdge.
4. **`src/pivorag/pipelines/hybrid.py`** — Core pipeline. The `retrieve()` method shows the full flow.
5. **`src/pivorag/graph/policy.py`** — Defense implementations. TraversalPolicy, EdgeAllowlist, TraversalBudget.
6. **`src/pivorag/eval/metrics.py`** — Security metrics. RPR, Leakage@k, AF, PD.
7. **`configs/pipelines/hybrid_defenses.yaml`** — Defense config. Shows all D1-D5 toggles.
8. **`configs/datasets/synthetic_enterprise.yaml`** — Dataset config. Tenants, tiers, bridge entities.

---

## Active Design Decisions

These decisions have already been made. Do not revisit them without explicit user direction:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Graph database | Neo4j AuraDB | Industry standard, Cypher query language, managed service |
| Vector store | ChromaDB | Lightweight, Python-native, cosine similarity built-in |
| Embedding model | all-MiniLM-L6-v2 | Fast, CPU-friendly, 384-dim, good quality for retrieval |
| NER model | spaCy en_core_web_sm | Fast, reliable, well-supported, sufficient for entity extraction |
| IaC | Terraform | Industry standard, GCP provider mature, state management |
| Package manager | pip + hatch | Simple, standard, pyproject.toml based |
| Linter | ruff | Fast, comprehensive, replaces flake8+isort+pyupgrade |
| Config format | YAML + pydantic | YAML for human editing, pydantic for validation |
| BFS for graph expansion | BFS over DFS/PageRank | Simpler, well-understood, max_hops naturally bounds depth |
| 4 tenants | Engineering, Finance, HR, Security | Covers cross-functional org, each has different sensitivity profiles |
| 15 bridge entities | 5 types × 3 each | Creates realistic but controllable cross-tenant paths |

---

## Next Implementation Tasks (Priority Order)

### Phase 2: COMPLETED
- ✅ Synthetic data generator (curated entities, 15 bridges, ground truth)
- ✅ Index builder (8-step pipeline, two-pass relation extraction, live-tested)
- ✅ A1-A4 attack implementations (15 tests passing)
- ✅ Relation extraction enhanced (GT + pattern-based, 7386 relations)
- ✅ Docker Compose + integration tests (52 pass with Docker)
- ✅ `build_indexes.py` against live services (2785 nodes, 15514 edges)
- ✅ Baseline experiments: P1 vs P3 (RPR 0.0 vs 0.9/1.0)
- ✅ Defense ablation: P3 vs P4-P8 (D1 alone eliminates leakage)
- ✅ Attack experiments: A1-A4 against P3 and P4 (D1 robust under attack)

### Phase 3: Paper Writing (Current Priority)
1. Fill in experimental results sections in LaTeX paper
2. Implement proper `pivot_depth()` with per-node hop distance tracking
3. Generate publication-ready figures (notebooks/03_results_plots.ipynb)
4. Write discussion section (interpret D1 effectiveness, attack limitations)
5. Write related work section (connect to RESEARCH_COMPILATION.md)
6. Measure utility impact (context size vs answer quality trade-off)
7. Standalone entity linker (improve hybrid pipeline entity resolution)

---

## File Inventory

| Directory | File Count | Purpose |
|-----------|-----------|---------|
| `src/pivorag/` | 39 .py files | Main package |
| `tests/` | 9 .py files | Test suite |
| `configs/` | 7 .yaml files | Pipeline, dataset, GCP configs |
| `infra/terraform/` | 8 .tf files | Infrastructure as Code |
| `scripts/` | 4 files | Data gen, index builder, experiment runner, exporter |
| `notebooks/` | 3 .ipynb files | Exploration, analysis, figures |
| `paper/` | 2 files | LaTeX source + bibliography |
| `data/queries/` | 2 .json files | Benign + adversarial query sets |
| `docs/` | 3 .md files | Setup, architecture, handoff |
| Root | 5 files | README, pyproject.toml, LICENSE, RESEARCH_COMPILATION, notes |
| **Total** | ~91 files | |

---

## Git Workflow

```bash
# Verify identity before any git operations
~/git-switch.sh  # Should show scthornton / scthornton@gmail.com

# If wrong:
~/git-switch.sh scthornton

# Verify remote uses SSH alias
git remote -v
# Should show: git@github-scthornton:scthornton/hybrid-rag-pivot-attacks.git

# If wrong:
git remote set-url origin git@github-scthornton:scthornton/hybrid-rag-pivot-attacks.git
```
