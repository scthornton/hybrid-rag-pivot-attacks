"""P3-P8: Hybrid RAG pipeline with configurable defenses.

The core pipeline: vector seed → entity linking → graph expansion → merge.
Defense toggles (D1-D5) are driven by the PipelineConfig.
This is where retrieval pivot risk is measured and mitigated.
"""

from __future__ import annotations

import time
from typing import Any

from pivorag.config import PipelineConfig, SensitivityTier
from pivorag.graph.expand import GraphExpander
from pivorag.graph.policy import EdgeAllowlist, TraversalPolicy
from pivorag.pipelines.base import BasePipeline, RetrievalContext
from pivorag.vector.retrieve import VectorRetriever


class HybridPipeline(BasePipeline):
    """Hybrid vector→graph pipeline with configurable defense suite."""

    def __init__(
        self,
        config: PipelineConfig,
        vector_retriever: VectorRetriever,
        graph_expander: GraphExpander,
        entity_linker=None,
    ) -> None:
        super().__init__(config)
        self.vector_retriever = vector_retriever
        self.graph_expander = graph_expander
        self.entity_linker = entity_linker

    def retrieve(
        self,
        query: str,
        user_id: str,
        user_tenant: str,
        user_clearance: SensitivityTier,
    ) -> RetrievalContext:
        start = time.perf_counter()
        traversal_log: list[dict[str, Any]] = []

        # Step 1: Vector retrieval (seed selection)
        vector_results = self.vector_retriever.retrieve(
            query=query,
            top_k=self.config.vector.top_k,
            user_tenant=user_tenant,
            user_clearance=user_clearance,
            auth_prefilter=self.config.vector.auth_prefilter,
        )
        seed_chunk_ids = [r.chunk_id for r in vector_results]
        traversal_log.append({
            "step": "vector_retrieval",
            "seeds": len(seed_chunk_ids),
        })

        # Step 2: Entity linking (map chunks → graph nodes)
        seed_node_ids = self._link_entities(vector_results)
        traversal_log.append({
            "step": "entity_linking",
            "linked_nodes": len(seed_node_ids),
        })

        # Step 3: Graph expansion with defense configuration
        graph_nodes = []
        node_depths: dict[str, int] = {}
        if self.config.graph.enabled and seed_node_ids:
            graph_nodes, node_depths = self._expand_with_defenses(
                seed_node_ids=seed_node_ids,
                user_tenant=user_tenant,
                user_clearance=user_clearance,
            )
            traversal_log.append({
                "step": "graph_expansion",
                "expanded_nodes": len(graph_nodes),
                "node_depths": node_depths,
            })

        # Step 4: Merge vector + graph results
        chunks = [
            {
                "chunk_id": r.chunk_id,
                "text": r.text,
                "score": r.score,
                **r.metadata,
            }
            for r in vector_results
        ]

        # Step 5: Apply merge-time filter (D5) if enabled
        if self.config.defenses.merge_filter.get("enabled", False):
            graph_nodes = self._apply_merge_filter(graph_nodes, user_clearance)
            traversal_log.append({
                "step": "merge_filter",
                "nodes_after_filter": len(graph_nodes),
            })

        elapsed_ms = (time.perf_counter() - start) * 1000

        return RetrievalContext(
            query=query,
            user_id=user_id,
            user_tenant=user_tenant,
            user_clearance=user_clearance,
            chunks=chunks,
            graph_nodes=[
                {
                    "node_id": n.node_id,
                    "node_type": n.node_type,
                    "tenant": n.tenant,
                    "sensitivity": n.sensitivity,
                    "provenance_score": n.provenance_score,
                    "hop_depth": node_depths.get(n.node_id, -1),
                    **n.properties,
                }
                for n in graph_nodes
            ] if graph_nodes else [],
            seed_chunk_ids=seed_chunk_ids,
            expanded_node_ids=[n.node_id for n in graph_nodes] if graph_nodes else [],
            traversal_log=traversal_log,
            latency_ms=elapsed_ms,
            pipeline_variant=self.variant,
        )

    def _link_entities(self, vector_results) -> list[str]:
        """Map vector-retrieved chunks to graph entity node IDs."""
        if self.entity_linker is None:
            # Fallback: use chunk_id as seed (assumes chunk nodes exist in graph)
            return [r.chunk_id for r in vector_results]
        # Use entity linker to find graph nodes mentioned in chunks
        node_ids = []
        for result in vector_results:
            linked = self.entity_linker.link(result.text, result.chunk_id)
            node_ids.extend([e.entity_id for e in linked])
        return list(set(node_ids))

    def _expand_with_defenses(
        self,
        seed_node_ids: list[str],
        user_tenant: str,
        user_clearance: SensitivityTier,
    ) -> tuple[list, dict[str, int]]:
        """Run graph expansion with defense stack applied.

        Returns (expanded_nodes, node_depths) where node_depths maps
        node_id → minimum hop distance from the nearest seed node.
        """
        # Determine expansion parameters based on defense config
        max_hops = self.config.graph.max_hops
        max_branching = self.config.graph.max_branching_factor
        max_total = self.config.graph.max_total_nodes
        allowed_edges = self.config.graph.edge_types

        # D3: Budget overrides
        budget_cfg = self.config.defenses.budgets
        if budget_cfg.get("enabled"):
            max_hops = min(max_hops, budget_cfg.get("max_hops", max_hops))
            budget_branch = budget_cfg.get("max_branching_factor", max_branching)
            max_branching = min(max_branching, budget_branch)
            max_total = min(max_total, budget_cfg.get("max_total_nodes", max_total))

        # D2: Edge allowlist overrides
        allowlist_cfg = self.config.defenses.edge_allowlist
        if allowlist_cfg.get("enabled"):
            allowlist = EdgeAllowlist(allowlist_cfg.get("query_classes", {}))
            allowed_edges = allowlist.get_allowed_edges("general")

        # Execute expansion
        result = self.graph_expander.bfs_expand(
            seed_node_ids=seed_node_ids,
            max_hops=max_hops,
            max_branching=max_branching,
            max_total_nodes=max_total,
            allowed_edge_types=allowed_edges,
        )

        nodes = result.expanded_nodes
        node_depths = result.node_depths

        # D1: Per-hop authorization filter
        authz_cfg = self.config.defenses.per_hop_authz
        if authz_cfg.get("enabled"):
            policy = TraversalPolicy(
                user_tenant=user_tenant,
                user_clearance=user_clearance,
                deny_sensitivity_escalation=authz_cfg.get("deny_sensitivity_escalation", True),
                deny_cross_tenant=authz_cfg.get("deny_cross_tenant", True),
            )
            nodes = policy.filter_expansion(nodes)

        # D4: Trust-weighted filtering
        trust_cfg = self.config.defenses.trust_weighting
        if trust_cfg.get("enabled"):
            min_trust = trust_cfg.get("min_trust_score", 0.6)
            nodes = [n for n in nodes if n.provenance_score >= min_trust]

        return nodes, node_depths

    def _apply_merge_filter(self, graph_nodes, user_clearance: SensitivityTier) -> list:
        """D5: Post-merge policy filter."""
        filtered = []
        for node in graph_nodes:
            node_tier = SensitivityTier(node.sensitivity)
            if node_tier <= user_clearance:
                filtered.append(node)
        return filtered
