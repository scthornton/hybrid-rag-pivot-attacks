"""Vector similarity search with optional authorization pre-filtering.

Retrieves top-k chunks from ChromaDB, optionally filtering by
tenant and sensitivity tier before returning results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pivorag.config import SensitivityTier


@dataclass
class RetrievalResult:
    chunk_id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorRetriever:
    """Retrieve chunks from ChromaDB with auth-aware filtering."""

    def __init__(self, index, embedding_model) -> None:
        self.index = index
        self.embedding_model = embedding_model

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        user_tenant: str | None = None,
        user_clearance: SensitivityTier = SensitivityTier.PUBLIC,
        auth_prefilter: bool = True,
    ) -> list[RetrievalResult]:
        """Retrieve top-k chunks for a query, with optional auth filtering."""
        query_embedding = self.embedding_model.embed(query).tolist()

        where_filter = None
        if auth_prefilter and user_tenant:
            # Only retrieve chunks the user is authorized to see
            allowed_tiers = [
                t.value for t in SensitivityTier
                if t.level <= user_clearance.level
            ]
            where_filter = {
                "$and": [
                    {"tenant": user_tenant},
                    {"sensitivity": {"$in": allowed_tiers}},
                ]
            }

        results = self.index.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        retrieved = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                retrieved.append(RetrievalResult(
                    chunk_id=chunk_id,
                    text=results["documents"][0][i] if results["documents"] else "",
                    score=1.0 - results["distances"][0][i],  # cosine distance → similarity
                    metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                ))
        return retrieved
