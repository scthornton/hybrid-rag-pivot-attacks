"""Document chunking with configurable token-based sizing.

Splits documents into 200-500 token chunks with overlap,
preserving metadata (doc_id, tenant, sensitivity) on each chunk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import tiktoken

if TYPE_CHECKING:
    from pivorag.graph.schema import Document


@dataclass
class ChunkResult:
    chunk_id: str
    doc_id: str
    text: str
    token_count: int
    tenant: str
    sensitivity: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)


class TokenChunker:
    """Split documents into token-counted chunks with overlap."""

    def __init__(
        self,
        target_size: int = 300,
        overlap: int = 50,
        encoding_name: str = "cl100k_base",
    ) -> None:
        self.target_size = target_size
        self.overlap = overlap
        self.encoder = tiktoken.get_encoding(encoding_name)

    def chunk_document(self, doc: Document) -> list[ChunkResult]:
        """Split a document into overlapping token chunks."""
        tokens = self.encoder.encode(doc.text)
        chunks: list[ChunkResult] = []
        start = 0
        idx = 0

        while start < len(tokens):
            end = min(start + self.target_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.encoder.decode(chunk_tokens)

            chunks.append(ChunkResult(
                chunk_id=f"{doc.doc_id}_chunk_{idx:04d}",
                doc_id=doc.doc_id,
                text=chunk_text,
                token_count=len(chunk_tokens),
                tenant=doc.tenant,
                sensitivity=doc.sensitivity,
                chunk_index=idx,
            ))

            start += self.target_size - self.overlap
            idx += 1

        return chunks
