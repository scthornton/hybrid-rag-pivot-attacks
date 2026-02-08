"""Dataset adapters for PivoRAG experiments.

Provides a unified interface for loading documents, tenants, and queries
from different data sources (synthetic, Enron email, SEC EDGAR).
"""

from pivorag.datasets.base import DatasetAdapter, DatasetStats
from pivorag.datasets.enron import EnronEmailAdapter
from pivorag.datasets.sec_edgar import SECEdgarAdapter
from pivorag.datasets.synthetic import SyntheticEnterpriseAdapter

__all__ = [
    "DatasetAdapter",
    "DatasetStats",
    "EnronEmailAdapter",
    "SECEdgarAdapter",
    "SyntheticEnterpriseAdapter",
]
