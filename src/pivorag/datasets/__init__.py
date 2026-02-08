"""Dataset adapters for PivoRAG experiments.

Provides a unified interface for loading documents, tenants, and queries
from different data sources (synthetic, Enron email, SEC EDGAR).

Adapters are lazy-imported to avoid pulling in script-level dependencies
(e.g. SyntheticEnterpriseAdapter depends on scripts/ being on sys.path).
"""

from __future__ import annotations

from pivorag.datasets.base import DatasetAdapter, DatasetStats


def get_adapter(name: str, **kwargs) -> DatasetAdapter:
    """Resolve a dataset name to an adapter instance.

    Args:
        name: One of 'synthetic', 'enron', 'edgar'.
        **kwargs: Forwarded to the adapter constructor.
    """
    if name == "synthetic":
        from pivorag.datasets.synthetic import SyntheticEnterpriseAdapter

        return SyntheticEnterpriseAdapter(**kwargs)
    if name == "enron":
        from pivorag.datasets.enron import EnronEmailAdapter

        return EnronEmailAdapter(**kwargs)
    if name == "edgar":
        from pivorag.datasets.sec_edgar import SECEdgarAdapter

        return SECEdgarAdapter(**kwargs)
    msg = f"Unknown dataset '{name}'. Choose from: synthetic, enron, edgar"
    raise ValueError(msg)


__all__ = [
    "DatasetAdapter",
    "DatasetStats",
    "get_adapter",
]
