"""D3: Budgeted Traversal.

Hard caps on graph expansion scope: max hops, max branching factor,
max total nodes visited, and timeout limits.
"""

from __future__ import annotations

from pivorag.graph.policy import TraversalBudget


class BudgetDefense:
    """Enforce hard traversal budget caps."""

    def __init__(
        self,
        max_hops: int = 2,
        max_branching_factor: int = 8,
        max_total_nodes: int = 40,
        timeout_ms: int = 2000,
    ) -> None:
        self.budget = TraversalBudget(
            max_hops=max_hops,
            max_branching_factor=max_branching_factor,
            max_total_nodes=max_total_nodes,
            timeout_ms=timeout_ms,
        )

    def get_constrained_params(
        self,
        requested_hops: int,
        requested_branching: int,
        requested_total: int,
    ) -> tuple[int, int, int]:
        """Return the minimum of requested and budget-allowed parameters."""
        return (
            min(requested_hops, self.budget.max_hops),
            min(requested_branching, self.budget.max_branching_factor),
            min(requested_total, self.budget.max_total_nodes),
        )
