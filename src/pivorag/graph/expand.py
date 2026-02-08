"""Graph expansion algorithms for hybrid RAG context assembly.

Implements BFS, Random Walk with Restart, and community-based
expansion from seed nodes identified by vector retrieval.
This is where retrieval pivot risk manifests.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pivorag.graph.schema import GraphNode

logger = logging.getLogger(__name__)

# Valid Neo4j relationship types — used to sanitise edge filters before
# they are interpolated into Cypher queries, preventing injection.
VALID_EDGE_TYPES = frozenset({
    "CONTAINS", "MENTIONS", "BELONGS_TO", "DEPENDS_ON",
    "OWNED_BY", "DERIVED_FROM", "RELATED_TO",
})


@dataclass
class ExpansionResult:
    """Result of a graph expansion from seed nodes."""

    seed_nodes: list[str]
    expanded_nodes: list[GraphNode]
    traversal_path: list[tuple[str, str, str]]  # (source, edge_type, target)
    total_hops: int
    nodes_visited: int
    edges_traversed: int
    node_depths: dict[str, int] = field(default_factory=dict)
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

        Uses apoc.path.spanningTree to track per-node hop distance,
        which feeds the pivot_depth (PD) metric.
        """
        edge_filter = ""
        if allowed_edge_types:
            sanitized = [t for t in allowed_edge_types if t in VALID_EDGE_TYPES]
            invalid = set(allowed_edge_types) - VALID_EDGE_TYPES
            if invalid:
                logger.warning("Invalid edge types filtered out: %s", invalid)
            if sanitized:
                types_str = "|".join(sanitized)
                edge_filter = f":{types_str}"

        query = f"""
        UNWIND $seed_ids AS seed_id
        MATCH (start {{node_id: seed_id}})
        CALL apoc.path.spanningTree(start, {{
            maxLevel: $max_hops,
            relationshipFilter: '{edge_filter}',
            limit: $max_total
        }})
        YIELD path
        WITH last(nodes(path)) AS node, length(path) AS depth
        RETURN node.node_id AS node_id,
               labels(node)[0] AS node_type,
               node.tenant AS tenant,
               node.sensitivity AS sensitivity,
               node.provenance_score AS provenance_score,
               properties(node) AS props,
               min(depth) AS hop_depth
        ORDER BY hop_depth
        LIMIT $max_total
        """

        expanded = []
        node_depths: dict[str, int] = {}
        with self.driver.session() as session:
            result = session.run(query, {
                "seed_ids": seed_node_ids,
                "max_hops": max_hops,
                "max_total": max_total_nodes,
            })
            for record in result:
                node_id = record["node_id"]
                expanded.append(GraphNode(
                    node_id=node_id,
                    node_type=record["node_type"] or "Unknown",
                    tenant=record["tenant"] or "",
                    sensitivity=record["sensitivity"] or "PUBLIC",
                    provenance_score=record["provenance_score"] or 1.0,
                    properties=dict(record["props"]) if record["props"] else {},
                ))
                node_depths[node_id] = record["hop_depth"]

        # D3: Enforce per-hop branching factor limit.
        # The Cypher query enforces max_total_nodes but not per-hop branching.
        # Post-query pruning ensures no single hop level contributes more than
        # max_branching nodes, aligning with the D3 defense specification.
        if max_branching and max_branching > 0:
            hop_groups: dict[int, list[GraphNode]] = defaultdict(list)
            for node in expanded:
                depth = node_depths.get(node.node_id, 0)
                hop_groups[depth].append(node)

            pruned: list[GraphNode] = []
            for depth in sorted(hop_groups):
                pruned.extend(hop_groups[depth][:max_branching])

            if len(pruned) < len(expanded):
                logger.debug(
                    "Branching factor pruned %d → %d nodes",
                    len(expanded), len(pruned),
                )
            expanded = pruned
            # Rebuild node_depths to only include surviving nodes
            node_depths = {n.node_id: node_depths[n.node_id] for n in expanded}

        return ExpansionResult(
            seed_nodes=seed_node_ids,
            expanded_nodes=expanded,
            traversal_path=[],
            total_hops=max_hops,
            nodes_visited=len(expanded),
            edges_traversed=0,
            node_depths=node_depths,
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
