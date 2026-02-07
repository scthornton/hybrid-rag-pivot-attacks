#!/usr/bin/env python3
"""Build ChromaDB vector index and Neo4j graph from processed data.

Runs the complete ingestion pipeline:
  1. Load synthetic JSON documents
  2. Chunk documents (TokenChunker)
  3. Extract entities (EntityExtractor with spaCy)
  4. Extract relations (RelationExtractor)
  5. Label sensitivity (SensitivityLabeler)
  6. Score provenance (ProvenanceScorer)
  7. Generate embeddings (EmbeddingModel)
  8. Insert into ChromaDB (VectorIndex)
  9. Build Neo4j graph (GraphBuilder)
  10. Print statistics and verify

Usage:
    # Dry run (no external services needed)
    python scripts/build_indexes.py --data data/raw/synthetic_enterprise.json --dry-run

    # Full run against local services
    python scripts/build_indexes.py --data data/raw/synthetic_enterprise.json

    # Full run with custom connection settings
    python scripts/build_indexes.py --data data/raw/synthetic_enterprise.json \\
        --chroma-host localhost --chroma-port 8000 \\
        --neo4j-uri bolt://localhost:7687 --neo4j-user neo4j --neo4j-pass localpassword
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import click

from pivorag.graph.schema import Document, GraphEdge, GraphNode
from pivorag.ingestion.chunker import TokenChunker
from pivorag.ingestion.entity_extract import EntityExtractor
from pivorag.ingestion.provenance import ProvenanceScorer, SourceType
from pivorag.ingestion.relation_extract import RelationExtractor
from pivorag.ingestion.sensitivity import SensitivityLabeler


def load_documents(data_path: str) -> list[dict]:
    """Load documents from the synthetic data JSON file."""
    raw = json.loads(Path(data_path).read_text())
    click.echo(f"Loaded {len(raw)} documents from {data_path}")
    return raw


def step_chunk(documents: list[dict], target_size: int, overlap: int) -> list[dict]:
    """Step 1: Chunk all documents into overlapping token chunks."""
    chunker = TokenChunker(target_size=target_size, overlap=overlap)
    all_chunks = []

    for doc_data in documents:
        doc = Document(
            doc_id=doc_data["doc_id"],
            title=doc_data.get("title", ""),
            text=doc_data["text"],
            source=doc_data.get("source", ""),
            tenant=doc_data.get("tenant", ""),
            sensitivity=doc_data.get("sensitivity", "PUBLIC"),
            provenance_score=doc_data.get("provenance_score", 1.0),
        )
        chunks = chunker.chunk_document(doc)
        for chunk in chunks:
            all_chunks.append({
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "text": chunk.text,
                "token_count": chunk.token_count,
                "tenant": chunk.tenant,
                "sensitivity": chunk.sensitivity,
                "chunk_index": chunk.chunk_index,
                "domain": doc_data.get("domain", ""),
                "doc_type": doc_data.get("doc_type", ""),
                "source": doc_data.get("source", ""),
                "provenance_score": doc_data.get("provenance_score", 1.0),
                # Carry forward ground truth annotations
                "gt_entities": doc_data.get("entities_mentioned", []),
                "gt_bridge_entities": doc_data.get("bridge_entities", []),
                "gt_relations": doc_data.get("relations", []),
            })

    click.echo(f"  Chunked {len(documents)} documents → {len(all_chunks)} chunks")
    return all_chunks


def step_extract_entities(chunks: list[dict]) -> tuple[list[dict], dict[str, list]]:
    """Step 2: Extract entities from all chunks using spaCy NER."""
    extractor = EntityExtractor()
    all_entities: list[dict] = []
    chunk_entity_map: dict[str, list] = {}  # chunk_id → [entity_dicts]

    for chunk in chunks:
        extracted = extractor.extract(chunk["text"], chunk["chunk_id"])
        chunk_entities = []
        for ent in extracted:
            entity_dict = {
                "entity_id": ent.entity_id,
                "text": ent.text,
                "entity_type": ent.entity_type,
                "canonical_name": ent.canonical_name,
                "source_chunk_id": ent.source_chunk_id,
                "confidence": ent.confidence,
            }
            all_entities.append(entity_dict)
            chunk_entities.append(entity_dict)
        chunk_entity_map[chunk["chunk_id"]] = chunk_entities

    # Deduplicate entities by entity_id
    unique_entities = {}
    for ent in all_entities:
        if ent["entity_id"] not in unique_entities:
            unique_entities[ent["entity_id"]] = ent
        else:
            # Track how many chunks mention this entity
            existing = unique_entities[ent["entity_id"]]
            existing.setdefault("mention_count", 1)
            existing["mention_count"] = existing.get("mention_count", 1) + 1

    deduped = list(unique_entities.values())
    click.echo(
        f"  Extracted {len(all_entities)} entity mentions → "
        f"{len(deduped)} unique entities"
    )
    return deduped, chunk_entity_map


def _build_name_to_id_map(chunk_entity_map: dict[str, list]) -> dict[str, str]:
    """Build a mapping from entity canonical_name → entity_id for GT relation resolution."""
    name_map: dict[str, str] = {}
    for ent_list in chunk_entity_map.values():
        for ent in ent_list:
            canon = ent["canonical_name"]
            if canon not in name_map:
                name_map[canon] = ent["entity_id"]
    return name_map


def _resolve_gt_entity(raw_name: str, name_map: dict[str, str]) -> str | None:
    """Resolve a ground-truth entity name to a NER entity_id."""
    canonical = raw_name.strip().lower().replace(" ", "_")
    # Direct match
    if canonical in name_map:
        return name_map[canonical]
    # Try with hyphens preserved (for system names like "api-gateway")
    canonical_hyphen = raw_name.strip().lower().replace(" ", "-")
    if canonical_hyphen in name_map:
        return name_map[canonical_hyphen]
    return None


def step_extract_relations(
    chunks: list[dict],
    chunk_entity_map: dict[str, list],
) -> list[dict]:
    """Step 3: Extract relations between entities.

    Two-pass approach:
    1. Resolve ground-truth relations (from synthetic data templates)
       by mapping raw entity names to NER entity IDs.
    2. Always run pattern-based extraction on NER entity pairs to
       catch relations between entities that GT doesn't cover.
    Deduplicates by (source, target) pair.
    """
    extractor = RelationExtractor()
    name_map = _build_name_to_id_map(chunk_entity_map)
    all_relations: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    gt_resolved = 0
    gt_unresolved = 0
    pattern_count = 0

    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        entities = chunk_entity_map.get(chunk_id, [])

        # Pass 1: Ground-truth relations (when entities resolve to NER IDs)
        for rel in chunk.get("gt_relations", []):
            src_id = _resolve_gt_entity(rel["source"], name_map)
            tgt_id = _resolve_gt_entity(rel["target"], name_map)
            if src_id and tgt_id:
                pair = (src_id, tgt_id)
                if pair not in seen_pairs:
                    all_relations.append({
                        "source_entity": src_id,
                        "target_entity": tgt_id,
                        "relation_type": rel["type"],
                        "source_chunk_id": chunk_id,
                        "confidence": 0.8,
                        "evidence": chunk["text"][:200],
                    })
                    seen_pairs.add(pair)
                    gt_resolved += 1
            else:
                gt_unresolved += 1

        # Pass 2: Pattern-based extraction on NER entity pairs
        if len(entities) >= 2:
            extracted = extractor.extract_from_chunk(
                entities=entities,
                chunk_text=chunk["text"],
                chunk_id=chunk_id,
            )
            for rel in extracted:
                pair = (rel.source_entity_id, rel.target_entity_id)
                if pair not in seen_pairs:
                    all_relations.append({
                        "source_entity": rel.source_entity_id,
                        "target_entity": rel.target_entity_id,
                        "relation_type": rel.relation_type,
                        "source_chunk_id": rel.source_chunk_id,
                        "confidence": rel.confidence,
                        "evidence": rel.evidence_text,
                    })
                    seen_pairs.add(pair)
                    pattern_count += 1

    click.echo(
        f"  Extracted {len(all_relations)} relations "
        f"(GT: {gt_resolved} resolved, {gt_unresolved} unresolved; "
        f"Pattern: {pattern_count})"
    )
    return all_relations


def step_label_sensitivity(chunks: list[dict]) -> list[dict]:
    """Step 4: Verify/relabel sensitivity tiers based on content."""
    labeler = SensitivityLabeler()
    relabeled = 0

    for chunk in chunks:
        # Use the metadata tier from the source document
        original = chunk["sensitivity"]
        labeled = labeler.label(chunk["text"], metadata_tier=original)
        chunk["sensitivity_verified"] = labeled.value
        if labeled.value != original:
            relabeled += 1

    click.echo(f"  Verified sensitivity labels ({relabeled} would change if content-based)")
    return chunks


def step_score_provenance(chunks: list[dict]) -> list[dict]:
    """Step 5: Score provenance/trust for each chunk."""
    scorer = ProvenanceScorer()

    source_type_map = {
        "engineering_wiki": SourceType.CURATED,
        "finance_system": SourceType.INTERNAL_SYSTEM,
        "hr_system": SourceType.INTERNAL_SYSTEM,
        "security_system": SourceType.INTERNAL_SYSTEM,
    }

    for chunk in chunks:
        source = chunk.get("source", "")
        source_type = source_type_map.get(source, SourceType.USER_GENERATED)
        chunk["trust_score"] = scorer.score(source_type)

    click.echo("  Scored provenance for all chunks")
    return chunks


def step_embed(chunks: list[dict], batch_size: int) -> list[dict]:
    """Step 6: Generate embeddings for all chunks."""
    from pivorag.vector.embed import EmbeddingModel

    model = EmbeddingModel()
    texts = [c["text"] for c in chunks]

    click.echo(f"  Generating embeddings for {len(texts)} chunks (batch_size={batch_size})...")
    embeddings = model.embed_batch(texts, batch_size=batch_size)

    for chunk, emb in zip(chunks, embeddings, strict=True):
        chunk["embedding"] = emb.tolist()

    click.echo(f"  Generated {len(embeddings)} embeddings (dim={model.dimension})")
    return chunks


def step_insert_chromadb(
    chunks: list[dict],
    host: str,
    port: int,
    collection_name: str,
    batch_size: int,
) -> int:
    """Step 7: Insert chunks into ChromaDB."""
    from pivorag.vector.index import VectorIndex

    index = VectorIndex(host=host, port=port, collection_name=collection_name)

    # Insert in batches to avoid memory issues
    total = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        ids = [c["chunk_id"] for c in batch]
        embeddings = [c["embedding"] for c in batch]
        documents = [c["text"] for c in batch]
        metadatas = [
            {
                "doc_id": c["doc_id"],
                "tenant": c["tenant"],
                "sensitivity": c["sensitivity"],
                "domain": c.get("domain", ""),
                "doc_type": c.get("doc_type", ""),
                "trust_score": c.get("trust_score", 1.0),
                "provenance_score": c.get("provenance_score", 1.0),
            }
            for c in batch
        ]
        index.add_chunks(ids, embeddings, documents, metadatas)
        total += len(batch)

    click.echo(f"  Inserted {total} chunks into ChromaDB ({collection_name})")
    return index.count()


def step_build_graph(
    chunks: list[dict],
    entities: list[dict],
    relations: list[dict],
    chunk_entity_map: dict[str, list],
    uri: str,
    username: str,
    password: str,
) -> dict[str, Any]:
    """Step 8: Build Neo4j knowledge graph."""
    from pivorag.graph.build_graph import GraphBuilder

    builder = GraphBuilder(uri=uri, username=username, password=password)

    # Build a set of valid entity IDs for edge validation
    entity_id_set = {ent["entity_id"] for ent in entities}

    try:
        # Create constraints
        builder.create_constraints()
        click.echo("  Created uniqueness constraints")

        # Add document and chunk nodes
        doc_ids_seen = set()
        for chunk in chunks:
            # Add document node if not seen
            doc_id = chunk["doc_id"]
            if doc_id not in doc_ids_seen:
                builder.add_node(GraphNode(
                    node_id=doc_id,
                    node_type="Document",
                    tenant=chunk["tenant"],
                    sensitivity=chunk["sensitivity"],
                    provenance_score=chunk.get("provenance_score", 1.0),
                    properties={
                        "domain": chunk.get("domain", ""),
                        "doc_type": chunk.get("doc_type", ""),
                    },
                ))
                doc_ids_seen.add(doc_id)

            # Add chunk node
            builder.add_node(GraphNode(
                node_id=chunk["chunk_id"],
                node_type="Chunk",
                tenant=chunk["tenant"],
                sensitivity=chunk["sensitivity"],
                provenance_score=chunk.get("trust_score", 1.0),
            ))

            # Document CONTAINS Chunk edge
            builder.add_edge(GraphEdge(
                source_id=doc_id,
                target_id=chunk["chunk_id"],
                edge_type="CONTAINS",
                trust_score=1.0,
            ))

        click.echo(f"  Added {len(doc_ids_seen)} document nodes + {len(chunks)} chunk nodes")

        # Add entity nodes
        for ent in entities:
            builder.add_node(GraphNode(
                node_id=ent["entity_id"],
                node_type="Entity",
                properties={
                    "text": ent["text"],
                    "entity_type": ent["entity_type"],
                    "canonical_name": ent["canonical_name"],
                },
            ))

        click.echo(f"  Added {len(entities)} entity nodes")

        # Add MENTIONS edges (chunk → entity) using NER-extracted entity IDs
        mentions_count = 0
        mentions_skipped = 0
        seen_mentions = set()
        for chunk_id, ent_list in chunk_entity_map.items():
            for ent in ent_list:
                eid = ent["entity_id"]
                # Deduplicate: same chunk→entity pair only once
                pair = (chunk_id, eid)
                if pair in seen_mentions:
                    continue
                seen_mentions.add(pair)

                if eid in entity_id_set:
                    builder.add_edge(GraphEdge(
                        source_id=chunk_id,
                        target_id=eid,
                        edge_type="MENTIONS",
                        trust_score=1.0,
                    ))
                    mentions_count += 1
                else:
                    mentions_skipped += 1

        click.echo(
            f"  Added {mentions_count} MENTIONS edges "
            f"({mentions_skipped} skipped — entity not found)"
        )

        # Add relation edges (entity → entity)
        relation_count = 0
        relation_skipped = 0
        for rel in relations:
            src = rel["source_entity"]
            tgt = rel["target_entity"]
            if src in entity_id_set and tgt in entity_id_set:
                builder.add_edge(GraphEdge(
                    source_id=src,
                    target_id=tgt,
                    edge_type=rel.get("relation_type", "RELATED_TO"),
                    trust_score=rel.get("confidence", 0.5),
                ))
                relation_count += 1
            else:
                relation_skipped += 1

        click.echo(
            f"  Added {relation_count} relation edges "
            f"({relation_skipped} skipped — entity not found)"
        )

        stats = builder.get_stats()
        click.echo(f"  Graph stats: {stats['nodes']} nodes, {stats['edges']} edges")
        return stats

    finally:
        builder.close()


def save_processed_data(
    chunks: list[dict],
    entities: list[dict],
    relations: list[dict],
    output_dir: str,
) -> None:
    """Save processed data for later use (e.g., dry-run mode)."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Save chunks (without embeddings to save space)
    chunks_out = []
    for c in chunks:
        c_copy = {k: v for k, v in c.items() if k != "embedding"}
        chunks_out.append(c_copy)

    (out / "processed_chunks.json").write_text(json.dumps(chunks_out, indent=2))
    (out / "extracted_entities.json").write_text(json.dumps(entities, indent=2))
    (out / "extracted_relations.json").write_text(json.dumps(relations, indent=2))
    click.echo(f"  Saved processed data to {out}/")


@click.command()
@click.option("--data", "-d", required=True, help="Path to synthetic documents JSON")
@click.option("--output", "-o", default="data/processed", help="Output dir for processed data")
@click.option("--chroma-host", default="localhost", help="ChromaDB host")
@click.option("--chroma-port", default=8000, type=int, help="ChromaDB port")
@click.option("--chroma-collection", default="pivorag_chunks", help="ChromaDB collection name")
@click.option("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j URI")
@click.option("--neo4j-user", default="neo4j", help="Neo4j username")
@click.option("--neo4j-pass", default="localpassword", help="Neo4j password")
@click.option("--chunk-size", default=300, type=int, help="Target chunk size in tokens")
@click.option("--chunk-overlap", default=50, type=int, help="Chunk overlap in tokens")
@click.option("--embed-batch-size", default=64, type=int, help="Embedding batch size")
@click.option("--dry-run", is_flag=True, help="Process data without writing to databases")
@click.option("--skip-embed", is_flag=True, help="Skip embedding generation (fast iteration)")
def main(
    data: str,
    output: str,
    chroma_host: str,
    chroma_port: int,
    chroma_collection: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pass: str,
    chunk_size: int,
    chunk_overlap: int,
    embed_batch_size: int,
    dry_run: bool,
    skip_embed: bool,
) -> None:
    """Build vector and graph indexes from synthetic enterprise data."""
    start = time.perf_counter()

    if dry_run:
        click.echo("DRY RUN — processing data without database writes")

    # Step 0: Load documents
    documents = load_documents(data)

    # Step 1: Chunk documents
    click.echo("\n[1/8] Chunking documents...")
    chunks = step_chunk(documents, target_size=chunk_size, overlap=chunk_overlap)

    # Step 2: Extract entities
    click.echo("\n[2/8] Extracting entities (spaCy NER)...")
    entities, chunk_entity_map = step_extract_entities(chunks)

    # Step 3: Extract relations
    click.echo("\n[3/8] Extracting relations...")
    relations = step_extract_relations(chunks, chunk_entity_map)

    # Step 4: Verify sensitivity labels
    click.echo("\n[4/8] Verifying sensitivity labels...")
    chunks = step_label_sensitivity(chunks)

    # Step 5: Score provenance
    click.echo("\n[5/8] Scoring provenance...")
    chunks = step_score_provenance(chunks)

    # Step 6: Generate embeddings
    if skip_embed:
        click.echo("\n[6/8] Skipping embeddings (--skip-embed)")
    else:
        click.echo("\n[6/8] Generating embeddings...")
        chunks = step_embed(chunks, batch_size=embed_batch_size)

    # Save processed data regardless of dry-run
    click.echo("\n[7/8] Saving processed data...")
    save_processed_data(chunks, entities, relations, output)

    # Step 7+8: Insert into databases (unless dry-run)
    if dry_run:
        click.echo("\n[8/8] Skipping database writes (dry-run)")
    else:
        if not skip_embed:
            click.echo("\n[7b/8] Inserting into ChromaDB...")
            chroma_count = step_insert_chromadb(
                chunks, chroma_host, chroma_port, chroma_collection, batch_size=100
            )
            click.echo(f"  ChromaDB total: {chroma_count} chunks")

        click.echo("\n[8/8] Building Neo4j graph...")
        graph_stats = step_build_graph(
            chunks, entities, relations, chunk_entity_map,
            neo4j_uri, neo4j_user, neo4j_pass,
        )

    elapsed = time.perf_counter() - start
    click.echo(f"\nDone in {elapsed:.1f}s")

    # Summary
    click.echo("\n=== Pipeline Summary ===")
    click.echo(f"Documents:  {len(documents)}")
    click.echo(f"Chunks:     {len(chunks)}")
    click.echo(f"Entities:   {len(entities)}")
    click.echo(f"Relations:  {len(relations)}")
    if not skip_embed and not dry_run:
        click.echo(f"ChromaDB:   {chroma_count} indexed")
    if not dry_run:
        click.echo(f"Neo4j:      {graph_stats['nodes']} nodes, {graph_stats['edges']} edges")


if __name__ == "__main__":
    main()
