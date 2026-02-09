#!/usr/bin/env python3
"""Fast loader: insert pre-processed data into ChromaDB + Neo4j.

Reads already-processed chunks/entities/relations from JSON files,
re-runs batch spaCy NER to rebuild the chunk→entity map,
generates embeddings, and inserts into databases.
Skips expensive CSV parsing and chunking.

Usage:
    python scripts/load_processed.py --input data/processed/enron
    python scripts/load_processed.py --input data/processed/enron --collection enron_chunks
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import click


def load_json(path: Path, label: str) -> list[dict]:
    """Load a JSON file and report size."""
    data = json.loads(path.read_text())
    click.echo(f"  Loaded {len(data)} {label} from {path.name}")
    return data


def rebuild_chunk_entity_map_ner(
    chunks: list[dict], entities: list[dict], batch_size: int = 1000
) -> dict[str, list[dict]]:
    """Rebuild chunk→entity map using batch spaCy NER.

    Uses nlp.pipe() with only the NER component enabled for speed.
    Maps NER results back to the canonical entity IDs from the saved entity list.
    """
    import spacy

    # Load with only NER — disable parser, tagger, lemmatizer for ~3x speedup
    # Keep tok2vec since NER depends on it for feature extraction
    disabled = ["tagger", "parser", "attribute_ruler", "lemmatizer"]
    nlp = spacy.load("en_core_web_sm", disable=disabled)

    # Build lookup: canonical_key → entity dict
    # canonical_key = f"{canonical_name}_{label}" matches entity_id format "ent_{canon}_{label}"
    canon_lookup: dict[str, dict] = {}
    for ent in entities:
        canon = ent.get("canonical_name", "")
        etype = ent.get("entity_type", "")
        key = f"{canon}_{etype}"
        canon_lookup[key] = ent

    click.echo(f"  Entity lookup built: {len(canon_lookup)} canonical keys")

    cemap: dict[str, list[dict]] = {}
    total_mentions = 0
    chunk_ids = [c["chunk_id"] for c in chunks]
    texts = [c["text"] for c in chunks]

    click.echo(f"  Running batch NER on {len(texts)} chunks (batch_size={batch_size})...")
    processed = 0
    t0 = time.perf_counter()

    for doc, chunk_id in zip(
        nlp.pipe(texts, batch_size=batch_size),
        chunk_ids,
        strict=True,
    ):
        chunk_ents: list[dict] = []
        seen_ids: set[str] = set()

        for ent in doc.ents:
            canonical = ent.text.strip().lower().replace(" ", "_")
            key = f"{canonical}_{ent.label_}"

            if key in canon_lookup and canon_lookup[key]["entity_id"] not in seen_ids:
                chunk_ents.append(canon_lookup[key])
                seen_ids.add(canon_lookup[key]["entity_id"])
                total_mentions += 1

        cemap[chunk_id] = chunk_ents
        processed += 1

        if processed % 10000 == 0:
            elapsed = time.perf_counter() - t0
            rate = processed / elapsed
            eta = (len(texts) - processed) / rate if rate > 0 else 0
            click.echo(
                f"  NER: {processed}/{len(texts)} chunks, "
                f"{total_mentions} mentions, "
                f"{rate:.0f} chunks/sec, ETA {eta:.0f}s"
            )

    click.echo(f"  NER complete: {total_mentions} mentions across {processed} chunks")
    return cemap


@click.command()
@click.option("--input", "-i", "input_dir", required=True, help="Dir with processed JSON files")
@click.option("--collection", default="enron_chunks", help="ChromaDB collection name")
@click.option("--chroma-host", default="localhost")
@click.option("--chroma-port", default=8000, type=int)
@click.option("--neo4j-uri", default="bolt://localhost:7687")
@click.option("--neo4j-user", default="neo4j")
@click.option("--neo4j-pass", default="pivorag_dev_2025")
@click.option("--embed-model", default="all-MiniLM-L6-v2")
@click.option("--embed-batch-size", default=256, type=int)
@click.option("--chroma-batch-size", default=500, type=int)
@click.option("--neo4j-batch-size", default=1000, type=int)
@click.option("--skip-chroma", is_flag=True, help="Skip ChromaDB insertion")
@click.option("--skip-neo4j", is_flag=True, help="Skip Neo4j insertion")
@click.option("--ner-cache", default=None, help="NER cache path (JSON)")
def main(
    input_dir: str,
    collection: str,
    chroma_host: str,
    chroma_port: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    embed_model: str,
    embed_batch_size: int,
    chroma_batch_size: int,
    neo4j_batch_size: int,
    skip_chroma: bool,
    skip_neo4j: bool,
    ner_cache: str | None,
) -> None:
    """Load pre-processed data into ChromaDB and Neo4j."""
    start = time.perf_counter()
    inp = Path(input_dir)

    # Load pre-processed data
    click.echo("[1/4] Loading pre-processed data...")
    chunks = load_json(inp / "processed_chunks.json", "chunks")
    entities = load_json(inp / "extracted_entities.json", "entities")
    relations = load_json(inp / "extracted_relations.json", "relations")

    # Rebuild chunk-entity map via batch NER (with optional cache)
    cache_path = Path(ner_cache) if ner_cache else None
    if cache_path and cache_path.exists():
        click.echo("\n[2/4] Loading cached chunk-entity map...")
        chunk_entity_map = json.loads(cache_path.read_text())
        click.echo(f"  Loaded cache: {len(chunk_entity_map)} chunks mapped")
    else:
        click.echo("\n[2/4] Rebuilding chunk-entity map (batch spaCy NER)...")
        chunk_entity_map = rebuild_chunk_entity_map_ner(chunks, entities)
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(chunk_entity_map))
            click.echo(f"  Saved NER cache to {cache_path}")

    # Generate embeddings
    if not skip_chroma:
        click.echo(f"\n[3/4] Generating embeddings ({embed_model})...")
        from pivorag.vector.embed import EmbeddingModel

        model = EmbeddingModel(model_name=embed_model)
        texts = [c["text"] for c in chunks]

        # Batch embedding with progress
        all_embeddings = []
        for i in range(0, len(texts), embed_batch_size):
            batch = texts[i : i + embed_batch_size]
            embs = model.embed_batch(batch, batch_size=embed_batch_size)
            all_embeddings.extend(embs)
            if (i // embed_batch_size) % 20 == 0:
                click.echo(f"  Embedded {len(all_embeddings)}/{len(texts)} chunks...")

        click.echo(f"  Done: {len(all_embeddings)} embeddings (dim={model.dimension})")

        # Insert into ChromaDB
        click.echo(f"\n[3b/4] Inserting into ChromaDB ({collection})...")
        from pivorag.vector.index import VectorIndex

        index = VectorIndex(host=chroma_host, port=chroma_port, collection_name=collection)

        for i in range(0, len(chunks), chroma_batch_size):
            batch = chunks[i : i + chroma_batch_size]
            batch_embs = all_embeddings[i : i + chroma_batch_size]
            ids = [c["chunk_id"] for c in batch]
            documents = [c["text"] for c in batch]
            metadatas = [
                {
                    "doc_id": c.get("doc_id", ""),
                    "tenant": c.get("tenant", ""),
                    "sensitivity": c.get("sensitivity", "PUBLIC"),
                    "domain": c.get("domain", ""),
                    "doc_type": c.get("doc_type", ""),
                    "trust_score": c.get("trust_score", 1.0),
                    "provenance_score": c.get("provenance_score", 1.0),
                }
                for c in batch
            ]
            index.add_chunks(ids, [e.tolist() for e in batch_embs], documents, metadatas)
            if (i // chroma_batch_size) % 20 == 0:
                click.echo(f"  Inserted {min(i + chroma_batch_size, len(chunks))}/{len(chunks)}...")

        click.echo(f"  ChromaDB total: {index.count()} chunks")
    else:
        click.echo("\n[3/4] Skipping ChromaDB (--skip-chroma)")

    # Build Neo4j graph using batch UNWIND queries (100-1000x faster than single inserts)
    if not skip_neo4j:
        click.echo("\n[4/4] Building Neo4j graph (batch UNWIND)...")
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
        entity_id_set = {e["entity_id"] for e in entities}

        try:
            # Create constraints
            with driver.session() as session:
                for cypher in [
                    "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.node_id IS UNIQUE",
                    "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Chunk) REQUIRE c.node_id IS UNIQUE",
                    "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.node_id IS UNIQUE",
                ]:
                    session.run(cypher)
            click.echo("  Created constraints")

            # Clear existing data
            with driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
            click.echo("  Cleared existing graph data")

            # Batch insert Document nodes
            doc_rows = []
            doc_ids_seen: set[str] = set()
            for chunk in chunks:
                doc_id = chunk["doc_id"]
                if doc_id not in doc_ids_seen:
                    doc_rows.append({
                        "node_id": doc_id,
                        "tenant": chunk.get("tenant", ""),
                        "sensitivity": chunk.get("sensitivity", "PUBLIC"),
                        "provenance_score": chunk.get("provenance_score", 1.0),
                    })
                    doc_ids_seen.add(doc_id)

            for i in range(0, len(doc_rows), neo4j_batch_size):
                batch = doc_rows[i : i + neo4j_batch_size]
                with driver.session() as session:
                    session.run(
                        "UNWIND $rows AS row "
                        "MERGE (d:Document {node_id: row.node_id}) "
                        "SET d.tenant = row.tenant, d.sensitivity = row.sensitivity, "
                        "d.provenance_score = row.provenance_score",
                        rows=batch,
                    )
            click.echo(f"  Added {len(doc_rows)} Document nodes")

            # Batch insert Chunk nodes
            chunk_rows = [
                {
                    "node_id": c["chunk_id"],
                    "tenant": c.get("tenant", ""),
                    "sensitivity": c.get("sensitivity", "PUBLIC"),
                    "provenance_score": c.get("trust_score", 1.0),
                }
                for c in chunks
            ]
            for i in range(0, len(chunk_rows), neo4j_batch_size):
                batch = chunk_rows[i : i + neo4j_batch_size]
                with driver.session() as session:
                    session.run(
                        "UNWIND $rows AS row "
                        "MERGE (c:Chunk {node_id: row.node_id}) "
                        "SET c.tenant = row.tenant, c.sensitivity = row.sensitivity, "
                        "c.provenance_score = row.provenance_score",
                        rows=batch,
                    )
                if (i // neo4j_batch_size) % 20 == 0:
                    done = min(i + neo4j_batch_size, len(chunk_rows))
                    click.echo(f"  Chunk nodes: {done}/{len(chunk_rows)}...")
            click.echo(f"  Added {len(chunk_rows)} Chunk nodes")

            # Batch insert Entity nodes
            entity_rows = [
                {
                    "node_id": e["entity_id"],
                    "text": e.get("text", ""),
                    "entity_type": e.get("entity_type", ""),
                    "canonical_name": e.get("canonical_name", ""),
                }
                for e in entities
            ]
            for i in range(0, len(entity_rows), neo4j_batch_size):
                batch = entity_rows[i : i + neo4j_batch_size]
                with driver.session() as session:
                    session.run(
                        "UNWIND $rows AS row "
                        "MERGE (e:Entity {node_id: row.node_id}) "
                        "SET e.text = row.text, e.entity_type = row.entity_type, "
                        "e.canonical_name = row.canonical_name, "
                        "e.tenant = '', e.sensitivity = 'PUBLIC', e.provenance_score = 1.0",
                        rows=batch,
                    )
                if (i // neo4j_batch_size) % 20 == 0:
                    done = min(i + neo4j_batch_size, len(entity_rows))
                    click.echo(f"  Entity nodes: {done}/{len(entity_rows)}...")
            click.echo(f"  Added {len(entity_rows)} Entity nodes")

            # Batch insert CONTAINS edges (doc → chunk)
            contains_rows = [
                {"source": c["doc_id"], "target": c["chunk_id"]}
                for c in chunks
            ]
            for i in range(0, len(contains_rows), neo4j_batch_size):
                batch = contains_rows[i : i + neo4j_batch_size]
                with driver.session() as session:
                    session.run(
                        "UNWIND $rows AS row "
                        "MATCH (d:Document {node_id: row.source}), (c:Chunk {node_id: row.target}) "
                        "MERGE (d)-[:CONTAINS {trust_score: 1.0}]->(c)",
                        rows=batch,
                    )
                if (i // neo4j_batch_size) % 50 == 0:
                    done = min(i + neo4j_batch_size, len(contains_rows))
                    click.echo(f"  CONTAINS: {done}/{len(contains_rows)}...")
            click.echo(f"  Added {len(contains_rows)} CONTAINS edges")

            # Batch insert MENTIONS edges (chunk → entity)
            mentions_rows: list[dict[str, str]] = []
            seen_mentions: set[tuple[str, str]] = set()
            for chunk_id, ent_list in chunk_entity_map.items():
                for ent in ent_list:
                    eid = ent["entity_id"]
                    pair = (chunk_id, eid)
                    if pair not in seen_mentions and eid in entity_id_set:
                        mentions_rows.append({"source": chunk_id, "target": eid})
                        seen_mentions.add(pair)

            click.echo(f"  Prepared {len(mentions_rows)} MENTIONS edges for insertion...")
            for i in range(0, len(mentions_rows), neo4j_batch_size):
                batch = mentions_rows[i : i + neo4j_batch_size]
                with driver.session() as session:
                    session.run(
                        "UNWIND $rows AS row "
                        "MATCH (c:Chunk {node_id: row.source}), (e:Entity {node_id: row.target}) "
                        "MERGE (c)-[:MENTIONS {trust_score: 1.0}]->(e)",
                        rows=batch,
                    )
                if (i // neo4j_batch_size) % 50 == 0:
                    done = min(i + neo4j_batch_size, len(mentions_rows))
                    click.echo(f"  MENTIONS: {done}/{len(mentions_rows)}...")
            click.echo(f"  Added {len(mentions_rows)} MENTIONS edges")

            # Batch insert relation edges (entity → entity)
            rel_rows: list[dict] = []
            for rel in relations:
                src = rel["source_entity"]
                tgt = rel["target_entity"]
                if src in entity_id_set and tgt in entity_id_set:
                    rel_rows.append({
                        "source": src,
                        "target": tgt,
                        "rel_type": rel.get("relation_type", "RELATED_TO"),
                        "confidence": rel.get("confidence", 0.5),
                    })

            for i in range(0, len(rel_rows), neo4j_batch_size):
                batch = rel_rows[i : i + neo4j_batch_size]
                with driver.session() as session:
                    session.run(
                        "UNWIND $rows AS row "
                        "MATCH (s:Entity {node_id: row.source}), (t:Entity {node_id: row.target}) "
                        "MERGE (s)-[:RELATED_TO {trust_score: row.confidence}]->(t)",
                        rows=batch,
                    )
            click.echo(f"  Added {len(rel_rows)} relation edges")

            # Stats
            with driver.session() as session:
                nc = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
                ec = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            click.echo(f"  Graph: {nc} nodes, {ec} edges")
        finally:
            driver.close()
    else:
        click.echo("\n[4/4] Skipping Neo4j (--skip-neo4j)")

    elapsed = time.perf_counter() - start
    click.echo(f"\nDone in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
