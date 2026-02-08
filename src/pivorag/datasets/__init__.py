"""Dataset adapters for PivoRAG experiments.

Provides a unified interface for loading documents, tenants, and queries
from different data sources (synthetic, Enron email, SEC EDGAR).
"""

from pivorag.datasets.base import DatasetAdapter, DatasetStats
from pivorag.datasets.enron import EnronEmailAdapter
from pivorag.datasets.sec_edgar import SECEdgarAdapter
from pivorag.datasets.synthetic import SyntheticEnterpriseAdapter

ADAPTERS: dict[str, type[DatasetAdapter]] = {
    "synthetic": SyntheticEnterpriseAdapter,
    "enron": EnronEmailAdapter,
    "edgar": SECEdgarAdapter,
}


def get_adapter(name: str, **kwargs) -> DatasetAdapter:
    """Resolve a dataset name to an adapter instance.

    Args:
        name: One of 'synthetic', 'enron', 'edgar'.
        **kwargs: Forwarded to the adapter constructor.
    """
    cls = ADAPTERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown dataset '{name}'. Choose from: {list(ADAPTERS)}"
        )
    return cls(**kwargs)


__all__ = [
    "ADAPTERS",
    "DatasetAdapter",
    "DatasetStats",
    "EnronEmailAdapter",
    "SECEdgarAdapter",
    "SyntheticEnterpriseAdapter",
    "get_adapter",
]
