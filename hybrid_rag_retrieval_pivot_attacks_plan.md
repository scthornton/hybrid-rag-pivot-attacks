# Research Project Plan: Retrieval Pivot Attacks in Hybrid RAG (Vector → Graph)

**Working title:** *Retrieval Pivot Attacks in Hybrid RAG: Measuring and Mitigating Amplified Leakage from Vector Seeds to Graph Expansion*

**One-sentence summary:** Hybrid RAG pipelines that do **vector retrieval → entity linking → graph expansion** introduce a security-specific amplification channel: a semantically retrieved “seed” can **pivot** into sensitive graph neighborhoods, yielding leakage not present (or far weaker) in vector-only or graph-only retrieval.

---

## 1) Why this is novel / publishable

Existing literature has strong coverage of:
- **RAG data poisoning / knowledge corruption** (vector-centric)  
- **GraphRAG attacks** (graph-centric)

**Gap:** Hybrid pipelines are increasingly deployed, but there is limited formalization and measurement of **cross-store pivoting**:
- vector similarity retrieves a seed chunk
- seed anchors an entity/node
- graph traversal expands context and can cross policy/sensitivity boundaries

### Proposed paper contributions (3-part “publishable” package)
1. **Formalization + metrics** for hybrid pivot risk (RPR, amplification, pivot depth).
2. **Hybrid-specific attack taxonomy** and reproducible evaluation harness.
3. **Mitigation suite** (policy-checked expansion, allowlisted edges, budgeted traversal, provenance-weighted expansion) with quantified utility tradeoffs.

---

## 2) Research questions and hypotheses

### RQ1 — Does hybrid retrieval amplify sensitive exposure?
**Hypothesis:** Hybrid vector→graph expansion yields higher sensitivity leakage than vector-only RAG under the same initial filters, because expansion introduces additional reachable material.

### RQ2 — What are the dominant pivot pathways?
**Hypothesis:** Most leakage occurs through a small number of “bridge” edge types (e.g., `BELONGS_TO`, `DEPENDS_ON`, `SAME_PROJECT`, `MENTIONS`) and high-degree connector nodes.

### RQ3 — Can we bound pivot risk without collapsing answer quality?
**Hypothesis:** Simple constraints (edge allowlists + hop budgets + per-hop policy checks) reduce leakage substantially while retaining most utility.

---

## 3) Threat model

### Attacker capabilities (realistic + publishable)
- **Content injection** into at least one source that becomes indexed (wiki page, ticket, shared doc, PR description, etc.)
- No need for direct DB admin access; attacker acts as a user in a shared system or through compromised ingestion.

### System assumptions
- Vector store supports similarity search over chunk embeddings.
- Graph database stores entities/relationships (docs, chunks, entities, systems, projects, owners, provenance).
- Pipeline:
  1. Vector search returns top-k chunks.
  2. Entity linking maps chunks → entity nodes.
  3. Graph expansion collects neighbors / related nodes / related chunks.
  4. Context set merged + reranked → LLM.

### Attacker goals
- **Exfiltration:** cause sensitive nodes/chunks to appear in retrieved context/citations.
- **Policy bypass:** induce cross-tenant or cross-clearance retrieval.
- **Manipulation:** steer the answer via poisoned neighborhoods (prompt injection content).

---

## 4) Definitions and metrics (core novelty)

### 4.1 Retrieval Pivot Risk (RPR)
**Definition:** Probability that a retrieval seed (from vector stage) causes inclusion of unauthorized or sensitive nodes/chunks during graph expansion.

Operationalize:
- Let `S(q)` be final retrieved set (chunks or docs) for query `q`.
- Let `Sensitive(x)` be a predicate for sensitivity tier or unauthorized policy.
- Then:
\[
RPR = \Pr_{q \sim Q}(\exists x \in S(q): Sensitive(x))
\]

### 4.2 Leakage@k
Count sensitive items in final top-k context set:
\[
Leakage@k(q) = |\{x \in S_k(q) : Sensitive(x)\}|
\]

### 4.3 Amplification Factor (AF)
Compare leakage of hybrid vs vector-only:
\[
AF = \frac{\mathbb{E}[Leakage@k]_{hybrid}}{\mathbb{E}[Leakage@k]_{vector}}
\]

### 4.4 Pivot Depth (PD)
Minimum graph hop distance from the seed anchor to first sensitive node encountered:
\[
PD(q) = \min \{ d(seed, x) : x \in S(q) \land Sensitive(x) \}
\]
If none found, PD = ∞.

### 4.5 Utility metrics (required for credibility)
- Answer accuracy (task-specific)
- Faithfulness / citation support rate
- Latency overhead (p50/p95)
- Retrieval precision/recall for known-answer benchmark

---

## 5) Hybrid-specific attack taxonomy

> Implement attacks as **simulated content injection** to stay safe-to-publish and reproducible.

### A1 — Vector Seed Steering (Centroid poisoning)
Craft injected chunks that are semantically close to many target queries.
- Goal: appear in top-k frequently
- Mechanism: broad language, common enterprise terms, high overlap with query intents

### A2 — Entity Anchor Injection
Injected chunks heavily mention high-value entities (systems, code names, owners) to force entity linking.
- Goal: map seed → sensitive node neighborhood

### A3 — Neighborhood Flooding (Graph gravity)
Create many nodes/edges around attacker-controlled entities so expansion biases toward attacker-selected paths.

### A4 — Bridge Node Attack
Create connector entities that plausibly relate to benign and sensitive subgraphs (shared vendors, shared project tags, reused abbreviations).

---

## 6) Mitigations to evaluate (defense suite)

### D1 — Policy-Checked Expansion (per-hop authZ)
Reapply authorization checks on **every hop and returned node** (not just on initial vector retrieval).

### D2 — Edge-Type Allowlisting (query-class aware)
Only traverse edge types explicitly permitted for the query class.
Example:
- “dependency” queries: allow `DEPENDS_ON`, `RUNS_ON`
- “ownership” queries: allow `OWNED_BY`, but restrict hop depth

### D3 — Budgeted Traversal
Hard caps:
- max hops
- max branching factor
- max total nodes visited
- timeouts / cost limits

### D4 — Provenance/Trust-Weighted Expansion
Maintain a trust score for nodes/edges based on provenance and apply:
- downweight low-trust sources in reranking
- or forbid expansion across low-trust boundaries

### D5 — Merge-time Policy Filter + Rerank
After merging vector+graph results:
- apply strict deny-by-default policy filter
- rerank with a model that penalizes low-trust / near-duplicate spam

---

## 7) Benchmark testbed design (reproducible)

### 7.1 Data components
- **Documents:** plain text (wikis, tickets, runbooks, code docs)
- **Chunks:** 200–500 token segments with stable `chunk_id`
- **Entities:** extracted (NER) and normalized IDs
- **Graph:** nodes + edges as below
- **Labels:** sensitivity tier + tenant + clearance attributes

### 7.2 Recommended approach for “enterprise realism”
- Combine:
  - a public corpus (e.g., software docs, security advisories) for base
  - synthetic “sensitive” overlays (M&A, credentials, HR, customer names)
- Create “tenants” by partitioning docs/projects; include some shared vendors to simulate plausible bridges.

### 7.3 Sensitivity tiers (example)
- `PUBLIC`
- `INTERNAL`
- `CONFIDENTIAL`
- `RESTRICTED`

Also a policy predicate:
- `Authorized(user, item)` derived from tenant + clearance.

---

## 8) Graph schema (starter, extensible)

### 8.1 Node types
- `Document(doc_id, title, source, tenant, sensitivity, created_at, provenance_score)`
- `Chunk(chunk_id, doc_id, tenant, sensitivity, embedding_ref, provenance_score)`
- `Entity(entity_id, type, canonical_name, tenant, sensitivity?)`
- `System(system_id, name, tenant, sensitivity)`
- `Project(project_id, name, tenant, sensitivity)`
- `User(user_id, tenant, clearance)`
- `Source(source_id, name, trust_level)`

### 8.2 Edge types
- `CONTAINS(Document → Chunk)`
- `MENTIONS(Chunk → Entity)`
- `BELONGS_TO(Document/Entity → Project)`
- `DEPENDS_ON(System/Project → System/Project)`
- `OWNED_BY(Project/System → User)`
- `DERIVED_FROM(Document/Chunk → Source)`
- `RELATED_TO(Entity ↔ Entity)` (optional, derived)

### 8.3 Expansion policies (examples)
- Default: from seed `Chunk`:
  1. `MENTIONS` → `Entity` (1 hop)
  2. `BELONGS_TO` → `Project` (2 hop)
  3. `CONTAINS` (Project’s docs) → `Chunk` (3 hop)
- Enforce allowlists, budgets, and per-hop authZ.

---

## 9) Pipeline variants to compare (experiments)

### P1 — Vector-only RAG
- similarity search with authZ prefilter
- optional reranker

### P2 — Graph-only retrieval
- start from extracted entities in query
- traverse for relevant chunks/docs

### P3 — Hybrid Vector→Graph expansion (baseline hybrid)
- vector seed → entity link → graph expand → merge → rerank

### P4–P8 — Hybrid + defenses
- +D1 (per-hop authZ)
- +D2 (edge allowlist)
- +D3 (budgets)
- +D4 (provenance weighting)
- +D5 (merge-time policy filter)
- plus ablations: each defense alone + combinations

---

## 10) Evaluation methodology

### 10.1 Query sets
- **Benign queries:** normal enterprise questions (runbooks, architecture, ownership, dependency)
- **Adversarial queries:** same intents but phrased to maximize semantic overlap or trigger expansion
- **Attack-assisted queries:** queries paired with injected content

### 10.2 Sensitivity exposure evaluation
Compute for each query and pipeline:
- RPR
- Leakage@k
- AF (hybrid vs vector-only)
- PivotDepth
- Count of unauthorized items retrieved (policy violations)

### 10.3 Utility evaluation
- Use a small QA benchmark derived from the corpus:
  - answers must cite correct doc/chunk
- Score:
  - exact match / fuzzy match
  - citation support rate
  - faithfulness checks (claim supported by retrieved chunk)
- Track latency overhead of graph expansion + defenses.

---

## 11) Expected results (what you want to show)
- Hybrid baseline (P3) shows materially higher RPR and AF than vector-only (P1).
- Attacks A1–A4 increase AF dramatically with small injection budgets.
- D1 + D2 + D3 reduce RPR sharply with moderate utility impact.
- D4 improves robustness specifically under poisoning/flooding attacks.

---

## 12) Paper outline (ready to write)

1. **Abstract**
2. **Introduction**
   - hybrid RAG adoption, risk gap, contributions
3. **Background**
   - vector retrieval, GraphRAG, hybrid patterns
4. **Threat Model**
5. **Retrieval Pivot Attacks**
   - taxonomy A1–A4
6. **Metrics**
   - RPR, AF, PivotDepth, Leakage@k
7. **Experimental Setup**
   - datasets, graph schema, pipelines
8. **Results**
   - baseline comparisons + attacks
9. **Mitigations**
   - D1–D5 and ablations
10. **Discussion**
    - tradeoffs, operational guidance
11. **Limitations**
12. **Related Work**
13. **Conclusion**
14. **Artifact Appendix**
    - configs, seeds, reproducibility steps

---

## 13) Repo scaffold (GitHub-ready)

```
hybrid-rag-pivot-risk/
  README.md
  LICENSE
  pyproject.toml
  configs/
    pipelines/
      vector_only.yaml
      graph_only.yaml
      hybrid_baseline.yaml
      hybrid_defenses.yaml
    datasets/
      synthetic_enterprise.yaml
  data/
    raw/                # optional (or use scripts to fetch/generate)
    processed/
    graphs/
    embeddings/
  src/
    pivorag/
      __init__.py
      ingestion/
        chunker.py
        entity_extract.py
        provenance.py
      vector/
        embed.py
        index.py
        retrieve.py
      graph/
        schema.py
        build_graph.py
        expand.py
        policy.py
      pipelines/
        vector_only.py
        graph_only.py
        hybrid.py
      attacks/
        seed_steering.py
        entity_anchor.py
        neighborhood_flood.py
        bridge_node.py
      defenses/
        per_hop_authz.py
        edge_allowlist.py
        budgets.py
        trust_weighting.py
        merge_filter.py
      eval/
        metrics.py
        benchmark.py
        run_eval.py
  notebooks/
    01_explore_dataset.ipynb
    02_results_plots.ipynb
  scripts/
    make_synth_data.py
    build_indexes.py
    run_all_experiments.sh
  results/
    tables/
    plots/
```

---

## 14) Implementation notes (safe + realistic)

- Avoid “weaponized” guidance: attacks are framed as *content injection in a simulated corpus* and measured via retrieval leakage metrics.
- Keep LLM generation optional: retrieval leakage can be measured without generating answers.
- If using an LLM to score faithfulness, keep it as an evaluation tool only.

---

## 15) Timeline (suggested milestones)

### Week 1–2: Testbed
- dataset generator + chunking
- embedding + vector index
- graph schema + builder
- baseline pipelines P1–P3

### Week 3–4: Attacks + metrics
- implement A1–A4 (simulation)
- implement metrics (RPR/AF/PD/Leakage@k)
- run baseline comparisons

### Week 5–6: Defenses
- D1–D3 first (high impact)
- D4–D5 second
- ablation studies

### Week 7–8: Paper + artifact polish
- results tables/plots
- reproducibility scripts
- write + submit

---

## 16) “Success checklist” for publication

- [ ] Clear novelty claim: hybrid pivot amplification
- [ ] Formal metric definitions + reproducible eval harness
- [ ] Strong baselines: vector-only + graph-only + hybrid
- [ ] Attack budget is small (e.g., 10 injected chunks) but impact is large
- [ ] Defenses are practical and measurable
- [ ] Open-source artifact passes reproducibility review

---

## 17) Next actions (immediately actionable)

1. Choose vector backend (e.g., FAISS) and graph backend (e.g., Neo4j) for the reference implementation.
2. Implement the synthetic enterprise dataset generator with:
   - tenant partitions
   - sensitivity tiers
   - a small number of bridge entities
3. Implement baseline P1–P3 and compute RPR/AF/PD.

---

*End of plan.*
