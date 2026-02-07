"""P2: Graph-only retrieval pipeline.

Extracts entities from the query, looks them up in the graph,
and expands neighborhoods without any vector retrieval step.
"""

from __future__ import annotations

import time

from pivorag.config import PipelineConfig, SensitivityTier
from pivorag.graph.expand import GraphExpander
from pivorag.pipelines.base import BasePipeline, RetrievalContext


class GraphOnlyPipeline(BasePipeline):
    """P2: Pure graph-based retrieval."""

    def __init__(
        self,
        config: PipelineConfig,
        expander: GraphExpander,
        entity_extractor=None,
    ) -> None:
        super().__init__(config)
        self.expander = expander
        self.entity_extractor = entity_extractor

    def retrieve(
        self,
        query: str,
        user_id: str,
        user_tenant: str,
        user_clearance: SensitivityTier,
    ) -> RetrievalContext:
        start = time.perf_counter()

        # Extract entities from query to use as seed nodes
        seed_ids = []
        if self.entity_extractor:
            entities = self.entity_extractor.extract(query, chunk_id="query")
            seed_ids = [e.entity_id for e in entities]

        # Expand from entity seeds
        expansion = self.expander.bfs_expand(
            seed_node_ids=seed_ids,
            max_hops=self.config.graph.max_hops,
            max_branching=self.config.graph.max_branching_factor,
            max_total_nodes=self.config.graph.max_total_nodes,
            allowed_edge_types=self.config.graph.edge_types,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        graph_nodes = [
            {
                "node_id": n.node_id,
                "node_type": n.node_type,
                "tenant": n.tenant,
                "sensitivity": n.sensitivity,
                "provenance_score": n.provenance_score,
                **n.properties,
            }
            for n in expansion.expanded_nodes
        ]

        return RetrievalContext(
            query=query,
            user_id=user_id,
            user_tenant=user_tenant,
            user_clearance=user_clearance,
            graph_nodes=graph_nodes,
            expanded_node_ids=[n.node_id for n in expansion.expanded_nodes],
            latency_ms=elapsed_ms,
            pipeline_variant=self.variant,
        )
