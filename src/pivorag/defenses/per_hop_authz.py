"""D1: Policy-Checked Expansion (Per-Hop Authorization).

Reapplies authorization checks on every hop and returned node
during graph expansion — not just on initial vector retrieval.
This is the most direct defense against retrieval pivoting.
"""

from __future__ import annotations

from pivorag.config import SensitivityTier
from pivorag.graph.policy import TraversalPolicy
from pivorag.graph.schema import GraphNode


class PerHopAuthzDefense:
    """Apply per-hop authorization during graph expansion."""

    def __init__(
        self,
        user_tenant: str,
        user_clearance: SensitivityTier,
        allowed_tenants: list[str] | None = None,
        deny_sensitivity_escalation: bool = True,
        deny_cross_tenant: bool = True,
    ) -> None:
        self.policy = TraversalPolicy(
            user_tenant=user_tenant,
            user_clearance=user_clearance,
            allowed_tenants=allowed_tenants,
            deny_sensitivity_escalation=deny_sensitivity_escalation,
            deny_cross_tenant=deny_cross_tenant,
        )

    def filter(self, nodes: list[GraphNode]) -> list[GraphNode]:
        """Remove unauthorized nodes from expansion results."""
        return self.policy.filter_expansion(nodes)

    def check_hop(
        self,
        from_node: GraphNode,
        to_node: GraphNode,
        edge_type: str,
    ) -> bool:
        """Check if a specific hop is allowed."""
        return self.policy.is_hop_allowed(from_node, to_node, edge_type)
