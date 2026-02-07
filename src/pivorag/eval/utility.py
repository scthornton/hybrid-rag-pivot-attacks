"""Utility metrics for measuring answer quality alongside security.

Ensures defenses don't destroy the benefits of hybrid RAG.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class UtilityMetrics:
    """Aggregated utility metrics for a pipeline evaluation run."""

    accuracy: float
    citation_support_rate: float
    p50_latency_ms: float
    p95_latency_ms: float
    mean_context_size: float
    total_queries: int

    def to_dict(self) -> dict:
        return {
            "accuracy": self.accuracy,
            "citation_support_rate": self.citation_support_rate,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "mean_context_size": self.mean_context_size,
            "total_queries": self.total_queries,
        }


def answer_accuracy(
    predictions: list[str],
    ground_truth: list[str],
    mode: str = "fuzzy",
) -> float:
    """Compute accuracy of predicted answers vs ground truth.

    Modes:
    - exact: exact string match
    - fuzzy: case-insensitive substring containment
    """
    if not predictions or not ground_truth:
        return 0.0

    correct = 0
    for pred, truth in zip(predictions, ground_truth, strict=False):
        exact_match = mode == "exact" and pred.strip() == truth.strip()
        fuzzy_match = mode == "fuzzy" and truth.strip().lower() in pred.strip().lower()
        if exact_match or fuzzy_match:
            correct += 1
    return correct / len(predictions)


def citation_support_rate(
    answers: list[str],
    retrieved_chunks: list[list[str]],
) -> float:
    """Measure how often answer claims are supported by retrieved chunks.

    Simple version: check if answer content appears in any retrieved chunk.
    """
    if not answers:
        return 0.0

    supported = 0
    for answer, chunks in zip(answers, retrieved_chunks, strict=False):
        answer_words = set(answer.lower().split())
        for chunk in chunks:
            chunk_words = set(chunk.lower().split())
            overlap = len(answer_words & chunk_words) / max(len(answer_words), 1)
            if overlap > 0.3:
                supported += 1
                break
    return supported / len(answers)


def latency_percentiles(
    latencies_ms: list[float],
) -> tuple[float, float]:
    """Compute p50 and p95 latency from a list of query latencies."""
    if not latencies_ms:
        return 0.0, 0.0
    arr = np.array(latencies_ms)
    return float(np.percentile(arr, 50)), float(np.percentile(arr, 95))
