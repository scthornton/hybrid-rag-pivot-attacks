# System Architecture Reference

Technical architecture of the PivoRAG research framework. This document covers the complete system design, from data ingestion through retrieval pipeline execution, including all attack and defense mechanisms.

---

## Pipeline Architecture

The core research question is: **when does hybrid RAG amplify retrieval risk?** The pipeline below shows where the pivot point occurs — the entity linking step that bridges the vector and graph worlds.

```
                        THE RETRIEVAL PIVOT POINT
                                  │
  ┌─────────┐    ┌──────────┐    │    ┌──────────────┐    ┌───────────┐
  │  Query   │───▶│  Vector  │────┼───▶│    Entity     │───▶│   Graph   │
  │          │    │ Retrieve │    │    │   Linking     │    │  Expand   │
  └─────────┘    │ (ChromaDB)│    │    │ (spaCy NER)  │    │  (Neo4j)  │
                 │           │    │    │              │    │           │
                 │ top-k     │    │    │ chunk→entity │    │ BFS over  │
                 │ chunks by │    │    │ mapping      │    │ neighbors │
                 │ cosine    │    │    └──────────────┘    └─────┬─────┘
                 │ similarity│                                   │
                 └─────┬─────┘                                   │
                       │                                         │
                       │         ┌───────────────────┐           │
                       └────────▶│      Merge        │◀──────────┘
                                 │  vector + graph   │
                                 │  results          │
                                 └────────┬──────────┘
                                          │
                                          ▼
                                 ┌───────────────────┐
                                 │  LLM Generation   │
                                 │  (with context)   │
                                 └───────────────────┘
```

**The risk:** A user queries for something benign. Vector search returns public chunks. Those chunks mention entities that live in the knowledge graph. Graph expansion follows edges from those entities into **neighboring subgraphs the user was never authorized to see** — sensitive credentials, confidential financials, restricted HR data. The graph doesn't know the user only asked about Kubernetes.

---

## Module Map

### `src/pivorag/` — Main Package (52 Python files)

```
src/pivorag/
├── __init__.py              # Package root
├── config.py                # Configuration management (PipelineConfig, EnvSettings)
│
├── ingestion/               # Data ingestion pipeline
│   ├── chunker.py           # TokenChunker — splits documents into overlapping chunks
│   ├── entity_extract.py    # EntityExtractor — spaCy NER to find entities in text
│   ├── relation_extract.py  # RelationExtractor — co-occurrence-based relation extraction
│   ├── sensitivity.py       # SensitivityLabeler — assigns sensitivity tiers to documents
│   └── provenance.py        # ProvenanceScorer — trust scores by source type
│
├── datasets/                # Dataset abstraction layer
│   ├── base.py              # DatasetAdapter ABC — common interface for all corpora
│   ├── synthetic.py         # SyntheticEnterpriseAdapter — wraps make_synth_data.py
│   ├── enron.py             # EnronEmailAdapter — 500K emails, 5 department tenants
│   └── sec_edgar.py         # SECEdgarAdapter — 10-K filings, 4 sector tenants
│
├── vector/                  # Vector store layer
│   ├── embed.py             # EmbeddingModel — sentence-transformers wrapper
│   ├── index.py             # VectorIndex — ChromaDB collection management
│   └── retrieve.py          # VectorRetriever — similarity search with auth prefilter
│
├── graph/                   # Knowledge graph layer
│   ├── schema.py            # Pydantic models (Document, Chunk, Entity, GraphNode, etc.)
│   ├── build_graph.py       # GraphBuilder — constructs Neo4j graph from entities/relations
│   ├── expand.py            # GraphExpander — BFS expansion from seed nodes
│   └── policy.py            # TraversalPolicy, EdgeAllowlist, TraversalBudget
│
├── pipelines/               # RAG pipeline variants
│   ├── base.py              # BasePipeline ABC + RetrievalContext dataclass
│   ├── vector_only.py       # P1: Vector-only retrieval
│   ├── graph_only.py        # P2: Graph-only retrieval
│   └── hybrid.py            # P3-P8: Hybrid with configurable defenses
│
├── attacks/                 # Adversarial attack implementations
│   ├── base.py              # BaseAttack ABC
│   ├── seed_steering.py     # A1: Seed Steering
│   ├── entity_anchor.py     # A2: Entity Anchor
│   ├── neighborhood_flood.py# A3: Neighborhood Flood
│   ├── bridge_node.py       # A4: Bridge Node
│   ├── metadata_forgery.py  # A5: Targeted Metadata Forgery (adaptive)
│   ├── entity_manipulation.py # A6: Entity Manipulation (adaptive)
│   └── query_manipulation.py# A7: Query Manipulation (adaptive, query-only)
│
├── defenses/                # Defense mechanism implementations
│   ├── per_hop_authz.py     # D1: Per-hop authorization
│   ├── edge_allowlist.py    # D2: Edge type filtering
│   ├── budgets.py           # D3: Traversal budget caps
│   ├── trust_weighting.py   # D4: Provenance-based trust filtering
│   └── merge_filter.py      # D5: Post-merge policy filter
│
├── generation/              # LLM generation evaluation
│   ├── llm_client.py        # LLMClient ABC (OpenAI, Anthropic, DeepSeek)
│   └── context_assembler.py # Formats RetrievalContext into RAG prompts
│
└── eval/                    # Evaluation framework
    ├── metrics.py           # Security metrics (RPR, Leakage@k, AF, PD)
    ├── generation_metrics.py# Generation metrics (ECR, ILS, FCR, GRR)
    ├── generation_benchmark.py # End-to-end generation benchmark runner
    ├── utility.py           # Utility metrics (accuracy, citation support, latency)
    ├── benchmark.py         # Benchmark orchestration
    └── run_eval.py          # CLI entry point (pivorag command)
```

---

## Data Flow

### Ingestion Pipeline

```
JSON Documents
    │
    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ TokenChunker  │────▶│ EntityExtract│────▶│ RelationExtract│
│ (tiktoken)   │     │ (spaCy NER)  │     │ (co-occurrence)│
│              │     │              │     │               │
│ doc → chunks │     │ chunk →      │     │ entity pairs → │
│ (300 tokens, │     │ entities     │     │ relations      │
│  50 overlap) │     │ (ORG, PERSON,│     │ (RELATED_TO,   │
│              │     │  TECH, etc.) │     │  DEPENDS_ON)   │
└──────┬───────┘     └──────┬───────┘     └───────┬────────┘
       │                    │                      │
       ▼                    │                      │
┌──────────────┐            │                      │
│SensitivityLbl│            │                      │
│ (rule-based) │            │                      │
│              │            │                      │
│ assigns tier │            │                      │
│ PUBLIC →     │            │                      │
│ RESTRICTED   │            │                      │
└──────┬───────┘            │                      │
       │                    │                      │
       ▼                    ▼                      ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ EmbeddingModel│     │  Neo4j Graph │     │  Neo4j Graph │
│ (MiniLM-L6)  │     │  (nodes)     │     │  (edges)     │
│              │     │              │     │              │
│ chunk →      │     │ entities as  │     │ relations as │
│ 384-dim      │     │ graph nodes  │     │ graph edges  │
│ embedding    │     │ with tenant, │     │ with type,   │
│              │     │ sensitivity  │     │ trust score  │
└──────┬───────┘     └──────────────┘     └──────────────┘
       │
       ▼
┌──────────────┐
│  ChromaDB    │
│ (vector idx) │
│              │
│ chunks with  │
│ embeddings + │
│ metadata     │
│ (tenant,     │
│  sensitivity)│
└──────────────┘
```

### Retrieval Pipeline (Hybrid, P3-P8)

```
1. VECTOR RETRIEVAL
   Query → embed → cosine search ChromaDB → top-k chunks
   (with optional auth prefilter by tenant + sensitivity)

2. ENTITY LINKING
   top-k chunks → spaCy NER → entity mentions → lookup in Neo4j
   (maps chunk text to graph node IDs)

3. GRAPH EXPANSION
   seed node IDs → BFS over Neo4j → expanded neighborhood
   (configurable: max_hops, max_branching, allowed_edge_types)

4. DEFENSE STACK (if enabled)
   D1: Per-hop authorization filter
   D2: Edge allowlist by query class
   D3: Traversal budget enforcement
   D4: Trust-weighted node filtering
   D5: Merge-time policy filter

5. MERGE
   vector chunks + graph nodes → unified context
   (dedup, rerank, max_context_chunks limit)

6. EVALUATION
   context → security metrics (RPR, Leakage@k, AF, PD)
   context → utility metrics (accuracy, citation support, latency)
```

---

## Pipeline Variants

Eight pipeline configurations for controlled experiments. Each variant isolates specific variables for the ablation study.

| Variant | Name | Vector | Graph | Defenses | Purpose |
|---------|------|--------|-------|----------|---------|
| **P1** | Vector Only | yes | no | none | Baseline — vector retrieval alone |
| **P2** | Graph Only | no | yes | none | Baseline — graph retrieval alone |
| **P3** | Hybrid Baseline | yes | yes | **none** | Attack surface — undefended hybrid |
| **P4** | Hybrid + D1 | yes | yes | Per-hop AuthZ | Isolate D1 effect |
| **P5** | Hybrid + D2 | yes | yes | Edge Allowlist | Isolate D2 effect |
| **P6** | Hybrid + D3 | yes | yes | Budgets | Isolate D3 effect |
| **P7** | Hybrid + D4 | yes | yes | Trust Weighting | Isolate D4 effect |
| **P8** | Hybrid + All | yes | yes | D1+D2+D3+D4+D5 | Full defense stack |

**Key comparisons:**
- **P1 vs P3**: Does graph expansion amplify leakage? (AF metric)
- **P3 vs P4-P7**: How much does each individual defense reduce RPR?
- **P3 vs P8**: What's the cumulative effect of the full defense stack?
- **P8 utility vs P1 utility**: Do defenses destroy answer quality?

### Configuration Files

Each variant has a YAML config in `configs/pipelines/`:

- `vector_only.yaml` — P1 (graph disabled, no defenses)
- `graph_only.yaml` — P2 (vector disabled)
- `hybrid_baseline.yaml` — P3 (both enabled, max_hops=3, no defenses)
- `hybrid_defenses.yaml` — P4-P8 (defense toggles, variant field selects which)

---

## Attack Taxonomy (A1–A7)

Seven retrieval pivot attacks: four non-adaptive (A1-A4) that assume honest metadata, and three adaptive (A5-A7) that test stronger threat models.

### A1: Seed Steering

**Target stage:** Vector retrieval (Step 1)

**Mechanism:** Craft adversarial chunks that maximize cosine similarity to anticipated query embeddings while embedding entity mentions that link to sensitive graph neighborhoods. Inject these into ChromaDB with PUBLIC sensitivity to bypass auth prefilters.

**Attack path:** Adversarial chunk → top-k selection → entity linking → graph expansion into restricted area

**Threat model:** Attacker can inject documents into the knowledge base (e.g., wiki contributor, data pipeline compromise)

### A2: Entity Anchor

**Target stage:** Entity linking (Step 2)

**Mechanism:** Identify target entities that sit near sensitive neighborhoods in the graph. Craft benign-looking documents that mention those entities. When NER processes these documents, it creates MENTIONS edges from chunks to the target entities. Any future query that retrieves these chunks triggers expansion toward sensitive nodes.

**Attack path:** Benign chunk with strategic entity mentions → NER extraction → new graph edges → pivot into sensitive area

**Threat model:** Attacker knows the graph schema and can craft documents mentioning specific entity names

### A3: Neighborhood Flood

**Target stage:** Graph expansion (Step 3)

**Mechanism:** Inject N documents that all mention entities in the 1-hop neighborhood of a sensitive target. This inflates the degree centrality of those neighboring nodes, making BFS or PageRank-weighted expansion algorithms strongly prefer that region of the graph. The sensitive target ends up in more expansion results.

**Attack path:** Mass injection near target → inflated degree → biased expansion → sensitive nodes surfaced

**Threat model:** Attacker can inject a moderate volume of documents (tens to hundreds)

### A4: Bridge Node

**Target stage:** Cross-tenant traversal

**Mechanism:** Identify entities in the attacker's authorized tenant and the target's restricted tenant. Craft documents mentioning entities from both tenants in the same text. Entity extraction creates cross-tenant edges. Graph expansion from the attacker's tenant now reaches the target's subgraph.

**Attack path:** Document mentioning entities from tenant A and tenant B → cross-tenant edges → traversal bridges isolation boundary

**Threat model:** Attacker is an authorized user in one tenant who wants access to another tenant's data

### A5: Targeted Metadata Forgery (Adaptive)

**Target stage:** Graph metadata (tenant labels)

**Mechanism:** Attacker relabels injected nodes with the *target* tenant's name, bypassing D1's per-hop tenant check. D1 alone fails under this attack because `forged_tenant in allowed_tenants` evaluates to true. D4 (trust weighting) catches forgery because injected documents have low provenance scores (0.2).

**Attack path:** Forge tenant label → D1 passes → expansion includes attacker content → D4 catches via low provenance

**Threat model:** Attacker can inject documents with arbitrary metadata (e.g., compromised data pipeline)

### A6: Entity Manipulation (Adaptive)

**Target stage:** Entity linking / deduplication

**Mechanism:** Attacker creates documents mentioning entities from the target tenant's namespace (discovered via OSINT — org charts, press releases, LinkedIn). NER extracts the same canonical names, and the entity linker merges them with existing nodes. This creates shared entity nodes where none should exist, enabling the chunk→entity→chunk pivot. D1 blocks because entity nodes have `tenant=""` (not in any allowed_tenants set).

**Attack path:** Documents mentioning target entities → NER collision → shared entity nodes → D1 blocks (entity tenant="")

**Threat model:** Attacker knows entity names from the target tenant (publicly discoverable information)

### A7: Query Manipulation (Adaptive, Query-Only)

**Target stage:** Query processing / NER on queries

**Mechanism:** Attacker crafts queries that directly mention entity names from the target tenant's namespace, steering entity linking toward sensitive neighborhoods. Unlike A1-A6, this requires NO document injection — the attacker only needs query-level access. D1 blocks for the same reason as A6: entity nodes have empty tenant.

**Attack path:** Entity-laden query → NER on query → entity linking to target subgraph → D1 blocks

**Threat model:** Attacker has query-level access only (no injection capability)

---

## Defense Suite (D1–D5)

Five complementary defenses that operate at different pipeline stages. Designed for defense-in-depth — each catches what the others miss.

### D1: Per-Hop Authorization

**Pipeline stage:** Graph expansion (every hop)

**Implementation:** `TraversalPolicy` in `graph/policy.py`

**Mechanism:** At every BFS hop, check:
1. Node sensitivity tier <= user's clearance level
2. Node tenant is in user's allowed tenant list
3. No sensitivity escalation (cannot hop from INTERNAL to CONFIDENTIAL)

**Key code pattern:** The authorization check handles both `None` and empty-string `""` tenants as "unassigned = unauthorized" to prevent the empty-string bypass:
```python
node.tenant is None or node.tenant not in self.allowed_tenants
```

### D2: Edge Allowlist

**Pipeline stage:** Graph expansion (edge selection)

**Implementation:** `EdgeAllowlist` in `graph/policy.py`

**Mechanism:** Query-class-aware filtering of edge types. Different query intents allow different edge traversals:
- `dependency` queries: DEPENDS_ON, CONTAINS, MENTIONS
- `ownership` queries: OWNED_BY, BELONGS_TO (max 1 hop)
- `general` queries: CONTAINS, MENTIONS, BELONGS_TO

This prevents an engineering query from following OWNED_BY edges into HR subgraphs.

### D3: Budgeted Traversal

**Pipeline stage:** Graph expansion (scope limiting)

**Implementation:** `TraversalBudget` in `graph/policy.py`

**Mechanism:** Hard caps on traversal scope:
- `max_hops = 2` (vs. baseline 3)
- `max_branching_factor = 8` (vs. baseline 15)
- `max_total_nodes = 40` (vs. baseline 100)
- `timeout_ms = 2000`

These prevent unbounded graph traversal from surfacing distant sensitive nodes.

### D4: Trust-Weighted Expansion

**Pipeline stage:** Post-expansion filtering

**Implementation:** `ProvenanceScorer` in `ingestion/provenance.py`

**Mechanism:** Each node carries a `provenance_score` based on its source:
- Curated: 1.0
- Internal system: 0.9
- External feed: 0.6
- User-generated: 0.5
- LLM-extracted: 0.4
- Web-scraped: 0.3

Nodes below `min_trust_score` (default 0.6) are filtered out. This defends against A3 (Neighborhood Flood) because injected content typically has low provenance scores.

### D5: Merge-Time Policy Filter

**Pipeline stage:** After merge (final context assembly)

**Implementation:** `_apply_merge_filter()` in `pipelines/hybrid.py`

**Mechanism:** Last line of defense. After vector and graph results are merged, re-check every item's sensitivity tier against the user's clearance. Catches anything that slipped through earlier stages.

### Defense Interaction Matrix

| Defense | A1 | A2 | A3 | A4 | A5 (Forgery) | A6 (Entity) | A7 (Query) |
|---------|----|----|----|----|-------------|-------------|------------|
| D1 (AuthZ) | partial | partial | no | **yes** | **FAILS** | **yes** | **yes** |
| D2 (Edges) | no | **yes** | partial | partial | no | partial | partial |
| D3 (Budget) | partial | partial | **yes** | partial | partial | partial | **yes** |
| D4 (Trust) | **yes** | partial | **yes** | partial | **yes** | partial | n/a |
| D5 (Merge) | partial | partial | partial | partial | partial | partial | partial |

**No single defense stops all attacks.** A5 (metadata forgery) is the critical case: D1 alone fails because forged tenant labels pass the authorization check. D4 catches forgery via low provenance scores. This is why the full stack (P8) combines all five — and why the defense stack is non-tautological.

---

## Graph Schema

### Node Types

| Type | Properties | Typical Tenant | Example |
|------|-----------|---------------|---------|
| Document | doc_id, title, text, source, sensitivity, provenance_score | per-tenant | "Project Alpha Architecture" |
| Chunk | chunk_id, doc_id, text, sensitivity, embedding_ref, provenance_score | inherits from doc | "Project Alpha uses microservices..." |
| Entity | entity_id, entity_type, canonical_name, sensitivity | per-tenant or shared | "kubernetes", "CloudCorp" |
| System | system_id, name, sensitivity | per-tenant | "k8s-prod-cluster" |
| Project | project_id, name, sensitivity | per-tenant or shared | "ProjectNexus" |
| User | user_id, clearance | per-tenant | "u_eng_001" |
| Source | source_id, name, trust_level | global | "engineering_wiki" |

### Edge Types

| Edge Type | Meaning | Example |
|-----------|---------|---------|
| CONTAINS | Document contains chunk | doc_001 → doc_001_chunk_0000 |
| MENTIONS | Chunk mentions entity | doc_001_chunk_0000 → ent_kubernetes |
| BELONGS_TO | Entity belongs to system/project | ent_alpha → project_alpha |
| DEPENDS_ON | System depends on system | payment_svc → billing_db |
| OWNED_BY | Resource owned by user/team | k8s_cluster → eng_team |
| DERIVED_FROM | Source derivation | llm_summary → original_doc |
| RELATED_TO | General semantic relation | entity_a → entity_b |

### Bridge Entities

40 entities create cross-tenant graph paths in the synthetic dataset (the attack surface). In the Enron and EDGAR datasets, bridge entities emerge naturally from cross-department executives, shared auditors, and multi-sector board members. Key categories:

| Type | Count | Tenants Connected | Examples |
|------|-------|-------------------|----------|
| Shared Vendor | 3 | engineering ↔ finance | CloudCorp, DataSyncInc, SecureNetLLC |
| Shared Infrastructure | 3 | engineering ↔ security | k8s-prod-cluster, splunk-siem, auth-service |
| Shared Personnel | 3 | HR ↔ engineering | Named employees |
| Shared Compliance | 3 | finance ↔ security | SOC2-audit, PCI-DSS-cert, ISO27001 |
| Shared Project | 3 | eng ↔ finance ↔ HR | ProjectNexus, ProjectHorizon, ProjectArcade |

---

## Sensitivity Tier Model

### Tier Hierarchy

```
RESTRICTED (level 3)  — Credentials, PII, vulnerabilities
    │
CONFIDENTIAL (level 2) — M&A plans, contracts, budgets
    │
INTERNAL (level 1)     — Wikis, runbooks, architecture docs
    │
PUBLIC (level 0)       — General knowledge, open-source references
```

### Authorization Rules

1. **Clearance check:** A user with clearance level N can access tiers 0 through N
2. **Tenant isolation:** A user can only see nodes in their `allowed_tenants` list
3. **No escalation (D1):** Graph traversal cannot hop from tier N to tier N+1
4. **Merge filter (D5):** Final check before context is assembled

### Distribution in Synthetic Data

| Tier | Fraction | Document Count (small/medium/large) |
|------|----------|--------------------------------------|
| PUBLIC | 40% | 400 / 4,000 / 40,000 |
| INTERNAL | 30% | 300 / 3,000 / 30,000 |
| CONFIDENTIAL | 20% | 200 / 2,000 / 20,000 |
| RESTRICTED | 10% | 100 / 1,000 / 10,000 |

---

## Security Metrics

### RPR — Retrieval Pivot Risk

```
RPR = Pr[Z(q,u) ∩ U_u ≠ ∅]
```

Probability that a query's retrieval context contains unauthorized items. RPR = 0 means perfect isolation; RPR = 1 means every query leaks.

### Leakage@k

```
Leakage@k(q) = |{x ∈ S_k(q) : Sensitive(x)}|
```

Count of sensitive items in the top-k context set. An item is "sensitive" if its tier exceeds the user's clearance OR it belongs to another tenant.

### AF — Amplification Factor

```
AF = E[Leakage@k]_hybrid / E[Leakage@k]_vector
```

How much more leakage does hybrid RAG produce compared to vector-only? AF >> 1 means the graph expansion significantly amplifies risk. AF = 1 means no amplification. AF < 1 would mean graph expansion somehow reduces leakage (unlikely without defenses).

### PD — Pivot Depth

```
PD(q) = min{d(seed, x) : x ∈ S(q) ∧ Sensitive(x)}
```

Minimum number of graph hops from a seed node to the first sensitive node. PD = 1 means sensitive nodes are directly adjacent to seeds. PD = ∞ means no sensitive nodes were reached.

---

## Generation Metrics

End-to-end metrics that measure how leaked retrieval context contaminates LLM-generated answers. Computed by comparing answers from the undefended pipeline (P3) against the defended pipeline (P4+).

### ECR — Entity Contamination Rate

```
ECR = |{e ∈ leaked_entities : e appears in answer}| / |leaked_entities|
```

Fraction of leaked entity names that appear in the generated answer. Uses exact + fuzzy string matching. ECR = 0 means the LLM didn't mention any leaked entities; ECR = 1 means every leaked entity was surfaced.

### ILS — Information Leakage Score

```
ILS = max{cos(answer_emb, chunk_emb) : chunk_emb ∈ leaked_chunks}
```

Maximum cosine similarity between the answer embedding and each leaked chunk embedding. High ILS means the answer is semantically close to unauthorized content.

### FCR — Factual Contamination Rate

LLM-as-judge (GPT-4o) compares a contaminated answer (P3 context) against a clean answer (P4 context) and identifies facts traceable to leaked chunks. Returns a score in [0, 1].

### GRR — Generation Refusal Rate

Whether the model effectively refused to use leaked context. If the contaminated and clean answers are nearly identical (Jaccard similarity >= 0.95), the model ignored the leaked context — GRR = 1.0.

---

## Configuration Reference

### Pipeline Config (YAML)

```yaml
pipeline:
  name: hybrid_baseline        # Human-readable name
  variant: P3                   # Variant identifier for metrics

vector:
  model: all-MiniLM-L6-v2      # Sentence-transformer model name
  top_k: 10                     # Number of vector results
  similarity_threshold: 0.3     # Minimum cosine similarity
  auth_prefilter: true           # Filter by tenant/sensitivity before search

graph:
  enabled: true                  # Toggle graph expansion
  max_hops: 3                    # BFS depth limit
  max_branching_factor: 15       # Max neighbors per hop
  max_total_nodes: 100           # Total node cap
  expansion_algo: bfs            # bfs | pagerank (future)
  edge_types: [CONTAINS, MENTIONS, BELONGS_TO, DEPENDS_ON, OWNED_BY, DERIVED_FROM]

entity_linking:
  enabled: true
  method: ner_lookup             # ner_lookup | embedding_match | hybrid
  confidence_threshold: 0.5

merge:
  strategy: union                # union | intersection | weighted
  dedup: true
  max_context_chunks: 20

defenses:
  per_hop_authz:
    enabled: false
    deny_cross_tenant: true
    deny_sensitivity_escalation: true
  edge_allowlist:
    enabled: false
    query_classes: { ... }
  budgets:
    enabled: false
    max_hops: 2
    max_branching_factor: 8
    max_total_nodes: 40
  trust_weighting:
    enabled: false
    min_trust_score: 0.6
  merge_filter:
    enabled: false
```

### Dataset Config (YAML)

```yaml
dataset:
  name: synthetic_enterprise
  version: "1.0"

scale:
  preset: small                  # small (1K) | medium (10K) | large (100K)

tenants:
  names: [acme_engineering, globex_finance, initech_hr, umbrella_security]

sensitivity_tiers:
  - { name: PUBLIC, fraction: 0.40 }
  - { name: INTERNAL, fraction: 0.30 }
  - { name: CONFIDENTIAL, fraction: 0.20 }
  - { name: RESTRICTED, fraction: 0.10 }

bridge_entities:
  count: 15
  types:
    - { name: shared_vendor, connects: [finance, engineering] }
    - { name: shared_infrastructure, connects: [engineering, security] }
    - { name: shared_personnel, connects: [hr, engineering] }
    - { name: shared_compliance, connects: [finance, security] }
    - { name: shared_project, connects: [engineering, finance, hr] }

random_seed: 42
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USERNAME` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `""` | Neo4j password |
| `CHROMA_HOST` | `localhost` | ChromaDB host |
| `CHROMA_PORT` | `8000` | ChromaDB port |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model |
| `OPENAI_API_KEY` | `""` | OpenAI API key (for generation eval) |
| `ANTHROPIC_API_KEY` | `""` | Anthropic API key (for generation eval) |
| `DEEPSEEK_API_KEY` | `""` | DeepSeek API key (for generation eval) |
