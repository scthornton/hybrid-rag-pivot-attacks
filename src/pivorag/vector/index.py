"""ChromaDB collection management for vector indexing.

Handles collection creation, chunk insertion with metadata,
and collection lifecycle for experiment runs.
"""

from __future__ import annotations

from typing import Any

import chromadb
from chromadb.config import Settings


class VectorIndex:
    """Manage ChromaDB collections for pivorag experiments."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        collection_name: str = "pivorag_chunks",
    ) -> None:
        self.collection_name = collection_name
        self.client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = None

    @property
    def collection(self) -> chromadb.Collection:
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add_chunks(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Add chunks with embeddings and metadata to the collection."""
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def reset(self) -> None:
        """Delete and recreate the collection (for clean experiment runs)."""
        self.client.delete_collection(self.collection_name)
        self._collection = None

    def count(self) -> int:
        return self.collection.count()
