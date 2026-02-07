#!/usr/bin/env python3
"""Run attack experiments: inject A1-A4 payloads and measure leakage amplification.

For each attack:
  1. Start from clean databases (rebuild from scratch)
  2. Inject attack payloads into vector store AND graph (connecting to existing entities)
  3. Run adversarial queries through P3 (hybrid, no defenses)
  4. Compare against the clean P3 baseline

Usage:
    python scripts/run_attack_experiments.py --attacks A1 A2 A3 A4

    # Quick test with just A1
    python scripts/run_attack_experiments.py --attacks A1
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import click

from pivorag.attacks.base import InjectionPayload
from pivorag.config import SensitivityTier
from pivorag.eval.metrics import amplification_factor, leakage_at_k, pivot_depth
from pivorag.pipelines.base import RetrievalContext


def load_adversarial_queries() -> list[dict]:
    return json.loads(Path("data/queries/adversarial.json").read_text())


def find_existing_entities(driver, entity_names: list[str]) -> dict[str, str]:
    """Find existing entity node IDs in the graph that match attack entity names.

    Returns a mapping from raw entity name → existing entity node_id.
    Uses multiple matching strategies: exact canonical, prefix, substring.
    """
    matches = {}
    with driver.session() as session:
        for name in entity_names:
            canonical = name.strip().lower().replace(" ", "_")
            canonical_hyphen = name.strip().lower().replace(" ", "-")

            # Strategy 1: Exact canonical match
            result = session.run(
                """
                MATCH (e:Entity)
                WHERE e.canonical_name = $canon1 OR e.canonical_name = $canon2
                RETURN e.node_id AS eid
                LIMIT 1
                """,
                canon1=canonical, canon2=canonical_hyphen,
            )
            record = result.single()
            if record:
                matches[name] = record["eid"]
                continue

            # Strategy 2: node_id prefix match (e.g. ent_vault_ → ent_vault_ORG)
            result = session.run(
                """
                MATCH (e:Entity)
                WHERE e.node_id STARTS WITH $prefix1 OR e.node_id STARTS WITH $prefix2
                RETURN e.node_id AS eid
                LIMIT 1
                """,
                prefix1=f"ent_{canonical}_", prefix2=f"ent_{canonical_hyphen}_",
            )
            record = result.single()
            if record:
                matches[name] = record["eid"]
                continue

            # Strategy 3: Substring match on canonical_name (fuzzy)
            result = session.run(
                """
                MATCH (e:Entity)
                WHERE e.canonical_name CONTAINS $search
                RETURN e.node_id AS eid
                LIMIT 1
                """,
                search=canonical,
            )
            record = result.single()
            if record:
                matches[name] = record["eid"]
    return matches


def inject_with_graph_links(
    payloads: list[InjectionPayload],
    vector_index,
    graph_builder,
    driver,
    attacker_tenant: str,
) -> dict[str, Any]:
    """Inject attack payloads with proper graph connectivity.

    Unlike the raw attack inject(), this function:
    1. Inserts chunks into ChromaDB
    2. Creates chunk nodes in the graph
    3. Finds EXISTING entity nodes matching payload entities
    4. Creates MENTIONS edges from injected chunks to existing entities

    This simulates what happens when injected content goes through
    the real ingestion pipeline (NER finds the entities, creates edges
    to existing graph nodes).
    """
    from pivorag.graph.schema import GraphEdge, GraphNode
    from pivorag.vector.embed import EmbeddingModel

    model = EmbeddingModel()

    # Collect all unique entity names from payloads
    all_entity_names = list({e for p in payloads for e in p.entities})
    existing_map = find_existing_entities(driver, all_entity_names)
    click.echo(
        f"  Entity resolution: {len(existing_map)}/{len(all_entity_names)} "
        f"matched to existing graph nodes"
    )

    # Insert chunks into ChromaDB
    ids = []
    embeddings = []
    documents = []
    metadatas = []

    for payload in payloads:
        chunk_id = f"injected_{payload.payload_id}"
        embedding = model.embed(payload.text).tolist()

        ids.append(chunk_id)
        embeddings.append(embedding)
        documents.append(payload.text)
        metadatas.append({
            "doc_id": f"injected_doc_{payload.payload_id}",
            "tenant": attacker_tenant,
            "sensitivity": "PUBLIC",
            "domain": "engineering",
            "doc_type": "injected_attack",
            "trust_score": payload.metadata.get("provenance_score", 0.3),
            "provenance_score": payload.metadata.get("provenance_score", 0.3),
        })

    vector_index.add_chunks(ids, embeddings, documents, metadatas)

    # Create graph nodes and edges
    mentions_created = 0
    for payload in payloads:
        chunk_id = f"injected_{payload.payload_id}"

        # Create chunk node
        graph_builder.add_node(GraphNode(
            node_id=chunk_id,
            node_type="Chunk",
            tenant=attacker_tenant,
            sensitivity="PUBLIC",
            provenance_score=0.3,
        ))

        # Link to existing entities via MENTIONS
        for entity_name in payload.entities:
            if entity_name in existing_map:
                graph_builder.add_edge(GraphEdge(
                    source_id=chunk_id,
                    target_id=existing_map[entity_name],
                    edge_type="MENTIONS",
                    trust_score=0.3,
                ))
                mentions_created += 1

    click.echo(f"  Injected {len(payloads)} chunks, {mentions_created} MENTIONS edges")
    return {
        "chunks_injected": len(payloads),
        "entities_resolved": len(existing_map),
        "mentions_created": mentions_created,
        "resolved_entities": existing_map,
    }


def rebuild_clean_databases(
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
) -> None:
    """Clear databases and rebuild from synthetic data."""
    import subprocess
    import sys

    # Clear Neo4j
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    driver.close()

    # Clear ChromaDB
    import chromadb
    client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
    for coll in client.list_collections():
        client.delete_collection(coll.name)

    # Rebuild
    click.echo("  Rebuilding indexes from synthetic data...")
    result = subprocess.run(
        [
            sys.executable, "scripts/build_indexes.py",
            "--data", "data/raw/synthetic_enterprise.json",
            "--chroma-host", chroma_host,
            "--chroma-port", str(chroma_port),
            "--neo4j-uri", neo4j_uri,
            "--neo4j-user", neo4j_user,
            "--neo4j-pass", neo4j_pass,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo(f"  ERROR: rebuild failed:\n{result.stderr}")
        raise RuntimeError("Rebuild failed")
    # Show summary line
    for line in result.stdout.splitlines():
        if "Pipeline Summary" in line or "Neo4j:" in line or "ChromaDB:" in line:
            click.echo(f"  {line.strip()}")


def create_pipeline(
    variant: str,
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
):
    """Create a pipeline instance connected to live services."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_experiments import build_pipeline_config

    from pivorag.vector.embed import EmbeddingModel
    from pivorag.vector.index import VectorIndex
    from pivorag.vector.retrieve import VectorRetriever

    config = build_pipeline_config(variant)
    model = EmbeddingModel("all-MiniLM-L6-v2")
    index = VectorIndex(
        host=chroma_host, port=chroma_port,
        collection_name="pivorag_chunks",
    )
    retriever = VectorRetriever(index=index, embedding_model=model)

    if variant == "P1":
        from pivorag.pipelines.vector_only import VectorOnlyPipeline
        return VectorOnlyPipeline(config=config, retriever=retriever)

    from neo4j import GraphDatabase

    from pivorag.graph.expand import GraphExpander
    from pivorag.pipelines.hybrid import HybridPipeline

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
    expander = GraphExpander(driver=driver)
    return HybridPipeline(
        config=config,
        vector_retriever=retriever,
        graph_expander=expander,
    )


def run_pipeline_queries(
    variant: str,
    queries: list[dict],
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
) -> list[RetrievalContext]:
    """Run queries through a pipeline variant and return contexts."""
    pipeline = create_pipeline(
        variant, chroma_host, chroma_port,
        neo4j_uri, neo4j_user, neo4j_pass,
    )

    contexts = []
    for q in queries:
        ctx = pipeline.retrieve(
            query=q["text"],
            user_id=f"user_{q['query_id'].lower()}",
            user_tenant=q["tenant"],
            user_clearance=SensitivityTier(q["user_clearance"]),
        )
        contexts.append(ctx)
    return contexts


def compute_metrics(contexts: list[RetrievalContext]) -> dict[str, Any]:
    """Compute security metrics from a list of retrieval contexts."""
    total = len(contexts)
    leakages = [leakage_at_k(ctx) for ctx in contexts]
    depths = [pivot_depth(ctx) for ctx in contexts]
    queries_with_leak = sum(1 for leak in leakages if leak > 0)

    return {
        "rpr": queries_with_leak / max(total, 1),
        "mean_leakage": sum(leakages) / max(total, 1),
        "queries_with_leakage": queries_with_leak,
        "total_queries": total,
        "mean_pivot_depth": sum(
            d for d in depths if d != float("inf")
        ) / max(sum(1 for d in depths if d != float("inf")), 1),
        "leakage_per_query": leakages,
    }


def generate_attack_payloads(
    attack_name: str,
    target_queries: list[str],
) -> tuple[list[InjectionPayload], str]:
    """Generate payloads for a named attack, return (payloads, attacker_tenant)."""
    if attack_name == "A1":
        from pivorag.attacks.seed_steering import SeedSteeringAttack
        attack = SeedSteeringAttack(injection_budget=9, target_path="engineering_to_security")
        return attack.generate_payloads(target_queries), attack.attacker_tenant
    elif attack_name == "A2":
        from pivorag.attacks.entity_anchor import EntityAnchorAttack
        attack = EntityAnchorAttack(injection_budget=10, target_area="security_credentials")
        return attack.generate_payloads(target_queries), attack.attacker_tenant
    elif attack_name == "A3":
        from pivorag.attacks.neighborhood_flood import NeighborhoodFloodAttack
        attack = NeighborhoodFloodAttack(
            injection_budget=20, target_neighborhood="security_neighborhood",
        )
        return attack.generate_payloads(target_queries), attack.attacker_tenant
    elif attack_name == "A4":
        from pivorag.attacks.bridge_node import BridgeNodeAttack
        attack = BridgeNodeAttack(
            injection_budget=15, bridge_path="engineering_to_security",
        )
        return attack.generate_payloads(target_queries), attack.attacker_tenant
    else:
        raise ValueError(f"Unknown attack: {attack_name}")


@click.command()
@click.option(
    "--attacks", "-a", multiple=True, default=["A1", "A2", "A3", "A4"],
    help="Attacks to run",
)
@click.option("--chroma-host", default="localhost")
@click.option("--chroma-port", default=8000, type=int)
@click.option("--neo4j-uri", default="bolt://localhost:7687")
@click.option("--neo4j-user", default="neo4j")
@click.option("--neo4j-pass", default="pivorag_dev_2025")
@click.option("--output", "-o", default="results")
@click.option("--skip-rebuild", is_flag=True, help="Skip initial rebuild (use existing data)")
def main(
    attacks: tuple[str, ...],
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    output: str,
    skip_rebuild: bool,
) -> None:
    """Run attack injection experiments and measure leakage amplification."""
    start = time.perf_counter()
    queries = load_adversarial_queries()
    target_query_texts = [q["text"] for q in queries]

    click.echo("PivoRAG Attack Experiments")
    click.echo(f"Attacks: {', '.join(attacks)}")
    click.echo(f"Queries: {len(queries)} adversarial")

    all_results: dict[str, Any] = {}

    # Step 1: Get clean baseline (P1 and P3 without attacks)
    click.echo(f"\n{'='*60}")
    click.echo("Phase 1: Clean baseline measurement")
    click.echo(f"{'='*60}")

    if not skip_rebuild:
        rebuild_clean_databases(
            chroma_host, chroma_port, neo4j_uri, neo4j_user, neo4j_pass,
        )

    p1_contexts = run_pipeline_queries(
        "P1", queries, chroma_host, chroma_port,
        neo4j_uri, neo4j_user, neo4j_pass,
    )
    p3_clean_contexts = run_pipeline_queries(
        "P3", queries, chroma_host, chroma_port,
        neo4j_uri, neo4j_user, neo4j_pass,
    )

    p1_metrics = compute_metrics(p1_contexts)
    p3_clean_metrics = compute_metrics(p3_clean_contexts)

    all_results["P1_baseline"] = p1_metrics
    all_results["P3_clean"] = p3_clean_metrics

    click.echo(f"  P1 baseline: RPR={p1_metrics['rpr']:.3f}, Leak={p1_metrics['mean_leakage']:.2f}")
    click.echo(
        f"  P3 clean:    RPR={p3_clean_metrics['rpr']:.3f}, "
        f"Leak={p3_clean_metrics['mean_leakage']:.2f}"
    )

    # Step 2: Run each attack
    from neo4j import GraphDatabase

    from pivorag.graph.build_graph import GraphBuilder
    from pivorag.vector.index import VectorIndex

    for attack_name in attacks:
        click.echo(f"\n{'='*60}")
        click.echo(f"Phase 2: Attack {attack_name}")
        click.echo(f"{'='*60}")

        # Rebuild clean state
        click.echo("  Rebuilding clean databases...")
        rebuild_clean_databases(
            chroma_host, chroma_port, neo4j_uri, neo4j_user, neo4j_pass,
        )

        # Generate payloads
        payloads, attacker_tenant = generate_attack_payloads(attack_name, target_query_texts)
        click.echo(f"  Generated {len(payloads)} payloads for {attack_name}")

        # Inject with proper graph links
        index = VectorIndex(
            host=chroma_host, port=chroma_port,
            collection_name="pivorag_chunks",
        )
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
        builder = GraphBuilder(uri=neo4j_uri, username=neo4j_user, password=neo4j_pass)

        try:
            inject_stats = inject_with_graph_links(
                payloads, index, builder, driver, attacker_tenant,
            )
        finally:
            builder.close()

        # Measure P3 with attack injected
        p3_attack_contexts = run_pipeline_queries(
            "P3", queries, chroma_host, chroma_port,
            neo4j_uri, neo4j_user, neo4j_pass,
        )
        p3_attack_metrics = compute_metrics(p3_attack_contexts)

        # Also measure P4 (D1 defense) under attack
        p4_attack_contexts = run_pipeline_queries(
            "P4", queries, chroma_host, chroma_port,
            neo4j_uri, neo4j_user, neo4j_pass,
        )
        p4_attack_metrics = compute_metrics(p4_attack_contexts)

        # Compute AF: P3_attack vs P3_clean
        af = amplification_factor(p3_attack_contexts, p3_clean_contexts)

        attack_result = {
            "attack": attack_name,
            "payloads": len(payloads),
            "injection_stats": inject_stats,
            "P3_under_attack": p3_attack_metrics,
            "P4_under_attack": p4_attack_metrics,
            "amplification_factor_vs_clean": af,
        }
        all_results[f"{attack_name}"] = attack_result

        click.echo(f"  P3 + {attack_name}:")
        click.echo(
            f"    RPR={p3_attack_metrics['rpr']:.3f}, "
            f"Leak={p3_attack_metrics['mean_leakage']:.2f}, AF={af:.2f}"
        )
        click.echo(f"  P4 + {attack_name} (D1 defense):")
        click.echo(
            f"    RPR={p4_attack_metrics['rpr']:.3f}, "
            f"Leak={p4_attack_metrics['mean_leakage']:.2f}"
        )

        driver.close()

    # Print comparison table
    click.echo(f"\n{'='*80}")
    click.echo("  ATTACK EXPERIMENT RESULTS")
    click.echo(f"{'='*80}")
    click.echo(f"{'Scenario':<25} {'RPR':>6} {'Leak':>6} {'AF':>6} {'Leak/Q':>7}")
    click.echo("-" * 60)

    click.echo(
        f"{'P1 baseline':<25} {p1_metrics['rpr']:>6.3f} "
        f"{p1_metrics['mean_leakage']:>6.2f} {'--':>6} "
        f"{p1_metrics['queries_with_leakage']}/{p1_metrics['total_queries']:>4}"
    )
    click.echo(
        f"{'P3 clean':<25} {p3_clean_metrics['rpr']:>6.3f} "
        f"{p3_clean_metrics['mean_leakage']:>6.2f} {'--':>6} "
        f"{p3_clean_metrics['queries_with_leakage']}/{p3_clean_metrics['total_queries']:>4}"
    )

    for attack_name in attacks:
        if attack_name not in all_results:
            continue
        ar = all_results[attack_name]
        p3m = ar["P3_under_attack"]
        af = ar["amplification_factor_vs_clean"]
        af_str = "inf" if af == float("inf") else f"{af:.2f}"
        click.echo(
            f"{'P3 + ' + attack_name:<25} {p3m['rpr']:>6.3f} "
            f"{p3m['mean_leakage']:>6.2f} {af_str:>6} "
            f"{p3m['queries_with_leakage']}/{p3m['total_queries']:>4}"
        )
        p4m = ar["P4_under_attack"]
        click.echo(
            f"{'P4 + ' + attack_name + ' (D1)':<25} {p4m['rpr']:>6.3f} "
            f"{p4m['mean_leakage']:>6.2f} {'--':>6} "
            f"{p4m['queries_with_leakage']}/{p4m['total_queries']:>4}"
        )

    click.echo("-" * 60)

    # Save results
    out = Path(output) / "tables"
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out / f"attack_experiments_{timestamp}.json"

    # Remove non-serializable fields
    serializable = {}
    for k, v in all_results.items():
        if isinstance(v, dict):
            clean = {}
            for k2, v2 in v.items():
                if k2 == "leakage_per_query":
                    clean[k2] = v2
                elif isinstance(v2, dict):
                    # Remove resolved_entities (contains node IDs, not useful in output)
                    clean[k2] = {
                        kk: vv for kk, vv in v2.items()
                        if kk != "resolved_entities"
                    }
                else:
                    clean[k2] = v2
            serializable[k] = clean
        else:
            serializable[k] = v

    path.write_text(json.dumps(serializable, indent=2, default=str))
    click.echo(f"\nResults saved to {path}")

    elapsed = time.perf_counter() - start
    click.echo(f"Total attack experiment time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
