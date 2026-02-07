"""Populate Neo4j knowledge graph from extracted entities and relations.

Creates nodes and edges in Neo4j based on the extracted entities,
relations, and document/chunk metadata from the ingestion pipeline.
"""

from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase

from pivorag.graph.schema import GraphEdge, GraphNode


class GraphBuilder:
    """Build and populate the Neo4j knowledge graph."""

    def __init__(self, uri: str, username: str, password: str) -> None:
        self.driver = GraphDatabase.driver(uri, auth=(username, password))

    def close(self) -> None:
        self.driver.close()

    def clear_database(self) -> None:
        """Remove all nodes and edges. Use with caution."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def create_constraints(self) -> None:
        """Create uniqueness constraints for node IDs."""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:System) REQUIRE s.system_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Project) REQUIRE p.project_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
        ]
        with self.driver.session() as session:
            for constraint in constraints:
                session.run(constraint)

    def add_node(self, node: GraphNode) -> None:
        """Create or merge a node in Neo4j."""
        query = (
            f"MERGE (n:{node.node_type} {{node_id: $node_id}}) "
            "SET n += $properties, n.tenant = $tenant, "
            "n.sensitivity = $sensitivity, n.provenance_score = $provenance_score"
        )
        with self.driver.session() as session:
            session.run(query, {
                "node_id": node.node_id,
                "properties": node.properties,
                "tenant": node.tenant,
                "sensitivity": node.sensitivity,
                "provenance_score": node.provenance_score,
            })

    def add_edge(self, edge: GraphEdge) -> None:
        """Create a relationship between two nodes."""
        query = (
            "MATCH (a {node_id: $source_id}), (b {node_id: $target_id}) "
            f"MERGE (a)-[r:{edge.edge_type.value}]->(b) "
            "SET r += $properties, r.trust_score = $trust_score"
        )
        with self.driver.session() as session:
            session.run(query, {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "properties": edge.properties,
                "trust_score": edge.trust_score,
            })

    def add_nodes_batch(self, nodes: list[GraphNode]) -> None:
        """Batch-add nodes for efficiency."""
        for node in nodes:
            self.add_node(node)

    def add_edges_batch(self, edges: list[GraphEdge]) -> None:
        """Batch-add edges for efficiency."""
        for edge in edges:
            self.add_edge(edge)

    def get_stats(self) -> dict[str, Any]:
        """Return graph statistics."""
        with self.driver.session() as session:
            node_count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            edge_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            return {"nodes": node_count, "edges": edge_count}
