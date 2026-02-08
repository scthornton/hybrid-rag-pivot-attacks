"""Per-hop authorization and policy enforcement for graph traversal.

Implements D1 (per-hop authZ), D2 (edge allowlists), and
sensitivity-tier traversal constraints to bound retrieval pivot risk.
"""

from __future__ import annotations

from pivorag.config import SensitivityTier
from pivorag.graph.schema import GraphNode


class TraversalPolicy:
    """Enforce authorization and sensitivity policies during graph expansion."""

    def __init__(
        self,
        user_tenant: str,
        user_clearance: SensitivityTier,
        allowed_tenants: list[str] | None = None,
        deny_sensitivity_escalation: bool = True,
        deny_cross_tenant: bool = True,
    ) -> None:
        self.user_tenant = user_tenant
        self.user_clearance = user_clearance
        self.allowed_tenants = allowed_tenants or [user_tenant]
        self.deny_sensitivity_escalation = deny_sensitivity_escalation
        self.deny_cross_tenant = deny_cross_tenant

    def is_node_authorized(self, node: GraphNode) -> bool:
        """Check if a user is authorized to see this node.

        Entity nodes default to tenant="" (empty string), which means
        they fail the cross-tenant check and are filtered out. This is
        by design: entity nodes are tenant-neutral shared concepts, so
        D1 blocks traversal through them, preventing the chunk→entity→chunk
        pivot path that causes cross-tenant leakage.
        """
        node_tier = SensitivityTier(node.sensitivity)
        if node_tier > self.user_clearance:
            return False

        # GraphNode.tenant is always str (Pydantic enforces this),
        # and bfs_expand coerces Neo4j NULLs to "".
        # Empty tenant ("") will not be in allowed_tenants, so
        # tenant-neutral entity nodes are correctly filtered.
        return not (
            self.deny_cross_tenant
            and node.tenant not in self.allowed_tenants
        )

    def is_hop_allowed(
        self,
        from_node: GraphNode,
        to_node: GraphNode,
        edge_type: str,
    ) -> bool:
        """Check if traversal from one node to another is allowed."""
        if not self.is_node_authorized(to_node):
            return False

        if self.deny_sensitivity_escalation:
            from_tier = SensitivityTier(from_node.sensitivity)
            to_tier = SensitivityTier(to_node.sensitivity)
            if to_tier > from_tier:
                return False

        return True

    def filter_expansion(self, nodes: list[GraphNode]) -> list[GraphNode]:
        """Filter expanded nodes to only those the user is authorized to see."""
        return [n for n in nodes if self.is_node_authorized(n)]


class EdgeAllowlist:
    """D2: Query-class-aware edge type filtering."""

    def __init__(self, allowlist_config: dict) -> None:
        self.config = allowlist_config

    def get_allowed_edges(self, query_class: str) -> list[str]:
        """Return allowed edge types for a given query class."""
        class_config = self.config.get(query_class, self.config.get("general", {}))
        return class_config.get("allowed", [])

    def get_max_hops(self, query_class: str) -> int | None:
        """Return max hops for a given query class, if specified."""
        class_config = self.config.get(query_class, {})
        return class_config.get("max_hops")


class TraversalBudget:
    """D3: Hard caps on traversal scope."""

    def __init__(
        self,
        max_hops: int = 2,
        max_branching_factor: int = 8,
        max_total_nodes: int = 40,
        timeout_ms: int = 2000,
    ) -> None:
        self.max_hops = max_hops
        self.max_branching_factor = max_branching_factor
        self.max_total_nodes = max_total_nodes
        self.timeout_ms = timeout_ms
        self._nodes_visited = 0

    def can_continue(self, current_hop: int, nodes_at_hop: int) -> bool:
        """Check if traversal should continue at this hop."""
        if current_hop >= self.max_hops:
            return False
        if nodes_at_hop >= self.max_branching_factor:
            return False
        return self._nodes_visited < self.max_total_nodes

    def record_visit(self, count: int = 1) -> None:
        self._nodes_visited += count

    def reset(self) -> None:
        self._nodes_visited = 0
