"""Generation benchmark runner: end-to-end evaluation of leaked context impact.

For each query:
1. Retrieve with P3 (undefended) and P4 (defended)
2. Identify leaked items = P3 context - P4 context
3. Generate answers with each LLM on both contexts
4. Compute ECR, ILS, FCR, GRR per (query, LLM) pair
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pivorag.eval.benchmark import BenchmarkQuery
from pivorag.eval.generation_metrics import (
    entity_contamination_rate,
    factual_contamination_rate,
    generation_refusal_rate,
    information_leakage_score,
)
from pivorag.generation.context_assembler import assemble_prompt
from pivorag.generation.llm_client import LLMClient
from pivorag.pipelines.base import BasePipeline, RetrievalContext

logger = logging.getLogger(__name__)


@dataclass
class GenerationBenchmarkResult:
    """Results from a generation benchmark run."""

    llm_provider: str
    llm_model: str
    dataset: str
    total_queries: int
    mean_ecr: float
    mean_ils: float
    mean_fcr: float
    mean_grr: float
    total_cost_usd: float
    per_query: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "dataset": self.dataset,
            "total_queries": self.total_queries,
            "mean_ecr": self.mean_ecr,
            "mean_ils": self.mean_ils,
            "mean_fcr": self.mean_fcr,
            "mean_grr": self.mean_grr,
            "total_cost_usd": self.total_cost_usd,
            "per_query": self.per_query,
        }


def _extract_leaked_items(
    contaminated_ctx: RetrievalContext,
    clean_ctx: RetrievalContext,
) -> tuple[list[str], list[str]]:
    """Identify items in contaminated context that aren't in clean context.

    Returns (leaked_entity_names, leaked_chunk_texts).
    """
    clean_ids = set(clean_ctx.all_item_ids)

    leaked_entities: list[str] = []
    leaked_texts: list[str] = []

    # Check graph nodes
    for node in contaminated_ctx.graph_nodes:
        node_id = node.get("node_id", "")
        if node_id not in clean_ids:
            # Extract entity name or text
            name = node.get("properties", {}).get("canonical_name", "")
            if name:
                leaked_entities.append(name)
            text = node.get("text", node.get("properties", {}).get("text", ""))
            if text:
                leaked_texts.append(text)

    # Check chunks
    for chunk in contaminated_ctx.chunks:
        chunk_id = chunk.get("chunk_id", chunk.get("node_id", ""))
        if chunk_id not in clean_ids:
            text = chunk.get("text", "")
            if text:
                leaked_texts.append(text)
            # Extract any entity names from chunk metadata
            for ent in chunk.get("entities_mentioned", []):
                leaked_entities.append(ent)

    return leaked_entities, leaked_texts


class GenerationBenchmarkRunner:
    """Run generation benchmarks across LLM providers."""

    def __init__(
        self,
        output_dir: str | Path = "results",
        budget_usd: float = 50.0,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.budget_usd = budget_usd

    def run(
        self,
        contaminated_pipeline: BasePipeline,
        clean_pipeline: BasePipeline,
        queries: list[BenchmarkQuery],
        llm_client: LLMClient,
        judge_client: LLMClient | None = None,
        embedding_model: Any = None,
        dataset_name: str = "unknown",
    ) -> GenerationBenchmarkResult:
        """Run generation evaluation for a single LLM across all queries.

        Parameters
        ----------
        contaminated_pipeline : BasePipeline
            The undefended pipeline (P3) that leaks cross-tenant context.
        clean_pipeline : BasePipeline
            The defended pipeline (P4+) that filters unauthorized context.
        queries : list[BenchmarkQuery]
            Benchmark queries to evaluate.
        llm_client : LLMClient
            The LLM to generate answers with.
        judge_client : LLMClient | None
            LLM to use as FCR judge (GPT-4o recommended). If None, FCR=0.
        embedding_model : Any
            EmbeddingModel instance for ILS computation. If None, ILS=0.
        dataset_name : str
            Dataset identifier for result labeling.
        """
        from pivorag.config import SensitivityTier

        ecr_values: list[float] = []
        ils_values: list[float] = []
        fcr_values: list[float] = []
        grr_values: list[float] = []
        per_query: list[dict[str, Any]] = []

        for i, q in enumerate(queries):
            # Budget check
            if llm_client.total_cost_usd >= self.budget_usd:
                logger.warning(
                    "Budget limit reached ($%.2f / $%.2f) after %d queries",
                    llm_client.total_cost_usd, self.budget_usd, i,
                )
                break

            logger.info("Query %d/%d: %s", i + 1, len(queries), q.query[:80])

            clearance = SensitivityTier(q.user_clearance)

            # Retrieve with both pipelines
            contaminated_ctx = contaminated_pipeline.retrieve(
                query=q.query, user_id=q.user_id,
                user_tenant=q.user_tenant, user_clearance=clearance,
            )
            clean_ctx = clean_pipeline.retrieve(
                query=q.query, user_id=q.user_id,
                user_tenant=q.user_tenant, user_clearance=clearance,
            )

            # Identify leaked items
            leaked_entities, leaked_texts = _extract_leaked_items(
                contaminated_ctx, clean_ctx,
            )

            # Generate answers
            contam_sys, contam_prompt = assemble_prompt(contaminated_ctx)
            clean_sys, clean_prompt = assemble_prompt(clean_ctx)

            contam_result = llm_client.generate(contam_prompt, contam_sys)
            clean_result = llm_client.generate(clean_prompt, clean_sys)

            # Compute ECR
            ecr = entity_contamination_rate(contam_result.text, leaked_entities)
            ecr_values.append(ecr)

            # Compute ILS
            ils = 0.0
            if embedding_model and leaked_texts:
                answer_emb = embedding_model.embed(contam_result.text)
                chunk_embs = [embedding_model.embed(t) for t in leaked_texts[:10]]
                ils = information_leakage_score(answer_emb, chunk_embs)
            ils_values.append(ils)

            # Compute FCR
            fcr = 0.0
            if judge_client and leaked_texts:
                fcr = factual_contamination_rate(
                    q.query, contam_result.text, clean_result.text,
                    leaked_texts, judge_client,
                )
            fcr_values.append(fcr)

            # Compute GRR
            grr = generation_refusal_rate(contam_result.text, clean_result.text)
            grr_values.append(grr)

            per_query.append({
                "query": q.query,
                "query_type": q.query_type,
                "ecr": ecr,
                "ils": ils,
                "fcr": fcr,
                "grr": grr,
                "leaked_entity_count": len(leaked_entities),
                "leaked_chunk_count": len(leaked_texts),
                "contaminated_answer_len": len(contam_result.text),
                "clean_answer_len": len(clean_result.text),
            })

        n = max(len(ecr_values), 1)
        return GenerationBenchmarkResult(
            llm_provider=llm_client.provider,
            llm_model=llm_client.model,
            dataset=dataset_name,
            total_queries=len(ecr_values),
            mean_ecr=sum(ecr_values) / n,
            mean_ils=sum(ils_values) / n,
            mean_fcr=sum(fcr_values) / n,
            mean_grr=sum(grr_values) / n,
            total_cost_usd=llm_client.total_cost_usd,
            per_query=per_query,
        )

    def save_results(
        self,
        result: GenerationBenchmarkResult,
        label: str = "",
    ) -> Path:
        """Save generation benchmark results to JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"generation_{result.llm_provider}_{result.dataset}_{label}_{timestamp}.json"
        path = self.output_dir / "tables" / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(json.dumps(result.to_dict(), indent=2))
        logger.info("Saved generation results to %s", path)
        return path
