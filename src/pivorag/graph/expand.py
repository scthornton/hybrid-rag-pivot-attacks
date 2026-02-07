"""Graph expansion algorithms for hybrid RAG context assembly.

Implements BFS, Random Walk with Restart, and community-based
expansion from seed nodes identified by vector retrieval.
This is where retrieval pivot risk manifests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pivorag.graph.schema import GraphNode


@dataclass
class ExpansionResult:
    """Result of a graph expansion from seed nodes."""

    seed_nodes: list[str]
    expanded_nodes: list[GraphNode]
    traversal_path: list[tuple[str, str, str]]  # (source, edge_type, target)
    total_hops: int
    nodes_visited: int
    edges_traversed: int
    metadata: dict[str, Any] = field(default_factory=dict)


class GraphExpander:
    """Expand context from seed nodes via graph traversal."""

    def __init__(self, driver) -> None:
        self.driver = driver

    def bfs_expand(
        self,
        seed_node_ids: list[str],
        max_hops: int = 2,
        max_branching: int = 10,
        max_total_nodes: int = 50,
        allowed_edge_types: list[str] | None = None,
    ) -> ExpansionResult:
        """Breadth-first expansion from seed nodes.

        This is the core operation that can cause retrieval pivot risk:
        starting from vector-retrieved seeds, BFS walks into potentially
        unauthorized graph neighborhoods.
        """
        edge_filter = ""
        if allowed_edge_types:
            types_str = "|".join(allowed_edge_types)
            edge_filter = f":{types_str}"

        query = f"""
        UNWIND $seed_ids AS seed_id
        MATCH (start {{node_id: seed_id}})
        CALL apoc.path.subgraphNodes(start, {{
            maxLevel: $max_hops,
            relationshipFilter: '{edge_filter}',
            limit: $max_total
        }})
        YIELD node
        RETURN DISTINCT node.node_id AS node_id,
               labels(node)[0] AS node_type,
               node.tenant AS tenant,
               node.sensitivity AS sensitivity,
               node.provenance_score AS provenance_score,
               properties(node) AS props
        LIMIT $max_total
        """

        expanded = []
        with self.driver.session() as session:
            result = session.run(query, {
                "seed_ids": seed_node_ids,
                "max_hops": max_hops,
                "max_total": max_total_nodes,
            })
            for record in result:
                expanded.append(GraphNode(
                    node_id=record["node_id"],
                    node_type=record["node_type"] or "Unknown",
                    tenant=record["tenant"] or "",
                    sensitivity=record["sensitivity"] or "PUBLIC",
                    provenance_score=record["provenance_score"] or 1.0,
                    properties=dict(record["props"]) if record["props"] else {},
                ))

        return ExpansionResult(
            seed_nodes=seed_node_ids,
            expanded_nodes=expanded,
            traversal_path=[],
            total_hops=max_hops,
            nodes_visited=len(expanded),
            edges_traversed=0,
        )

    def rwr_expand(
        self,
        seed_node_ids: list[str],
        restart_prob: float = 0.15,
        max_iterations: int = 100,
        max_total_nodes: int = 50,
    ) -> ExpansionResult:
        """Random Walk with Restart expansion from seed nodes.

        Provides trust-biased traversal when combined with edge weights.
        """
        raise NotImplementedError("RWR expansion — implement with networkx or Neo4j GDS")
