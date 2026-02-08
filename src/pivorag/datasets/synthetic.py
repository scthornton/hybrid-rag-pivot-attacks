"""Synthetic enterprise dataset adapter.

Wraps the existing make_synth_data.py generators behind the DatasetAdapter
interface so the synthetic corpus can be used interchangeably with Enron
and EDGAR in the experiment pipeline.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import yaml
from faker import Faker
from scripts.generate_queries import (
    generate_adversarial_queries,
    generate_benign_queries,
)
from scripts.make_synth_data import (
    DOMAIN_TO_TENANT,
    generate_dataset,
    get_bridge_entities,
)

from pivorag.config import SensitivityTier
from pivorag.datasets.base import DatasetAdapter
from pivorag.eval.benchmark import BenchmarkQuery
from pivorag.graph.schema import Document

_DEFAULT_TIERS = [
    {"name": "PUBLIC", "fraction": 0.40},
    {"name": "INTERNAL", "fraction": 0.30},
    {"name": "CONFIDENTIAL", "fraction": 0.20},
    {"name": "RESTRICTED", "fraction": 0.10},
]


class SyntheticEnterpriseAdapter(DatasetAdapter):
    """Adapter for the synthetic multi-tenant enterprise corpus.

    Can be configured via a YAML config file (matching the existing
    configs/datasets/synthetic_enterprise.yaml format) or directly
    with constructor arguments.
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        total_documents: int = 1000,
        bridge_count: int | None = None,
        seed: int = 42,
    ) -> None:
        self._config_path = config_path
        self._total_documents = total_documents
        self._bridge_count = bridge_count
        self._seed = seed
        self._cfg: dict[str, Any] | None = None

        if config_path is not None:
            with Path(config_path).open() as f:
                self._cfg = yaml.safe_load(f)

    @property
    def name(self) -> str:
        return "synthetic"

    def _build_cfg(self) -> dict[str, Any]:
        """Build a config dict compatible with generate_dataset()."""
        if self._cfg is not None:
            return self._cfg

        return {
            "dataset": {"name": "synthetic_enterprise"},
            "scale": {
                "preset": "custom",
                "presets": {"custom": {"total_documents": self._total_documents}},
            },
            "sensitivity_tiers": list(_DEFAULT_TIERS),
        }

    def load_documents(self) -> list[Document]:
        random.seed(self._seed)
        Faker.seed(self._seed)

        cfg = self._build_cfg()
        raw_docs = generate_dataset(cfg, bridge_count=self._bridge_count)

        documents = []
        for raw in raw_docs:
            doc = Document(
                doc_id=raw["doc_id"],
                title=raw["title"],
                text=raw["text"],
                source=raw.get("source", ""),
                tenant=raw["tenant"],
                sensitivity=raw["sensitivity"],
                provenance_score=raw.get("provenance_score", 1.0),
            )
            documents.append(doc)
        return documents

    def get_tenants(self) -> list[str]:
        return list(DOMAIN_TO_TENANT.values())

    def get_sensitivity_distribution(self) -> dict[SensitivityTier, float]:
        tiers = _DEFAULT_TIERS
        if self._cfg:
            tiers = self._cfg.get("sensitivity_tiers", _DEFAULT_TIERS)
        return {SensitivityTier(t["name"]): t["fraction"] for t in tiers}

    def get_bridge_entities(self) -> list[dict[str, Any]]:
        return get_bridge_entities(self._bridge_count)

    def generate_queries(
        self,
        n_benign: int = 100,
        n_adversarial: int = 100,
    ) -> list[BenchmarkQuery]:
        benign_raw = generate_benign_queries(n_benign, self._seed)
        adv_raw = generate_adversarial_queries(n_adversarial, self._seed)

        queries = []
        for raw in benign_raw:
            queries.append(BenchmarkQuery(
                query=raw["text"],
                query_type="benign",
                user_tenant=raw["tenant"],
                user_clearance=raw["user_clearance"],
            ))
        for raw in adv_raw:
            queries.append(BenchmarkQuery(
                query=raw["text"],
                query_type="adversarial",
                user_tenant=raw["tenant"],
                user_clearance=raw["user_clearance"],
            ))
        return queries
