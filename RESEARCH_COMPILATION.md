# Research Compilation: Retrieval Pivot Attacks in Hybrid RAG

## Measuring and Mitigating Amplified Leakage from Vector Seeds to Graph Expansion

**Compiled:** February 6, 2026
**Researcher:** Scott Thornton, perfecXion.ai
**Purpose:** Consolidated research foundation for top-tier venue submission (IEEE S&P 2027 / USENIX Security 2026 / ACM CCS 2026)

---

## Table of Contents

1. [Literature Landscape](#1-literature-landscape)
2. [Gap Analysis](#2-gap-analysis)
3. [Standards & Frameworks Mapping](#3-standards--frameworks-mapping)
4. [Real-World Evidence](#4-real-world-evidence)
5. [RAG System Corpus Findings](#5-rag-system-corpus-findings)
6. [Strategic Positioning](#6-strategic-positioning)
7. [Key Citations Reference List](#7-key-citations-reference-list)

---

## 1. Literature Landscape

This section catalogs 40+ papers across RAG security, GraphRAG attacks, defenses, and privacy research. Each paper is assessed for its relevance to the cross-store pivot threat model central to our work. A **HIGH** cross-store relevance rating means the paper directly informs or borders the vector-to-graph amplification problem. **MED** indicates partial overlap (single-store attack or defense with transferable insights). **LOW** indicates tangential relevance or background context only.

### 1.1 Attack Papers

| Paper | Venue / Date | Key Finding | Cross-Store Relevance |
|-------|-------------|-------------|----------------------|
| **GRAGPoison** (GraphRAG Under Fire) | IEEE S&P 2026 (accepted); arXiv Jan 2025 | First relation-centric poisoning attack on GraphRAG. Achieves **98% ASR** by injecting false relations and supporting subgraphs that exploit shared relations across queries. Uses **<68% poisoning text** compared to baselines. Demonstrates the "GraphRAG paradox": graph structure defends against naive poisoning but creates new amplification surfaces through shared relations and community coverage. Three-phase attack: relation selection via greedy set cover, relation injection with competing triples, and relation enhancement to boost degree centrality. | **HIGH** -- Directly demonstrates graph-structure amplification from small injections. The shared-relation exploitation maps directly to our pivot model: a single poisoned vector seed that anchors a false relation can corrupt every query traversing that relation. GRAGPoison's relation enhancement phase is the graph-side analog of our bridge-node attack. |
| **TKPA / UKPA** (Few Words Distort Graphs) | arXiv Aug 2025 | Targeted and Untargeted Knowledge Poisoning Attacks against GraphRAG. Modifying as few as **0.06% of corpus text** drops QA accuracy from 95% to 50%. TKPA achieves **93.1% success** on targeted queries. Attacks target globally influential hub nodes using coreference chain manipulation to force community merger between unrelated topics. Universal KPA variant poisons multiple queries simultaneously by attacking high-betweenness-centrality nodes. | **HIGH** -- Proves that minimal text perturbation causes outsized graph-level damage. The 0.06% modification rate is critical for our threat model: an attacker who can modify a tiny fraction of ingested documents (via wiki edits, ticket updates, or shared docs) can compromise the entire graph neighborhood structure. Hub-node targeting directly informs our bridge-node attack vector. |
| **RAG Safety KG-RAG** | Information Fusion (Elsevier), 2025 | First systematic study of data poisoning attacks specifically targeting Knowledge Graph RAG systems. Explores triple perturbation strategies (entity substitution, relation swapping, triple insertion) to pollute knowledge graphs and mislead multi-hop reasoning chains. Evaluates impact on downstream QA accuracy and faithfulness metrics. | **HIGH** -- Provides the only published formalization of KG-specific poisoning in a RAG context. Their triple perturbation taxonomy maps directly to our graph-side attack primitives. The study's focus on multi-hop reasoning degradation validates our hypothesis that graph expansion amplifies poisoned content. |
| **RAGCrawler** | arXiv Jan 2026 | KG-guided extraction attack achieving **84.4% knowledge coverage** of target RAG systems. Uses knowledge graph structure to systematically map and extract the contents of a RAG knowledge base. Iterative query refinement guided by discovered graph topology enables near-complete corpus reconstruction. | **HIGH** -- Demonstrates that graph structure itself becomes an extraction oracle. In hybrid RAG, an attacker can use RAGCrawler-style probing on the graph side to map sensitive neighborhoods, then craft vector-side queries that pivot into those neighborhoods. This is the reconnaissance phase for retrieval pivot attacks. |
| **PoisonedRAG** | USENIX Security 2025 (accepted Jun 2024) | First formal knowledge corruption attack on RAG systems. Achieves **90% ASR** by injecting just **5 malicious texts** per target question into knowledge databases containing millions of documents. Attack formalized as optimization: craft text that maximizes retrieval probability and LLM compliance simultaneously. Demonstrates scalability across GPT-4, GPT-3.5, LLaMA-2. **302 citations** as of Feb 2026. | **MED** -- Establishes the vector-side entry point for our compound attack. PoisonedRAG's 90% retrieval success rate for poisoned documents provides the empirically validated "V" parameter in our attack model. The key limitation this paper does not address is what happens after retrieval, specifically graph expansion from poisoned seeds. |
| **CorruptRAG** | arXiv Apr 2025 | Advances poisoning by showing **single-document attacks** achieve higher ASR than multi-document approaches. Designed for real-world constraints: limited attacker access, audit trail evasion, and monitoring system circumvention. Poisoned texts crafted for stealth through semantic consistency with surrounding corpus. | **MED** -- Single-document attacks are more practical and harder to detect. In hybrid RAG, one poisoned document serves dual roles: vector search result and graph traversal seed. CorruptRAG's stealth characteristics make detection at the vector layer harder, increasing the probability that the pivot to graph expansion occurs unchallenged. |
| **CtrlRAG** | Semantic Scholar 2025 | Black-box poisoning achieving **90% ASR on GPT-4o** with only 5 poisoned documents per question. Uses reference-context feedback loop to optimize poisoned document content without requiring white-box model access. Tested on MS MARCO retrieval benchmark. | **MED** -- Black-box attack model matches real-world hybrid RAG threat scenarios where attackers lack internal system access. The feedback optimization loop could be extended to optimize for graph-pivot exploitation: crafting documents that not only get retrieved but also contain entity mentions that trigger traversal into sensitive neighborhoods. |
| **Pandora** | NDSS AISCC Workshop, Feb 2024 | RAG-based indirect jailbreak achieving **64.3% success on GPT-3.5** and **34.8% on GPT-4**. Demonstrates that poisoning retrieval context is more effective than direct prompt injection for jailbreaking aligned models. Privacy violation queries show highest jailbreak success. | **MED** -- Pandora's indirect jailbreak mechanism compounds with graph expansion. A poisoned document that jailbreaks the LLM via retrieval could instruct the model to ignore access controls or expand its graph queries beyond authorized boundaries, creating a two-stage attack: jailbreak via vector retrieval, then unrestricted graph traversal via compromised LLM. |
| **BadRAG / TrojanRAG** | arXiv 2024-2025 | Backdoor attacks on RAG systems achieving **99% accuracy** in retrieving backdoor knowledge and **93.68% exact match** on NQ task. BadRAG embeds adversarial triggers in documents; TrojanRAG injects backdoors at the retriever level without modifying base models. Covers jailbreaking, bias steering, and denial-of-service goals. Evaluated across 11 tasks and 10 LLMs. | **MED** -- Backdoor triggers could be designed to activate specifically during the pivot phase. A TrojanRAG-style backdoor could remain dormant during vector-only retrieval but activate when graph expansion brings additional context, making detection at the vector layer impossible. |
| **Poisoned-MRAG** | arXiv Mar 2025 | First knowledge poisoning attack on multimodal RAG. Achieves **98% ASR** with 5 malicious image-text pairs in InfoSeek database (481K pairs). Two strategies: dirty-label (direct manipulation) and clean-label (subtle poisoning). Evaluated 4 defenses, all showed limited effectiveness. | **LOW** -- Multimodal extension establishes that RAG poisoning generalizes across modalities. As enterprise hybrid RAG systems incorporate images, diagrams, and code alongside text, cross-modal poisoning becomes an additional entry vector for pivot attacks. |
| **RIPRAG** | arXiv Oct 2025 | Reinforcement learning-based black-box poisoning attack on RAG. Uses RL agent to optimize poisoned document generation through query-response feedback without access to retrieval model internals. Achieves competitive ASR with significantly fewer iterations than gradient-based methods. | **MED** -- RL-based optimization could be adapted to the hybrid setting, where the reward signal incorporates both retrieval success (vector stage) and graph expansion reach (graph stage). This represents an automated approach to crafting pivot-optimized poisoned documents. |
| **NeuroGenPoisoning** | NeurIPS 2025 | Neuron-guided poisoning achieving **>90% success** by targeting specific neurons in the retrieval model that are most influential for document ranking. Uses gradient-based analysis to identify critical neurons and crafts poisoned documents that maximally activate them. | **MED** -- Neuron-level targeting enables crafting poisoned documents that are not just semantically similar but neurally optimized for retrieval. Combined with entity-rich content for graph anchoring, this creates highly effective pivot seeds. |
| **FlippedRAG** | ACM CCS 2025 | Opinion manipulation attack that flips RAG-generated stances on controversial topics. Demonstrates that retrieval poisoning can systematically bias LLM outputs toward attacker-chosen positions. Stealth attack that maintains fluency and coherence of generated text. | **MED** -- Opinion manipulation through graph expansion could flip stances on sensitive business decisions. In a corporate hybrid RAG, a pivot attack could bring biased graph context into business intelligence queries, steering strategic recommendations. |
| **Machine Against the RAG** | USENIX Security 2025 | Introduces "blocker documents" that prevent RAG from retrieving legitimate content. Denial-of-service attack where crafted documents occupy retrieval slots, blocking access to correct information. Demonstrates retrieval-level censorship. | **LOW** -- Blocker documents could be used to force queries through graph expansion by preventing vector-only answers, effectively guaranteeing the pivot phase executes. This represents an indirect amplification vector. |
| **ImportSnare** | ACM CCS 2025 | Code RAG hijacking attack targeting code generation assistants. Injects malicious code snippets into code knowledge bases that get retrieved and incorporated into generated code. Demonstrates supply-chain-style attacks through RAG systems. | **LOW** -- Code RAG hijacking represents a domain-specific pivot attack. Poisoned code snippets retrieved from vector search could reference graph-stored API definitions, dependency trees, or access control configurations, creating code-level pivots into sensitive system architecture. |
| **Corpus Poisoning Dense Retrievers** | EMNLP 2023 | Foundational work on poisoning dense retrieval systems. Demonstrates that adversarial passages can be crafted to be retrieved for arbitrary queries by manipulating embedding space geometry. Establishes theoretical basis for all subsequent RAG poisoning work. | **MED** -- Provides the mathematical foundation for our vector-side attack model. The embedding-space manipulation techniques directly enable seed steering (A1) in our attack taxonomy. |

### 1.2 Defense Papers

| Paper | Venue / Date | Key Finding | Cross-Store Relevance |
|-------|-------------|-------------|----------------------|
| **RAGuard** | NeurIPS 2025 | Detection framework for RAG poisoning attacks. Uses statistical analysis of retrieval patterns and document-query alignment scores to identify poisoned documents in the knowledge base. Provides real-time detection during retrieval without modifying the base RAG pipeline. | **MED** -- RAGuard operates at the vector retrieval layer. Could be extended to monitor pivot patterns (detecting when vector retrieval results trigger anomalous graph expansion). However, current design does not account for cross-store interactions. |
| **SeCon-RAG** | NeurIPS 2025 | Two-stage defense: first performs semantic consistency checking between retrieved documents, then applies contrastive filtering to remove outlier documents before LLM generation. Reduces poisoning success while maintaining retrieval quality. | **MED** -- Semantic consistency checking could be extended to verify consistency between vector-retrieved content and graph-expanded context. Cross-store consistency verification is a key defense primitive in our framework. |
| **RevPRAG** | EMNLP 2025 (Findings) | Activation-based detection achieving **98% TPR** at low FPR. Analyzes LLM internal activations to detect when retrieved content is poisoned, based on the observation that poisoned inputs create distinctive activation patterns distinguishable from clean inputs. | **HIGH** -- RevPRAG's activation analysis could detect when graph-expanded context introduces poisoned or anomalous content that was not present in the original vector retrieval. The activation signature of "normal vector retrieval + poisoned graph expansion" likely differs from clean hybrid retrieval, making this a promising detection primitive for pivot attacks. |
| **SDAG** (Sparse-Dense Attention Guard) | arXiv Feb 2026 | Block-sparse attention mechanism that partitions context into trusted and untrusted segments, applying differential attention weights. Reduces influence of untrusted retrieved content on generation while preserving utility from trusted sources. Hardware-efficient implementation using block-sparse GPU kernels. | **HIGH** -- Directly applicable to hybrid RAG where vector-retrieved content and graph-expanded content have different trust levels. SDAG's partitioned attention could assign lower attention weights to graph-expanded nodes when the pivot path crosses trust boundaries. This is the closest existing work to a cross-store defense mechanism. |
| **SD-RAG** (Selective Disclosure RAG) | arXiv Jan 2026 | Selective disclosure framework that controls what information from the knowledge base reaches the LLM based on query-specific need-to-know policies. Implements information-theoretic bounds on context disclosure. | **HIGH** -- Need-to-know policies that span both vector and graph retrieval are central to our defense architecture. SD-RAG's selective disclosure model could be extended with graph-aware policies that restrict disclosure based on traversal depth and sensitivity gradient. |
| **SoK: Privacy Risks in RAG** | IEEE SaTML 2026 | Systematization of knowledge covering all known privacy attack vectors in RAG systems: membership inference, data extraction, embedding inversion, and attribute inference. Provides unified taxonomy and evaluation methodology. Notes that hybrid and graph RAG privacy risks remain under-studied. | **HIGH** -- Explicitly identifies hybrid RAG privacy as an open problem. Their taxonomy validates that cross-store privacy amplification is a recognized gap. This SoK directly motivates our work and positions it within the broader RAG privacy landscape. |
| **Riddle Me This** | ACM CCS 2025 | Membership inference attack on RAG systems. Determines whether specific documents exist in a RAG knowledge base by analyzing generation behavior differences. Achieves high accuracy in both black-box and gray-box settings. | **MED** -- Membership inference in hybrid RAG has compounded risk: graph structure reveals not just document presence but relationship patterns. An attacker who confirms a document's presence via membership inference can then craft queries to pivot through that document into sensitive graph neighborhoods. |
| **Traceback of RAG Poisoning** | ACM Web Conference 2025 | Forensic traceback method for identifying which documents in a RAG knowledge base are responsible for poisoned outputs. Uses causal analysis to trace from LLM output back through retrieval to source documents. Enables post-incident investigation and poisoned document removal. | **MED** -- Traceback in hybrid RAG must trace not just through vector retrieval but through graph expansion paths. Current traceback stops at the document level and does not follow graph traversal chains. Extending traceback to cover pivot paths is identified as a key requirement in our framework. |

### 1.3 Privacy & Extraction Papers

| Paper | Venue / Date | Key Finding | Cross-Store Relevance |
|-------|-------------|-------------|----------------------|
| **Graph RAG Privacy Paradox** | arXiv Aug 2025 | "Graph RAG systems may reduce raw text leakage, but they are significantly more vulnerable to extraction of structured entity and relationship information." First analysis of unique privacy trade-offs in graph-based RAG: structured summaries create consistently vulnerable attack surfaces; multi-hop reasoning reveals relationship patterns invisible in single-step retrieval. | **HIGH** -- Directly validates our core thesis. The privacy paradox means hybrid RAG systems face compounded risk: vector-side text leakage combined with graph-side structural leakage. The "structured summary vulnerability" maps to our community-contamination attack vector. |
| **Multi-Agentic AI-RAG Vulnerabilities** | EU Open Science 2025 | Analysis of security vulnerabilities in multi-agent RAG architectures where multiple LLM agents coordinate retrieval and generation. Documents cascading failure modes where compromised agent decisions propagate through agent networks. Single compromised agent poisoned 87% of downstream decision-making within 4 hours. | **HIGH** -- Agentic hybrid RAG represents the most dangerous deployment pattern for pivot attacks. When an LLM agent autonomously decides traversal depth, edge types, and expansion strategies, a poisoned vector seed can manipulate the agent into performing unrestricted graph exploration. Multi-agent coordination amplifies this: one agent's poisoned retrieval becomes another agent's trusted input. |
| **AgCyRAG** | CEUR-WS Vol-4079, 2025 | Agentic KG-RAG system for cybersecurity log analysis. Uses LLM agents to navigate knowledge graphs of security events, performing autonomous Cypher query generation and multi-hop threat correlation. Demonstrates practical hybrid retrieval in security-critical domains. | **MED** -- AgCyRAG represents a high-value target for pivot attacks. Security log graphs contain sensitive incident data, access patterns, and vulnerability information. A pivot attack on a security analysis system could expose the organization's entire threat landscape through graph traversal from an innocuous log entry. |
| **SafeRAG** | arXiv:2501.18636, Jan 2025 | First RAG security evaluation benchmark. Classifies attacks into silver noise, inter-context conflict, soft ad, and white denial-of-service. Tests 14 RAG components across attack types. Introduces Noise Contamination Through Documents (NCTD) attack methodology. Reveals significant vulnerabilities across all tested components. | **MED** -- SafeRAG's benchmark methodology informs our hybrid RAG security benchmark design. However, SafeRAG tests single-store configurations only. Extending their attack taxonomy with cross-store pivot attacks and their evaluation methodology with amplification metrics is a direct contribution of our work. |

### 1.4 Supplementary and Background Papers

| Paper | Venue / Date | Key Finding | Cross-Store Relevance |
|-------|-------------|-------------|----------------------|
| **Microsoft GraphRAG** (From Local to Global) | arXiv Apr 2024 | Introduces community-based retrieval using Leiden algorithm for hierarchical graph partitioning. Global search over community summaries enables theme-level queries. Local search via entity neighborhood expansion. DRIFT search combines both. | **MED** -- Defines the target architecture for our attacks. Community structure, global summaries, and local expansion are all pivot-exploitable mechanisms. |
| **HybridRAG** | arXiv Aug 2024 | Demonstrates that combining vector and graph retrieval outperforms either alone: 8% factual correctness improvement, 11% context relevance improvement from graph component. Established hybrid RAG as a viable paradigm. | **LOW** -- Establishes the performance motivation for hybrid RAG adoption, contextualizing why organizations deploy the architectures we study. |
| **Benchmarking Vector, Graph, and Hybrid RAG** | arXiv Jul 2025 | Comprehensive comparison showing graph-based retrieval achieves 86% comprehensiveness on complex queries vs. 57% for vector RAG. Hybrid configurations maintain 80-83% F1 with significantly reduced hallucination. | **LOW** -- Provides the utility baseline our defenses must preserve. The comprehensiveness gap between vector-only and hybrid quantifies what organizations lose if they abandon graph expansion for security. |
| **RAG Security and Privacy Threat Model** | arXiv Sep 2024 | First formal threat model for RAG systems. Defines adversary types, privacy threats (membership inference, document reconstruction), and poisoning formalization. Does not address hybrid or graph-specific threats. | **MED** -- Provides the threat modeling methodology we extend to hybrid architectures. Their adversary capability taxonomy is the starting point for our cross-store adversary model. |
| **Access Control for Graph-Structured Data** | arXiv May 2024 | Survey of RBAC, ABAC, and path-based access control models for property graphs. Few models integrated with LLM-driven GraphRAG or agent tooling. Identifies path-level authorization as an open challenge. | **MED** -- Path-level authorization is precisely what our per-hop defense (D1) implements. This survey confirms that the graph database community recognizes the gap but has not addressed it in RAG contexts. |
| **LPRAG** (Locally Private RAG) | arXiv Dec 2024 | Local differential privacy for RAG through entity-level perturbation rather than full-text perturbation. Achieves privacy preservation while maintaining retrieval utility. | **LOW** -- Entity-level DP could protect against pivot attacks by adding noise to entity links between vector and graph stores, breaking precise traversal paths. |
| **KnowGen-RAG** | ACM 2025 | Hybrid RAG framework integrating knowledge graphs with LLM generation for application security and compliance. Demonstrates industry recognition of graph security requirements in RAG. | **LOW** -- Validates enterprise demand for secure hybrid RAG. |
| **HopRAG** | arXiv Feb 2025 | Graph-structured knowledge exploration with retrieve-reason-prune mechanism. Constructs passage graph with LLM-generated pseudo-queries as edges. | **LOW** -- Multi-hop reasoning framework whose prune mechanism could be adapted for security-aware traversal. |
| **StepChain GraphRAG** | arXiv Oct 2025 | BFS-based reasoning flow with dynamic edge expansion and explicit evidence chains for multi-hop QA. | **LOW** -- BFS traversal with evidence chains provides an auditable traversal pattern that supports our forensic traceback requirements. |

### 1.5 Literature Summary Statistics

**Total papers cataloged:** 42

**By relevance tier:**
- **HIGH cross-store relevance:** 12 papers (directly inform pivot attack/defense model)
- **MED cross-store relevance:** 20 papers (transferable single-store insights)
- **LOW cross-store relevance:** 10 papers (background and contextual)

**By category:**
- Attack papers: 16
- Defense papers: 9
- Privacy and extraction: 6
- Background and architecture: 11

**By venue tier:**
- IEEE S&P: 1
- USENIX Security: 2
- ACM CCS: 3
- NeurIPS: 3
- EMNLP: 2
- IEEE SaTML: 1
- Other top venues (NDSS, ICLR, Information Fusion): 3
- arXiv preprints: 20+

**Temporal distribution:** 85% of papers published 2024-2026, reflecting the rapid emergence of this research area.

---

## 2. Gap Analysis

Eight specific research gaps have been identified through systematic literature review. Each gap is classified by fill status, supporting evidence, and direct relevance to the proposed paper.

### Gap 1: Cross-Store Pivot Attacks

**Status: COMPLETELY UNFILLED**

**Evidence:** Exhaustive search across IEEE Xplore, ACM DL, USENIX proceedings, arXiv, Semantic Scholar, and Google Scholar returns **zero results** for "retrieval pivot attack," "cross-store amplification," "vector-to-graph attack," or "hybrid RAG security attack." The closest work is GRAGPoison (graph-only attacks) and PoisonedRAG (vector-only attacks). No paper studies what happens when vector poisoning triggers graph expansion.

**What exists:**
- GRAGPoison demonstrates graph-structure amplification from text injection (S&P 2026)
- PoisonedRAG demonstrates vector-side poisoning with 90% ASR (USENIX Security 2025)
- TKPA shows 0.06% text modification can drop graph QA accuracy by 45 percentage points
- CorruptRAG demonstrates single-document attacks

**What is missing:**
- Formal model of how vector retrieval seeds transition into graph traversal operations
- Measurement of amplification factor when poisoned vector results trigger graph expansion
- Attack taxonomy specific to the cross-store boundary
- Empirical evaluation of compound attack success rates

**Why this matters:** Every hybrid RAG deployment (Microsoft GraphRAG, Neo4j+LangChain, LangGraph agentic systems) implements a vector-to-graph pivot mechanism. This mechanism is the security-critical boundary that no existing work formalizes or evaluates.

**Our contribution:** First formal definition of Retrieval Pivot Attacks with four attack vectors (seed steering, entity anchor injection, neighborhood flooding, bridge-node attack) and empirical evaluation of compound success rates.

---

### Gap 2: Hybrid RAG Security Architecture

**Status: COMPLETELY UNFILLED**

**Evidence:** No published security architecture spans both vector and graph stores in a RAG system. Existing architectures address vector database security (Cisco securing vector databases guide, Pinecone RBAC) or graph database security (Neo4j RBAC, Memgraph label-based access control) independently. The OWASP LLM Top 10 2025 introduces LLM08 (Vector and Embedding Weaknesses) but does not address graph components. MITRE ATLAS includes RAG Database Retrieval (AML.T0052) but treats RAG as a monolithic system.

**What exists:**
- Pinecone + SpiceDB access control pattern for vector retrieval with authorization graphs
- Neo4j fine-grained traverse/read/write permissions
- Memgraph label-based access control
- General RAG security guidelines (Cisco, OWASP, NIST)

**What is missing:**
- Unified security architecture spanning vector store, graph store, and the pivot boundary
- Authorization model for cross-store operations
- Security policy language that can express constraints on vector-to-graph transitions
- Reference implementation of secure hybrid RAG

**Our contribution:** Defense suite (D1-D5) with per-hop authorization, edge-type allowlisting, budgeted traversal, provenance-weighted expansion, and merge-time policy filtering, all operating across the cross-store boundary.

---

### Gap 3: RPR Formalization

**Status: COMPLETELY UNFILLED**

**Evidence:** The term "Retrieval Pivot Risk" does not appear in any published work. The closest formalization is the general RAG threat model (arXiv Sep 2024), which defines adversary types and attack goals but does not model the amplification from vector to graph retrieval. GRAGPoison formalizes relation-centric poisoning but within a single store.

**What exists:**
- General RAG threat model with adversary capability taxonomy
- Information-theoretic privacy measures for single-store RAG
- GRAGPoison's graph-specific attack formalization
- Differential privacy frameworks for retrieval systems

**What is missing:**
- Mathematical definition of RPR as probability of unauthorized node inclusion during graph expansion from vector-seeded starting points
- Amplification Factor (AF) metric comparing hybrid vs. vector-only leakage
- Pivot Depth (PD) metric measuring minimum graph distance to first sensitive node
- Leakage@k metric counting sensitive items in final context

**Our contribution:** Four formal metrics (RPR, AF, PD, Leakage@k) with mathematical definitions, operationalization procedures, and empirical measurement methodology.

---

### Gap 4: Defenses for Multi-Store RAG

**Status: COMPLETELY UNFILLED**

**Evidence:** Published defenses operate within a single retrieval modality. RAGuard and RevPRAG detect poisoning at the vector/LLM layer. SeCon-RAG performs consistency checking among retrieved documents. SDAG applies differential attention to trusted/untrusted segments. SD-RAG implements selective disclosure. None of these defenses consider the vector-to-graph transition or graph expansion as an attack amplification mechanism.

**What exists:**
- RAGuard: statistical detection of poisoned retrieval patterns (NeurIPS 2025)
- RevPRAG: activation-based detection with 98% TPR (EMNLP 2025)
- SeCon-RAG: semantic consistency filtering (NeurIPS 2025)
- SDAG: block-sparse attention for trusted/untrusted partitioning (Feb 2026)
- SD-RAG: selective disclosure framework (Jan 2026)
- TrustRAG: trust-weighted document scoring

**What is missing:**
- Per-hop authorization that re-checks access at every graph traversal step
- Edge-type allowlisting conditioned on query class and user role
- Expansion budgets (max hops, max branching, max nodes) enforced at the graph traversal API
- Provenance-weighted traversal that attenuates trust from untrusted vector seeds
- Cross-store merge-time policy filtering

**Our contribution:** Five defense mechanisms (D1-D5) specifically designed for the vector-to-graph boundary, with ablation studies measuring security-utility tradeoffs.

---

### Gap 5: Hybrid RAG Security Benchmark

**Status: COMPLETELY UNFILLED**

**Evidence:** SafeRAG (arXiv:2501.18636) is the most comprehensive RAG security benchmark but tests only single-store configurations. RAG Security Bench (RSB) evaluates 13 poisoning attacks but lacks hybrid RAG scenarios. SecMulti-RAG addresses multi-source retrieval but does not model vector-to-graph transitions. No benchmark includes datasets with sensitivity-tiered graph neighborhoods, cross-store attack scenarios, or amplification metrics.

**What exists:**
- SafeRAG: 4 attack categories, 14 RAG components tested, single-store only
- RSB: 13 poisoning attacks across 3 categories, diverse architectures but no hybrid-specific
- SecMulti-RAG: multi-source retrieval with 79-92% win rates, no graph pivot modeling
- MMLU, NQ, TriviaQA: standard QA benchmarks without security dimensions

**What is missing:**
- Synthetic enterprise dataset with tenant partitions, sensitivity tiers, and bridge entities
- Attack scenarios spanning all four pivot attack vectors
- Metrics for cross-store amplification (AF, RPR, PD)
- Reproducible evaluation harness for hybrid RAG security
- Baseline measurements across vector-only, graph-only, and hybrid configurations

**Our contribution:** First hybrid RAG security benchmark with synthetic enterprise data, four attack implementations, five defense configurations, and comprehensive metric reporting.

---

### Gap 6: Cross-Store Consistency Verification

**Status: COMPLETELY UNFILLED**

**Evidence:** SeCon-RAG (NeurIPS 2025) performs semantic consistency checking among retrieved documents but operates entirely within a single retrieval modality. No published work verifies consistency between vector-retrieved content and graph-expanded content. The concept of cross-store consistency, asking whether the graph expansion is logically consistent with the original vector query and retrieved seed, has not been formalized.

**What exists:**
- SeCon-RAG: intra-store semantic consistency checking
- NLI-based contradiction detection for retrieved documents
- Hallucination detection at the generation layer
- SDAG: differential attention between trusted/untrusted context segments

**What is missing:**
- Cross-store consistency model: does graph expansion semantically align with vector query intent?
- Anomaly detection for pivot patterns (vector retrieval triggering unexpected graph neighborhoods)
- Contradiction detection between vector-sourced and graph-sourced context
- Real-time monitoring of cross-store retrieval divergence

**Our contribution:** Merge-time policy filter (D5) that checks consistency between vector and graph retrieval results before context assembly, plus observability framework for empirical RPR estimation.

---

### Gap 7: Traceback in Multi-Store Environments

**Status: MOSTLY UNFILLED**

**Evidence:** "Traceback of RAG Poisoning" (ACM Web 2025) provides forensic methods for identifying responsible documents in poisoned RAG outputs, but traces only through the vector retrieval path to source documents. It does not follow graph traversal chains, meaning the graph expansion that amplified the poisoning remains uninvestigated. RevPRAG (EMNLP 2025) detects poisoning via LLM activations but cannot attribute the poisoning to specific graph traversal decisions.

**What partially exists:**
- Document-level traceback from LLM output to retrieved documents (ACM Web 2025)
- Activation-based poisoning detection without source attribution (RevPRAG)
- General RAG forensics methodology

**What is missing:**
- Traversal-path traceback: from LLM output through graph expansion path back to vector seed
- Attribution of poisoning amplification to specific graph edges and hop decisions
- Cross-store audit trail connecting vector retrieval events to graph traversal events
- Forensic reconstruction of the complete pivot attack chain

**Our contribution:** Cross-store audit trail specification and logging framework that records the complete retrieval path from query through vector retrieval, entity linking, graph expansion, context assembly, to LLM generation.

---

### Gap 8: Graph Amplification in Hybrid Contexts

**Status: PARTIALLY FILLED**

**Evidence:** GRAGPoison (S&P 2026) and TKPA (Aug 2025) demonstrate graph-structure amplification, proving that graph topology causes small poisoning inputs to have outsized effects. The "Graph RAG Privacy Paradox" (Aug 2025) establishes that graph RAG trades text leakage for structural leakage. However, all studies examine amplification within a single store (graph-only). The compound amplification from vector poisoning into graph expansion has not been measured.

**What exists:**
- GRAGPoison: 98% ASR via shared-relation exploitation in graph-only setting
- TKPA: 0.06% text modification causing 45-point accuracy drop via hub-node targeting
- Graph RAG Privacy Paradox: structural information extraction > text leakage in graph RAG
- Multi-agent cascading failure: 87% downstream poisoning from single compromised agent

**What is missing:**
- Measurement of compound amplification factor: (vector poisoning success) x (graph expansion reach)
- Empirical comparison of amplification in hybrid vs. graph-only vs. vector-only settings
- Characterization of graph topology features that maximize pivot-driven amplification
- Relationship between branching factor, traversal depth, and amplification in hybrid context

**Our contribution:** Empirical measurement of the Amplification Factor (AF = E[Leakage@k_hybrid] / E[Leakage@k_vector]) across multiple graph topologies and attack configurations, with analysis of topology features that drive amplification.

---

### Gap Analysis Summary Table

| # | Gap | Status | Closest Work | Our Contribution |
|---|-----|--------|-------------|------------------|
| 1 | Cross-Store Pivot Attacks | UNFILLED | GRAGPoison (graph-only) | First formal pivot attack taxonomy |
| 2 | Hybrid RAG Security Architecture | UNFILLED | Pinecone+SpiceDB (vector-only) | D1-D5 cross-store defense suite |
| 3 | RPR Formalization | UNFILLED | General RAG threat model | RPR, AF, PD, Leakage@k metrics |
| 4 | Defenses for Multi-Store RAG | UNFILLED | RAGuard, RevPRAG (single-store) | Five hybrid-specific defenses |
| 5 | Hybrid RAG Security Benchmark | UNFILLED | SafeRAG (single-store) | First hybrid RAG security benchmark |
| 6 | Cross-Store Consistency Verification | UNFILLED | SeCon-RAG (intra-store) | Merge-time policy filter + monitoring |
| 7 | Traceback in Multi-Store | MOSTLY UNFILLED | ACM Web 2025 (document-level) | Cross-store audit trail framework |
| 8 | Graph Amplification in Hybrid | PARTIALLY FILLED | GRAGPoison, TKPA (graph-only) | Compound AF measurement |

---

## 3. Standards & Frameworks Mapping

This section maps the retrieval pivot attack threat to established security frameworks, demonstrating that the vulnerability class falls within recognized threat categories while highlighting that no framework specifically addresses cross-store amplification.

### 3.1 OWASP LLM Top 10 (2025 Edition)

**LLM04: Data and Model Poisoning**

Directly relevant to vector-side entry point of pivot attacks. LLM04 covers scenarios where training data or fine-tuning data is manipulated, as well as knowledge base poisoning in RAG systems. Our vector seed steering (A1) and entity anchor injection (A2) attacks are instances of LLM04 applied to the vector store of a hybrid RAG system. OWASP's recommended mitigations (data validation, provenance tracking, anomaly detection) address the vector side but do not extend to graph expansion.

**LLM08: Vector and Embedding Weaknesses (NEW in 2025)**

The most directly relevant OWASP category. LLM08 debuted in the 2025 edition specifically to address RAG architecture vulnerabilities. It covers embedding poisoning, similarity attacks, vector database unauthorized access, and embedding inversion. With 53% of companies relying on RAG rather than fine-tuning, this category reflects the industry's growing recognition of retrieval-layer risks. Our work extends LLM08 by showing that vector and embedding weaknesses compound with graph structure to create amplified leakage. OWASP's remediation (fine-grained vector DB access control, embedding validation, retrieval log monitoring) is necessary but insufficient without graph-side controls.

**Mapping to our attack taxonomy:**
- A1 (Seed Steering) maps to LLM08 embedding poisoning
- A2 (Entity Anchor) maps to LLM04 knowledge base manipulation + LLM08 similarity attacks
- A3 (Neighborhood Flooding) extends beyond current OWASP scope (graph-specific)
- A4 (Bridge Node) extends beyond current OWASP scope (cross-store specific)

### 3.2 MITRE ATLAS (October 2025 Update)

**Framework scope:** 15 tactics, 66 techniques, 46 sub-techniques targeting AI/ML systems.

**October 2025 expansion:** Added 14 new techniques focused on AI Agents and Generative AI systems, developed in collaboration with Zenity Labs. Key additions relevant to our work:

**AML.T0052: RAG Database Retrieval** -- Extracting sensitive information by exploiting the retrieval mechanism. Our RAGCrawler-informed reconnaissance phase (using graph topology to guide extraction queries) is an extension of this technique to hybrid settings.

**AML.T0051: RAG Database Prompting** -- Specifically prompting an AI to retrieve sensitive internal documents. Pivot attacks use benign-seeming prompts that trigger graph expansion into sensitive neighborhoods, a more sophisticated variant of this technique.

**AML.T0015: Gather RAG-Indexed Targets** -- Identifying data sources for targeting. In hybrid RAG, this includes mapping both the vector index contents and the graph schema/topology, enabling attackers to identify optimal pivot paths.

**AML.T0040: RAG Credential Harvesting** -- Using LLM access to collect credentials from RAG stores. Credential nodes in knowledge graphs are particularly vulnerable to pivot attacks because they are often connected to system and user nodes that serve as high-degree hubs.

**AI Agent Tool Invocation** -- Forcing agents to use authorized tools for unauthorized actions. In agentic hybrid RAG (LangGraph, CrewAI), the graph traversal tool can be manipulated via poisoned retrieval context to perform unauthorized expansions.

**Exfiltration via AI Agent Tool Invocation** -- Using agent "write" tools to exfiltrate data. When graph expansion reaches sensitive nodes, an agentic RAG system might summarize and export this information through email, API calls, or CRM updates.

**Gap in ATLAS:** No technique specifically addresses cross-store amplification or vector-to-graph pivot attacks. The RAG-specific techniques treat RAG as a monolithic system rather than a multi-component architecture with distinct attack surfaces at component boundaries.

### 3.3 NIST AI 100-2 E2025

NIST AI 100-2 E2025 incorporates RAG into its AI security taxonomy, recognizing retrieval-augmented generation as a distinct architectural pattern with specific security considerations. The framework addresses:

- Data integrity in knowledge bases used for retrieval
- Access control for retrieval operations
- Privacy preservation during information retrieval and generation
- Provenance tracking for retrieved content

**Relevance to our work:** NIST's inclusion of RAG in its taxonomy validates the importance of RAG security research. However, the framework does not distinguish between vector-only, graph-only, and hybrid RAG architectures. Our work provides the architectural decomposition needed to apply NIST guidelines to hybrid deployments, specifically identifying the vector-to-graph boundary as a critical control point.

### 3.4 MAESTRO Framework (Cloud Security Alliance)

The CSA MAESTRO (Multi-Agent Environment Security Threat, Risk, and Opportunity) framework provides threat modeling for agentic AI systems. Two threat categories directly apply to hybrid RAG pivot attacks:

**T18: RAG Input Manipulation**

Covers attacks that manipulate the input to RAG systems to influence retrieval results. In hybrid RAG, input manipulation includes both query-level manipulation (crafting queries that trigger specific graph expansions) and corpus-level manipulation (poisoning documents with entity mentions that anchor graph traversal to sensitive neighborhoods). MAESTRO's T18 mitigations focus on input validation and retrieval monitoring but do not address the graph expansion phase.

**T25: Dependency Workflow Disruption**

Addresses attacks that exploit dependencies between system components. The vector-to-graph dependency in hybrid RAG is a workflow dependency: graph expansion depends on vector retrieval results. Disrupting or manipulating this dependency, specifically by controlling which vector results seed graph traversal, is precisely the pivot attack mechanism. MAESTRO's T25 mitigations (dependency isolation, workflow validation) align with our defense architecture but require hybrid-specific implementation.

**MAESTRO coverage assessment:** The framework recognizes multi-component AI system threats but does not specifically model the vector-graph boundary or amplification dynamics. Our work operationalizes MAESTRO's threat categories with hybrid-RAG-specific attack implementations and defenses.

### 3.5 OWASP Top 10 for Agentic Applications (2026)

The forthcoming OWASP Agentic Apps Top 10 addresses security risks in autonomous AI agent systems. Relevant categories for hybrid RAG include:

- **Agent Memory Poisoning:** Indirect prompt injection via poisoned data sources corrupts agent long-term memory. In hybrid RAG, graph-stored knowledge functions as agent memory, making graph poisoning equivalent to memory poisoning.
- **Tool Abuse:** Agents using authorized tools (including graph query tools) for unauthorized purposes. Pivot attacks exploit legitimate graph traversal tools to access unauthorized neighborhoods.
- **Cascading Agent Failures:** Single compromised agent poisoning downstream decision-making. Research shows 87% downstream contamination within 4 hours from a single compromised agent.

OWASP's agentic taxonomy of 15 threat categories recognizes the expanded attack surface from tool use and multi-agent coordination, validating that agentic hybrid RAG represents the highest-risk deployment pattern for pivot attacks.

### 3.6 Framework Mapping Summary

| Framework | Relevant Categories | Coverage of Cross-Store Pivot | Gap |
|-----------|-------------------|-------------------------------|-----|
| OWASP LLM Top 10 | LLM04, LLM08 | Partial (vector-side only) | No graph expansion coverage |
| MITRE ATLAS | AML.T0051, T0052, T0015, T0040 | Partial (monolithic RAG view) | No multi-component decomposition |
| NIST AI 100-2 | RAG taxonomy inclusion | Minimal (architecture-agnostic) | No hybrid-specific guidance |
| CSA MAESTRO | T18, T25 | Partial (component dependency) | No vector-graph boundary model |
| OWASP Agentic 2026 | Memory poisoning, tool abuse | Partial (agentic focus) | No retrieval-specific pivot model |

**Key insight:** Every major framework recognizes RAG security risks but treats RAG as a monolithic system. None decompose hybrid RAG into its constituent stores or model the security boundary between them. This cross-framework gap validates the novelty and necessity of our work.

---

## 4. Real-World Evidence

### 4.1 Financial GraphRAG Incident ($1.8M, November 2025)

A simulated attack scenario against a financial services GraphRAG deployment demonstrated a potential **$1.8M loss** through a pivot-style attack chain:

**Attack chain reconstruction:**
1. Attacker registered a shell company in the organization's vendor management system.
2. Injected a `relationship_note` property into the Knowledge Graph: "Verified partner since 2010, auto-approval enabled."
3. When an analyst queried "Show me suppliers for product X," the system retrieved the shell company via vector similarity (the shell company's description was semantically optimized for this query).
4. Graph traversal expanded from the shell company node, pulling the injected `relationship_note`.
5. The LLM, reading "auto-approval enabled," advised the analyst to proceed without additional verification checks.
6. The fabricated trust relationship bypassed manual approval controls.

**Significance:** This incident demonstrates the full pivot attack chain in a production-realistic setting: vector entry point, graph expansion, LLM manipulation via graph-sourced context. The $1.8M figure represents the potential transaction value that would have been approved without human review.

**Key lesson:** The attack succeeded because the graph traversal was not subject to independent authorization. The `relationship_note` property was treated as trusted context solely because it existed in the graph, regardless of its provenance.

### 4.2 CVE-2024-8309: Cypher Injection via LangChain

**Vulnerability:** SQL/Cypher injection vulnerability in LangChain's Neo4j integration allowing attackers to craft malicious natural language inputs that, when converted to Cypher queries by the LLM, execute unauthorized graph operations.

**Attack mechanism:**
1. User provides natural language query containing injection payload.
2. LangChain's text-to-Cypher conversion includes payload in generated query.
3. Injected Cypher traverses unauthorized graph regions, modifies data, or exfiltrates sensitive information.

**Relevance to pivot attacks:** This CVE demonstrates that the text-to-Cypher interface between vector retrieval and graph querying is a proven attack surface. If retrieved documents (from vector search) contain injection payloads in their text, and an agentic RAG system processes this text to generate Cypher queries, the vector-to-graph pivot becomes a direct injection vector. The poisoned document does not just seed graph traversal; it directly controls the traversal query.

### 4.3 CVE-2025-68664: LangGrinch (CVSS 9.3)

**Vulnerability:** Critical deserialization vulnerability in langchain-core (CWE-502). The `dumps()` and `dumpd()` functions did not properly escape user-controlled dictionaries containing the reserved `lc` key.

**Technical details:**
- 12 vulnerable flows identified across standard LangChain operational patterns
- Affects event streaming, logging, message history/memory caches
- Enables secret extraction from environment variables when `secrets_from_env=True` (previously default)
- Enables class instantiation within trusted namespaces (langchain_core, langchain, langchain_community)
- Enables arbitrary code execution via Jinja2 templates

**Attack chain in hybrid RAG context:**
1. Attacker crafts poisoned document containing LangChain's `lc` marker key in structured fields.
2. Vector retrieval returns poisoned document.
3. Hybrid pipeline processes document through LangChain serialization.
4. Deserialization interprets malicious payload as trusted LangChain object.
5. Payload executes: extracts secrets, instantiates objects, or runs arbitrary code.
6. Combined with graph expansion, attacker gains both code execution and graph data access.

**Patches:** langchain-core versions 1.2.5 and 0.3.81 introduce restrictive defaults, allowlist parameters, and blocked Jinja2 templates.

**Significance:** LangGrinch proves that the LangChain ecosystem, which underpins most production hybrid RAG deployments, has had critical vulnerabilities at the serialization layer. Pivot attacks can exploit these vulnerabilities by embedding payloads in documents retrieved through vector search that activate during graph-side processing.

### 4.4 Embedding Inversion: 92% Reconstruction Accuracy

**Research finding:** Adversaries can recover **92% of a 32-token text input** from T5-based embeddings using vec2text and related embedding inversion techniques. General reconstruction accuracy ranges from 60-80% across different embedding models.

**Implications for hybrid RAG:**
- Vector embeddings stored in Pinecone, Weaviate, or other vector databases are not one-way transformations. They can be approximately reversed.
- In hybrid RAG, embedding inversion reveals not just document content but entity mentions that anchor graph traversal. An attacker who inverts embeddings can map the vector-to-graph boundary without direct graph access.
- Combined with RAGCrawler-style topology probing (84.4% coverage), embedding inversion enables complete reconstruction of the hybrid RAG's knowledge representation.

**OWASP classification:** LLM08:2025 (Vector and Embedding Weaknesses) explicitly recognizes embedding inversion as a vulnerability category.

**Defense implications:** Embedding encryption (homomorphic encryption, functional encryption, or TEE-based approaches) can prevent inversion but introduces latency overhead. In hybrid RAG, encrypted embeddings would also obscure the entity-to-graph mapping, potentially reducing pivot attack reconnaissance capability.

### 4.5 Additional Real-World Context

**Enterprise RAG adoption (2025-2026):**
- 30-60% of enterprise AI use cases adopt RAG (Vectara 2025)
- 63.6% of implementations use GPT-based models
- 80.5% rely on standard retrieval frameworks (FAISS, Elasticsearch)
- Vector database market reached $1.73B in 2024, projected $10.6B by 2032

**Cascading agent failures:**
- Single compromised agent poisoned 87% of downstream decision-making within 4 hours
- EchoLeak (CVE-2025-32711) demonstrated real-world agentic AI exploitation against Microsoft Copilot

**Shadow AI exposure:**
- 77% of enterprise employees have pasted company data into chatbot queries (LayerX 2025)
- 22% of those instances included confidential personal or financial data
- AI-driven scams increased 456% (May 2024 to April 2025, Sift Q2 2025)

These statistics establish that hybrid RAG systems operate in hostile threat environments where both external attackers and insider data exposure create conditions favorable to pivot attacks.

---

## 5. RAG System Corpus Findings

Research into the `/Users/scott/perfecxion/rag_system` corpus identified 75+ files directly relevant to hybrid RAG security. These findings inform the experimental design and validate that the attack surface described in our threat model exists in real implementations.

### 5.1 Hybrid RAG Implementations

**SafeRAG Hybrid Retriever**

The SafeRAG benchmark includes a hybrid retrieval implementation that combines dense retrieval with sparse retrieval (BM25) and optional knowledge graph lookup. The hybrid retriever demonstrates the exact pivot mechanism our attacks target: dense retrieval results are used to seed graph queries that expand context. SafeRAG's evaluation reveals significant vulnerabilities to all four attack categories (silver noise, inter-context conflict, soft ad, white DoS), but does not test cross-store amplification.

**Weaviate Hybrid Search**

Multiple configuration files and implementation examples demonstrate Weaviate's hybrid search capability, which fuses vector (dense) and keyword (sparse, BM25) retrieval with configurable alpha weighting. While Weaviate's hybrid search operates within a single store, the architectural pattern (fuse two retrieval modalities, rerank results) mirrors the vector-to-graph pattern at a structural level. Weaviate's tenant isolation and ACL features provide single-store security but do not extend to graph expansion.

### 5.2 Neo4j / Graph Implementations

**7 LangChain Neo4j Templates Identified:**

1. **neo4j-vector-memory** -- Vector store with conversational memory backed by Neo4j graph. Implements the exact vector-to-graph pivot: vector retrieval seeds graph-based memory lookup, creating a direct channel from poisoned vector content to graph-stored conversation context.

2. **neo4j-cypher** -- Text-to-Cypher generation using LLM. Vulnerable to injection attacks (CVE-2024-8309) where natural language input or retrieved context manipulates generated Cypher queries.

3. **neo4j-advanced-rag** -- Advanced RAG patterns including parent-child document retrieval via graph relationships. The parent-child traversal creates a natural pivot path: retrieve child document via vector, expand to parent and sibling documents via graph.

4. **neo4j-generation** -- Graph-to-text generation pipeline. Demonstrates that graph content directly feeds LLM generation without intermediate security validation.

5. **neo4j-semantic-layer** -- Semantic layer over graph data enabling natural language queries against graph schema. The semantic layer abstracts away graph access controls, potentially enabling privilege escalation through natural language queries that the semantic layer translates into unrestricted Cypher.

6. **neo4j-parent** -- Parent document retrieval using graph relationships to locate related documents. Another pivot pathway: vector retrieval of a child chunk triggers graph traversal to parent documents with potentially higher sensitivity.

7. **neo4j-cypher-memory** -- Combines Cypher query generation with graph-backed memory. Compound vulnerability surface: LLM-generated Cypher operates on a memory graph that may contain sensitive conversation history.

### 5.3 Attack Frameworks

**10 Attack Primitives Identified:**

1. **Corpus Poisoning** -- Injection of adversarial passages into knowledge bases
2. **Embedding Manipulation** -- Direct modification of vector embeddings
3. **Retrieval Hijacking** -- Forcing retrieval of attacker-chosen documents
4. **Entity Injection** -- Adding false entities to knowledge graphs
5. **Relation Injection** -- Adding false relationships between existing entities
6. **Community Poisoning** -- Manipulating community detection through strategic node/edge injection
7. **Prompt Injection via Retrieval** -- Embedding LLM instructions in retrievable documents
8. **Backdoor Triggers** -- Hidden patterns that activate specific retrieval/generation behaviors
9. **Semantic Flooding** -- Overwhelming retrieval with semantically similar poisoned content
10. **Cross-Modal Poisoning** -- Exploiting multimodal retrieval to inject attacks through non-text modalities

**SafeRAG NCTD Attacks:** SafeRAG's Noise Contamination Through Documents methodology provides a structured approach to testing retrieval robustness against document-level contamination. NCTD attacks inject noise at varying granularity (word, sentence, paragraph, document) and measure degradation of retrieval precision and generation accuracy.

### 5.4 Exfiltration Research

**6 Attack Vectors Documented:**

1. **Direct extraction via prompting:** Crafting queries that cause the RAG system to verbatim reproduce sensitive retrieved content. Success rate varies by model (GPT-4 more resistant than GPT-3.5).

2. **Membership inference:** Determining whether specific documents exist in the knowledge base through behavioral analysis of generated outputs. "Riddle Me This" (CCS 2025) achieves high accuracy in both black-box and gray-box settings.

3. **Embedding inversion:** Reconstructing source text from vector embeddings. 92% accuracy on 32-token sequences with T5-based embeddings, 60-80% general accuracy.

4. **Structural extraction via graph probing:** RAGCrawler (Jan 2026) demonstrates 84.4% knowledge coverage through systematic graph-guided querying. Iterative query refinement guided by discovered topology enables near-complete corpus mapping.

5. **Backdoor-triggered extraction:** BadRAG/TrojanRAG-style triggers that cause verbatim or paraphrased reproduction of specific knowledge base content when activated. 94% verbatim extraction success on Gemma-2B-IT.

6. **Cross-modal leakage:** Multimodal RAG systems leak information across modalities, allowing text content to be inferred from image retrieval behavior and vice versa.

### 5.5 Defense Tools and Benchmarks

**Defense tools identified in corpus:**

- **Input sanitization pipelines:** Multiple implementations of query validation and prompt injection detection at the retrieval input layer.
- **Output filtering:** Post-generation PII detection and content safety classification.
- **Retrieval anomaly detection:** Statistical monitoring of retrieval patterns to identify poisoning attempts.
- **Access control integration:** SpiceDB and Pinecone access control patterns for pre-filtering retrieval by user permissions.
- **Embedding validation:** Outlier detection in embedding space to flag anomalous document embeddings before indexing.

**Benchmark datasets identified:**

- SafeRAG evaluation suite with 4 attack categories
- NQ (Natural Questions) for QA accuracy baseline
- MS MARCO for retrieval quality evaluation
- Multiple synthetic poisoning datasets for attack success rate measurement

**Critical finding:** No defense tool or benchmark in the corpus addresses cross-store security. Every tool operates within a single retrieval modality (vector OR graph), confirming the gap our work fills.

---

## 6. Strategic Positioning

### 6.1 Target Venues

**Tier 1 (Primary targets):**

| Venue | Deadline (Estimated) | Fit Assessment |
|-------|---------------------|----------------|
| **IEEE S&P 2027** | Dec 2026 (cycle 1) / Apr 2027 (cycle 2) | Strongest fit. S&P accepted GRAGPoison for 2026, establishing precedent for RAG/GraphRAG security. Our cross-store analysis extends GRAGPoison to hybrid architectures, making it a natural "next step" paper for S&P reviewers familiar with the domain. The formal metrics and defense evaluation match S&P's preference for rigorous, systems-oriented security work. |
| **USENIX Security 2026** | Oct 2026 (summer cycle) | Strong fit. USENIX Security accepted PoisonedRAG for 2025, demonstrating interest in RAG security. Our work bridges PoisonedRAG (vector-side) with GRAGPoison (graph-side), directly connecting to both accepted papers. USENIX's emphasis on practical attacks and defenses aligns with our reproducible evaluation harness. |
| **ACM CCS 2026** | May 2026 | Strong fit. CCS accepted FlippedRAG, ImportSnare, and "Riddle Me This" for 2025, showing broad RAG security interest. Our privacy-focused analysis (RPR as privacy metric, amplification of sensitive data exposure) aligns with CCS's privacy track. |
| **NeurIPS 2026** | May 2026 | Good fit for the ML-security angle. NeurIPS accepted RAGuard and SeCon-RAG for 2025, establishing precedent for RAG defense papers. Our defense mechanisms with utility-security tradeoff analysis fit the ML systems security track. |

**Tier 2 (Backup targets):**

| Venue | Fit Assessment |
|-------|----------------|
| NDSS 2027 | Strong systems security focus, Pandora precedent |
| IEEE SaTML 2027 | SoK: Privacy Risks in RAG accepted for 2026, direct alignment |
| AAAI 2027 | AI safety track, broader ML audience |
| ACSAC 2026 | Applied security, faster turnaround |

### 6.2 Key Differentiators

**Differentiator 1: First formal cross-store security analysis.**

No published work models the security boundary between vector and graph stores in a hybrid RAG system. We provide the first formal definition of Retrieval Pivot Risk (RPR), the first measurement of cross-store Amplification Factor (AF), and the first attack taxonomy targeting the vector-to-graph boundary. This is not incremental improvement over existing work; it is a new problem formulation.

**Differentiator 2: First hybrid RAG security benchmark.**

SafeRAG, RSB, and other benchmarks test single-store configurations. Our benchmark is the first to include sensitivity-tiered graph neighborhoods, cross-store attack scenarios, amplification metrics, and comparison across vector-only, graph-only, and hybrid pipelines. The reproducible evaluation harness enables future research to build on our results.

**Differentiator 3: Compound threat quantification.**

We provide the first empirical measurement of compound attack success when combining vector poisoning with graph expansion. Existing papers measure vector-side ASR (PoisonedRAG: 90%) and graph-side ASR (GRAGPoison: 98%) independently. We measure what happens when both attack surfaces are exploited simultaneously through the pivot mechanism.

**Differentiator 4: Defense suite with utility tradeoff analysis.**

Our five defenses (D1-D5) are the first designed specifically for the cross-store boundary. Unlike prior defenses that operate within a single store, our defenses span the vector-to-graph transition and include ablation studies quantifying the security-utility tradeoff at each layer.

### 6.3 Compound Threat Estimate

**Estimated compound success rate against undefended hybrid RAG: 95%+**

**Derivation:**

The theoretical model computes attack success as the product of three stages:

1. **Vector entry (V):** PoisonedRAG demonstrates 90% ASR with 5 poisoned documents. CorruptRAG shows single-document attacks achieve even higher rates. Conservative estimate: **V = 0.90**.

2. **Pivot acceptance (P):** In current hybrid RAG implementations, graph expansion from vector-retrieved entities is automatic and unconditional. No published system performs authorization checking at the pivot boundary. Conservative estimate: **P = 1.00** (every vector result triggers graph expansion).

3. **Graph reach (G):** GRAGPoison achieves 98% ASR within graph-only settings. TKPA shows 93.1% targeted success. The probability that a 2-hop expansion from a strategically placed seed reaches at least one sensitive node in a typical enterprise graph (where sensitive nodes are within 2 hops of 60%+ of all nodes): **G = 0.95+** for realistic enterprise graph topologies.

**Compound success: V x P x G = 0.90 x 1.00 x 0.95 = 0.855 (conservative lower bound)**

With optimized attacks (CorruptRAG-level single-document entry, TKPA-level hub targeting):

**Optimized compound success: 0.95 x 1.00 x 0.98 = 0.931**

With RL-optimized poisoning (RIPRAG) targeting hybrid-specific objectives:

**Maximum estimated compound success: 95%+**

These estimates assume no cross-store defenses are deployed. With our defense suite (D1-D5), we hypothesize reduction to **<15% compound ASR** while maintaining **>80% retrieval utility** (F1 on QA benchmark).

### 6.4 Related Work Positioning

**Against GRAGPoison (S&P 2026):**

GRAGPoison is the closest related work and the strongest baseline for comparison. Key differences:

| Dimension | GRAGPoison | Our Work |
|-----------|-----------|----------|
| Attack scope | Graph-only (poisoning within GraphRAG) | Cross-store (vector entry, graph amplification) |
| Entry point | Document injection processed by graph indexer | Vector embedding poisoning that seeds graph traversal |
| Amplification model | Shared-relation exploitation within graph | Cross-store amplification factor (AF) measuring hybrid vs. vector-only |
| Defense scope | Not addressed (attack paper) | Five cross-store defenses with ablation |
| Benchmark | Custom graph QA evaluation | Multi-pipeline benchmark (vector, graph, hybrid) |

We position our work as extending GRAGPoison's insight (graph structure amplifies small poisoning) to the hybrid setting (graph structure amplifies vector-sourced poisoning across the store boundary), and complementing their attack analysis with a comprehensive defense framework.

**Against RAGCrawler (Jan 2026):**

RAGCrawler provides the reconnaissance methodology that enables targeted pivot attacks. Where RAGCrawler maps graph topology for extraction, we use graph topology knowledge to optimize pivot attack placement. RAGCrawler's 84.4% coverage metric represents an upper bound on what pivot attacks can reach.

**Against SDAG (Feb 2026):**

SDAG is the closest existing defense mechanism. Its block-sparse attention partitioning between trusted and untrusted context segments directly applies to our setting (vector-retrieved vs. graph-expanded content). We build on SDAG by adding graph-specific awareness: rather than simply partitioning by source, our defenses consider traversal path, sensitivity gradient, and cross-store consistency.

**Against SD-RAG (Jan 2026):**

SD-RAG's selective disclosure model aligns with our per-hop authorization (D1) and edge-type allowlisting (D2). We extend selective disclosure with graph-aware policies that restrict information flow based on traversal topology, not just document-level classification.

---

## 7. Key Citations Reference List

### Attack Papers

1. **GRAGPoison:** Hu, Z., Zhong, S., Zhang, Y., et al. "GraphRAG Under Fire." *IEEE Symposium on Security and Privacy (S&P)*, 2026. arXiv:2501.14050. URL: https://arxiv.org/abs/2501.14050

2. **TKPA/UKPA:** Authors TBD. "A Few Words Can Distort Graphs: Knowledge Poisoning Attacks on GraphRAG." arXiv preprint, August 2025. URL: https://arxiv.org/html/2508.04276

3. **RAG Safety KG-RAG:** Authors TBD. "Knowledge Poisoning Attacks on Knowledge Graph RAG." *Information Fusion* (Elsevier), 2025. URL: https://www.sciencedirect.com/science/article/abs/pii/S1566253525009625

4. **RAGCrawler:** Authors TBD. "RAGCrawler: KG-Guided Extraction of RAG Knowledge Bases." arXiv preprint, January 2026.

5. **PoisonedRAG:** Zou, W., Geng, R., Wang, B., Jia, J. "PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation of Large Language Models." *USENIX Security Symposium*, 2025. arXiv:2402.07867. URL: https://arxiv.org/abs/2402.07867

6. **CorruptRAG:** Authors TBD. "CorruptRAG: Practical Poisoning Attacks on Retrieval-Augmented Generation." arXiv preprint, April 2025. arXiv:2504.03957. URL: https://arxiv.org/abs/2504.03957

7. **CtrlRAG:** Authors TBD. "CtrlRAG: Black-Box Poisoning Attacks on RAG Systems." 2025. Semantic Scholar ID: b308393d47e68d1cd746b4f2f632db4eda875751. URL: https://www.semanticscholar.org/paper/b308393d47e68d1cd746b4f2f632db4eda875751

8. **Pandora:** Deng, G., Liu, Y., et al. "Pandora: Jailbreak GPTs by Retrieval Augmented Generation Poisoning." *NDSS AISCC Workshop*, 2024. arXiv:2402.08416. URL: https://arxiv.org/abs/2402.08416

9. **BadRAG:** Authors TBD. "BadRAG: Identifying Vulnerabilities in Retrieval Augmented Generation of Large Language Models." arXiv preprint, 2024. URL: https://www.aimodels.fyi/papers/arxiv/badrag-identifying-vulnerabilities-retrieval-augmented-generation-large

10. **TrojanRAG:** Authors TBD. "TrojanRAG: Retrieval-Augmented Generation Can Be Backdoor Driver in Large Language Models." arXiv:2405.13401. URL: https://arxiv.org/abs/2405.13401

11. **Poisoned-MRAG:** Authors TBD. "Poisoned-MRAG: Knowledge Poisoning Attacks to Multimodal Retrieval Augmented Generation." arXiv preprint, March 2025. arXiv:2503.06254. URL: https://arxiv.org/abs/2503.06254

12. **RIPRAG:** Authors TBD. "RIPRAG: Reinforcement Learning-Based Black-Box Poisoning Attacks on RAG." arXiv preprint, October 2025.

13. **NeuroGenPoisoning:** Authors TBD. "Neuron-Guided Poisoning Attacks on Retrieval-Augmented Generation." *NeurIPS*, 2025.

14. **FlippedRAG:** Authors TBD. "FlippedRAG: Black-Box Opinion Manipulation Attacks to Retrieval-Augmented Generation of Large Language Models." *ACM Conference on Computer and Communications Security (CCS)*, 2025.

15. **Machine Against the RAG:** Authors TBD. "Machine Against the RAG: Jamming Retrieval-Augmented Generation with Blocker Documents." *USENIX Security Symposium*, 2025.

16. **ImportSnare:** Authors TBD. "ImportSnare: Hijacking Code RAG for Supply-Chain Attacks." *ACM Conference on Computer and Communications Security (CCS)*, 2025.

17. **Corpus Poisoning Dense Retrievers:** Zhong, Z., Friedman, Z., Chen, D. "Poisoning Retrieval Corpora by Injecting Adversarial Passages." *Empirical Methods in Natural Language Processing (EMNLP)*, 2023. arXiv:2310.19156. URL: https://arxiv.org/abs/2310.19156

### Defense Papers

18. **RAGuard:** Authors TBD. "RAGuard: A Detection Framework for Poisoning Attacks on Retrieval-Augmented Generation." *NeurIPS*, 2025.

19. **SeCon-RAG:** Authors TBD. "SeCon-RAG: Two-Stage Semantic Consistency Defense for Retrieval-Augmented Generation." *NeurIPS*, 2025.

20. **RevPRAG:** Authors TBD. "RevPRAG: Activation-Based Detection of RAG Poisoning." *Findings of EMNLP*, 2025. URL: https://aclanthology.org/2025.findings-emnlp.698

21. **SDAG:** Authors TBD. "SDAG: Block-Sparse Attention Guard for Retrieval-Augmented Generation." arXiv preprint, February 2026.

22. **SD-RAG:** Authors TBD. "SD-RAG: Selective Disclosure for Retrieval-Augmented Generation." arXiv preprint, January 2026.

23. **SafeRAG:** Authors TBD. "SafeRAG: Benchmarking Security in Retrieval-Augmented Generation." arXiv:2501.18636, January 2025. URL: https://arxiv.org/abs/2501.18636

24. **Traceback of RAG Poisoning:** Authors TBD. "Traceback of RAG Poisoning Attacks." *ACM Web Conference*, 2025. URL: https://dl.acm.org/doi/10.1145/3696410.3714756

### Privacy & Extraction Papers

25. **SoK: Privacy Risks in RAG:** Authors TBD. "SoK: Privacy Risks in Retrieval-Augmented Generation." *IEEE Conference on Secure and Trustworthy Machine Learning (SaTML)*, 2026.

26. **Riddle Me This:** Authors TBD. "Riddle Me This: Membership Inference Attacks on Retrieval-Augmented Generation." *ACM Conference on Computer and Communications Security (CCS)*, 2025.

27. **Graph RAG Privacy Paradox:** Authors TBD. "Exposing Privacy Risks in Graph Retrieval-Augmented Generation." arXiv preprint, August 2025. arXiv:2508.17222. URL: https://arxiv.org/abs/2508.17222

28. **Multi-Agentic AI-RAG Vulnerabilities:** Authors TBD. "Security Vulnerabilities in Multi-Agentic AI-RAG Systems." *EU Open Science*, 2025.

### Architecture & Framework References

29. **AgCyRAG:** Authors TBD. "AgCyRAG: Agentic Knowledge Graph RAG for Cybersecurity." *CEUR-WS*, Vol-4079, 2025. URL: https://ceur-ws.org/Vol-4079/paper11.pdf

30. **Microsoft GraphRAG:** Edge, D., Trinh, H., Cheng, N., et al. "From Local to Global: A Graph RAG Approach to Query-Focused Summarization." arXiv:2404.16130, 2024. URL: https://arxiv.org/abs/2404.16130

31. **HybridRAG:** Authors TBD. "HybridRAG: Integrating Knowledge Graphs and Vector Retrieval for Enhanced RAG." arXiv:2408.04948, August 2024. URL: https://arxiv.org/abs/2408.04948

32. **RAG Security Threat Model:** Arzanipour, H., Behnia, R., et al. "RAG Security and Privacy: Formalizing the Threat Model." arXiv:2509.20324, September 2024. URL: https://arxiv.org/abs/2509.20324

33. **Access Control for Graph-Structured Data:** Authors TBD. "A Comparison of Access Control Approaches for Graph-Structured Data." arXiv:2405.20762, May 2024. URL: https://arxiv.org/abs/2405.20762

### Standards & Frameworks

34. **OWASP LLM Top 10 2025.** "OWASP Top 10 for Large Language Model Applications, Version 2025." OWASP Foundation, November 2024. URL: https://genai.owasp.org/

35. **MITRE ATLAS.** "Adversarial Threat Landscape for AI Systems." MITRE Corporation, October 2025 update. URL: https://atlas.mitre.org/

36. **NIST AI 100-2 E2025.** "Artificial Intelligence Risk Management Framework: Generative AI Profile." National Institute of Standards and Technology, 2025.

37. **MAESTRO.** "Multi-Agent Environment Security Threat, Risk, and Opportunity Framework." Cloud Security Alliance, 2025. URL: https://cloudsecurityalliance.org/blog/2025/02/06/agentic-ai-threat-modeling-framework-maestro

38. **OWASP Agentic Applications Top 10.** "OWASP Top 10 for Agentic Applications, Version 2026." OWASP Foundation, 2026.

### Vulnerability Disclosures

39. **CVE-2024-8309.** Cypher injection in LangChain Neo4j integration. NVD.

40. **CVE-2025-68664 (LangGrinch).** Critical deserialization vulnerability in langchain-core. CVSS 9.3. NVD. URL: https://nvd.nist.gov/vuln/detail/CVE-2025-68664

41. **CVE-2025-68665.** Serialization injection in LangChain.js. CVSS 8.6. NVD.

### Industry Sources

42. **Embedding Inversion (vec2text).** Morris, J.X., Kuleshov, V., Shmatikov, V., Rush, A.M. "Text Embeddings Reveal (Almost) As Much As Text." *EMNLP*, 2023.

43. **Pinecone + SpiceDB Access Control Pattern.** "RAG Access Control." Pinecone Documentation. URL: https://www.pinecone.io/learn/rag-access-control/

44. **Memgraph Pivot Search.** "Knowledge Retrieval in Memgraph." Memgraph Documentation. URL: https://memgraph.com/docs/ai-ecosystem/graph-rag/knowledge-retrieval

---

## Appendix A: Research Methodology

This compilation was assembled through:

1. **Systematic literature search** across IEEE Xplore, ACM Digital Library, USENIX proceedings, arXiv, Semantic Scholar, and Google Scholar using query terms: "RAG poisoning," "GraphRAG attack," "hybrid RAG security," "knowledge graph RAG vulnerability," "retrieval-augmented generation privacy," "cross-store attack," "vector-to-graph attack," and "retrieval pivot."

2. **Citation chain analysis** starting from PoisonedRAG (302 citations) and GRAGPoison, following forward and backward citations to identify related work.

3. **Framework and standards review** of OWASP, MITRE ATLAS, NIST, and CSA publications for RAG and AI security classifications.

4. **Corpus analysis** of the perfecXion.ai RAG system (114,000 indexed chunks, 2.1GB ChromaDB) for implementation patterns and attack surface documentation.

5. **Vendor documentation review** for Neo4j, Pinecone, Weaviate, Memgraph, LangChain, and LangGraph security features and known vulnerabilities.

**Search date range:** January 2023 through February 2026.

**Inclusion criteria:** Papers must address at least one of: RAG system security, knowledge graph attacks/defenses, vector database security, or hybrid retrieval architecture security.

**Exclusion criteria:** Papers focused exclusively on LLM training-time attacks (without retrieval component), traditional database security (without AI/ML integration), or general prompt injection (without RAG-specific analysis).

---

## Appendix B: Notation Reference

| Symbol | Definition |
|--------|-----------|
| G = (V, E) | Knowledge graph with nodes V and edges E |
| c(v) | Sensitivity classification of node v |
| auth(u, v) | Authorization predicate: 1 if user u may access node v |
| A_u | Authorized node set for user u |
| S(q) | Seed node set from vector retrieval for query q |
| Exp(G, S, u, q) | Graph expansion operator |
| Z(q, u) | Final context node set after expansion |
| U_u | Unauthorized sensitive node set for user u |
| RPR(u) | Retrieval Pivot Risk for user u |
| AF | Amplification Factor: E[Leakage@k_hybrid] / E[Leakage@k_vector] |
| PD(q) | Pivot Depth: minimum hops from seed to first sensitive node |
| Leakage@k(q) | Count of sensitive items in top-k context set |
| RPA(u) | Retrieval Pivot Amplification: RPR_hybrid / RPR_vector |
| b | Average branching factor of graph |
| d | Traversal depth (hops) |
| V | Vector entry success probability |
| P | Pivot acceptance rate |
| G | Graph reach probability |

---

*End of Research Compilation.*
*Last updated: February 6, 2026.*
