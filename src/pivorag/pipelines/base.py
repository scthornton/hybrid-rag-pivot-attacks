"""Abstract base class for all RAG pipeline variants.

Defines the interface that P1 (vector-only), P2 (graph-only),
and P3-P8 (hybrid + defense variants) all implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pivorag.config import PipelineConfig, SensitivityTier


@dataclass
class RetrievalContext:
    """Complete retrieval context returned by a pipeline."""

    query: str
    user_id: str
    user_tenant: str
    user_clearance: SensitivityTier
    chunks: list[dict[str, Any]] = field(default_factory=list)
    graph_nodes: list[dict[str, Any]] = field(default_factory=list)
    seed_chunk_ids: list[str] = field(default_factory=list)
    expanded_node_ids: list[str] = field(default_factory=list)
    traversal_log: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    pipeline_variant: str = ""

    @property
    def all_item_ids(self) -> list[str]:
        return self.seed_chunk_ids + self.expanded_node_ids

    @property
    def sensitive_items(self) -> list[dict[str, Any]]:
        """Return items with sensitivity above PUBLIC."""
        sensitive = []
        for item in self.chunks + self.graph_nodes:
            tier = item.get("sensitivity", "PUBLIC")
            if SensitivityTier(tier) > SensitivityTier.PUBLIC:
                sensitive.append(item)
        return sensitive


class BasePipeline(ABC):
    """Abstract base for all RAG pipeline variants."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    @abstractmethod
    def retrieve(
        self,
        query: str,
        user_id: str,
        user_tenant: str,
        user_clearance: SensitivityTier,
    ) -> RetrievalContext:
        """Execute the full retrieval pipeline and return context."""

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def variant(self) -> str:
        return self.config.variant
