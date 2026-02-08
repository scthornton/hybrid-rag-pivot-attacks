"""Abstract base class for dataset adapters.

Every dataset (synthetic, Enron, EDGAR) implements this interface so the
evaluation pipeline can swap data sources without changing benchmark or
pipeline code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pivorag.config import SensitivityTier
from pivorag.eval.benchmark import BenchmarkQuery
from pivorag.graph.schema import Document


@dataclass
class DatasetStats:
    """Summary statistics for a loaded dataset."""

    total_documents: int = 0
    total_chunks: int = 0
    total_entities: int = 0
    total_relations: int = 0
    tenants: list[str] = field(default_factory=list)
    sensitivity_distribution: dict[str, float] = field(default_factory=dict)
    bridge_entity_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class DatasetAdapter(ABC):
    """Abstract interface for dataset loading and query generation.

    Adapters handle the full lifecycle: download raw data, parse it into
    pivorag Document objects, identify tenants and sensitivity labels,
    discover bridge entities, and generate benchmark queries.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this dataset (e.g. 'synthetic', 'enron', 'edgar')."""

    @abstractmethod
    def load_documents(self) -> list[Document]:
        """Load and return all documents in pivorag schema format.

        For external datasets, this may trigger a download on first call.
        Documents should have tenant, sensitivity, and provenance_score set.
        """

    @abstractmethod
    def get_tenants(self) -> list[str]:
        """Return the list of tenant identifiers for this dataset."""

    @abstractmethod
    def get_sensitivity_distribution(self) -> dict[SensitivityTier, float]:
        """Return the target sensitivity tier distribution.

        Maps each tier to its expected fraction (should sum to 1.0).
        """

    @abstractmethod
    def get_bridge_entities(self) -> list[dict[str, Any]]:
        """Return bridge entities that create cross-tenant graph paths.

        Each entry should have at minimum:
        - 'name': canonical entity name
        - 'type': bridge category (e.g. 'shared_vendor', 'shared_personnel')
        - 'connects': list of tenant names this entity bridges
        """

    @abstractmethod
    def generate_queries(
        self,
        n_benign: int = 100,
        n_adversarial: int = 100,
    ) -> list[BenchmarkQuery]:
        """Generate benchmark queries for this dataset.

        Benign queries ask about content within a single tenant.
        Adversarial queries attempt to reach cross-tenant content
        through shared entities and graph paths.
        """

    def get_collection_name(self) -> str:
        """Return the ChromaDB collection name for this dataset's chunks."""
        return f"{self.name}_chunks"

    def get_stats(self, documents: list[Document] | None = None) -> DatasetStats:
        """Compute summary statistics. Override for dataset-specific stats."""
        if documents is None:
            documents = self.load_documents()

        by_sensitivity: dict[str, int] = {}
        by_tenant: dict[str, int] = {}
        for doc in documents:
            by_sensitivity[doc.sensitivity] = by_sensitivity.get(doc.sensitivity, 0) + 1
            by_tenant[doc.tenant] = by_tenant.get(doc.tenant, 0) + 1

        total = max(len(documents), 1)
        dist = {s: count / total for s, count in by_sensitivity.items()}

        return DatasetStats(
            total_documents=len(documents),
            tenants=list(by_tenant.keys()),
            sensitivity_distribution=dist,
            bridge_entity_count=len(self.get_bridge_entities()),
            metadata={"by_tenant": by_tenant},
        )
