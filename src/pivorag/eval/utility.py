"""Utility metrics for measuring answer quality alongside security.

Ensures defenses don't destroy the benefits of hybrid RAG.

Context Recall@k: fraction of ground-truth relevant documents appearing
in the top-k retrieval context. This is a retrieval-only metric that
does not require LLM generation, making it appropriate for measuring
whether defenses degrade retrieval quality.

Context Precision@k: fraction of top-k items that are ground-truth
relevant. Together with recall, these characterize the security-utility
tradeoff of each defense configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    mean_context_recall: float = 0.0
    mean_context_precision: float = 0.0
    recall_per_query: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "accuracy": self.accuracy,
            "citation_support_rate": self.citation_support_rate,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "mean_context_size": self.mean_context_size,
            "total_queries": self.total_queries,
            "mean_context_recall": self.mean_context_recall,
            "mean_context_precision": self.mean_context_precision,
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


def context_recall_at_k(
    retrieved_ids: list[str],
    ground_truth_ids: list[str],
) -> float:
    """Compute Recall@k: fraction of ground-truth items in the retrieved set.

    Recall@k = |retrieved ∩ ground_truth| / |ground_truth|

    Measures whether the pipeline retrieves the documents needed to
    answer the query. A defense that improves security but reduces
    recall is degrading answer quality.
    """
    if not ground_truth_ids:
        return 0.0
    retrieved_set = set(retrieved_ids)
    hits = sum(1 for gt_id in ground_truth_ids if gt_id in retrieved_set)
    return hits / len(ground_truth_ids)


def context_precision_at_k(
    retrieved_ids: list[str],
    ground_truth_ids: list[str],
) -> float:
    """Compute Precision@k: fraction of retrieved items that are ground-truth relevant.

    Precision@k = |retrieved ∩ ground_truth| / |retrieved|

    Measures context noise. High precision means most retrieved items
    are relevant; low precision means the context is diluted with
    irrelevant (but possibly authorized) content.
    """
    if not retrieved_ids:
        return 0.0
    gt_set = set(ground_truth_ids)
    hits = sum(1 for r_id in retrieved_ids if r_id in gt_set)
    return hits / len(retrieved_ids)


def latency_percentiles(
    latencies_ms: list[float],
) -> tuple[float, float]:
    """Compute p50 and p95 latency from a list of query latencies."""
    if not latencies_ms:
        return 0.0, 0.0
    arr = np.array(latencies_ms)
    return float(np.percentile(arr, 50)), float(np.percentile(arr, 95))
