"""Tests for LLM generation evaluation (clients, metrics, assembly)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from pivorag.eval.generation_metrics import (
    GenerationMetrics,
    entity_contamination_rate,
    factual_contamination_rate,
    generation_refusal_rate,
    information_leakage_score,
)
from pivorag.generation.context_assembler import (
    assemble_prompt,
    format_context_items,
)
from pivorag.generation.llm_client import (
    DeepSeekClient,
    GenerationResult,
    LLMClient,
    OpenAIClient,
)
from pivorag.pipelines.base import RetrievalContext

# ---------------------------------------------------------------------------
# ECR tests
# ---------------------------------------------------------------------------


class TestEntityContaminationRate:
    def test_no_entities(self) -> None:
        assert entity_contamination_rate("Some answer text", []) == 0.0

    def test_exact_match(self) -> None:
        answer = "Maria Chen reviewed the budget with CloudCorp."
        entities = ["Maria Chen", "CloudCorp"]
        assert entity_contamination_rate(answer, entities) == 1.0

    def test_partial_match(self) -> None:
        answer = "The budget was reviewed by Chen."
        entities = ["Maria Chen", "CloudCorp"]
        # "Chen" is a word from "Maria Chen" (len > 2), so partial match
        ecr = entity_contamination_rate(answer, entities)
        assert ecr == 0.5  # 1 of 2 matched

    def test_no_match(self) -> None:
        answer = "The system operates normally."
        entities = ["Maria Chen", "CloudCorp"]
        assert entity_contamination_rate(answer, entities) == 0.0

    def test_case_insensitive(self) -> None:
        answer = "CLOUDCORP provides services."
        entities = ["CloudCorp"]
        assert entity_contamination_rate(answer, entities) == 1.0


# ---------------------------------------------------------------------------
# ILS tests
# ---------------------------------------------------------------------------


class TestInformationLeakageScore:
    def test_no_leaked_chunks(self) -> None:
        answer_emb = np.array([1.0, 0.0, 0.0])
        assert information_leakage_score(answer_emb, []) == 0.0

    def test_identical_embeddings(self) -> None:
        emb = np.array([1.0, 0.0, 0.0])
        ils = information_leakage_score(emb, [emb])
        assert ils == pytest.approx(1.0, abs=0.01)

    def test_orthogonal_embeddings(self) -> None:
        answer_emb = np.array([1.0, 0.0, 0.0])
        chunk_emb = np.array([0.0, 1.0, 0.0])
        ils = information_leakage_score(answer_emb, [chunk_emb])
        assert ils == pytest.approx(0.0, abs=0.01)

    def test_max_across_chunks(self) -> None:
        answer_emb = np.array([1.0, 0.0, 0.0])
        chunk_far = np.array([0.0, 1.0, 0.0])
        chunk_close = np.array([0.9, 0.1, 0.0])
        ils = information_leakage_score(answer_emb, [chunk_far, chunk_close])
        # Should pick the closer chunk
        assert ils > 0.5


# ---------------------------------------------------------------------------
# GRR tests
# ---------------------------------------------------------------------------


class TestGenerationRefusalRate:
    def test_identical_answers_means_refusal(self) -> None:
        answer = "The system operates on Kubernetes."
        assert generation_refusal_rate(answer, answer) == 1.0

    def test_very_different_answers(self) -> None:
        contaminated = "Maria Chen salary is $250,000 with CloudCorp contract details."
        clean = "The system operates on Kubernetes."
        assert generation_refusal_rate(contaminated, clean) == 0.0

    def test_empty_answers(self) -> None:
        assert generation_refusal_rate("", "something") == 0.0
        assert generation_refusal_rate("something", "") == 0.0


# ---------------------------------------------------------------------------
# FCR tests (with mock judge)
# ---------------------------------------------------------------------------


class TestFactualContaminationRate:
    def test_no_leaked_chunks(self) -> None:
        mock_judge = MagicMock(spec=LLMClient)
        fcr = factual_contamination_rate(
            "What is X?", "Answer about X.", "Answer about X.", [],
            mock_judge,
        )
        assert fcr == 0.0

    def test_judge_returns_score(self) -> None:
        mock_judge = MagicMock(spec=LLMClient)
        mock_judge.generate.return_value = GenerationResult(
            text='{"leaked_facts": ["salary info"], "count": 1, '
            '"contamination_score": 0.7}',
            model="test",
        )
        fcr = factual_contamination_rate(
            "What is the salary?",
            "The salary is $250,000.",
            "I don't have that information.",
            ["Employee record: salary $250,000"],
            mock_judge,
        )
        assert fcr == pytest.approx(0.7)

    def test_judge_returns_zero(self) -> None:
        mock_judge = MagicMock(spec=LLMClient)
        mock_judge.generate.return_value = GenerationResult(
            text='{"leaked_facts": [], "count": 0, "contamination_score": 0.0}',
            model="test",
        )
        fcr = factual_contamination_rate(
            "What is X?", "Answer.", "Answer.", ["Some leaked text"],
            mock_judge,
        )
        assert fcr == 0.0


# ---------------------------------------------------------------------------
# Context assembler tests
# ---------------------------------------------------------------------------


class TestContextAssembler:
    def _make_context(
        self,
        chunks: list[dict[str, Any]] | None = None,
        graph_nodes: list[dict[str, Any]] | None = None,
    ) -> RetrievalContext:
        from pivorag.config import SensitivityTier
        return RetrievalContext(
            query="What is Project Alpha?",
            user_id="test_user",
            user_tenant="acme_engineering",
            user_clearance=SensitivityTier.INTERNAL,
            chunks=chunks or [],
            graph_nodes=graph_nodes or [],
        )

    def test_empty_context(self) -> None:
        ctx = self._make_context()
        system, prompt = assemble_prompt(ctx)
        assert "ONLY" in system
        assert "Project Alpha" in prompt

    def test_chunks_included(self) -> None:
        ctx = self._make_context(
            chunks=[{"text": "Alpha uses Kubernetes.", "doc_id": "doc_001"}],
        )
        context_text = format_context_items(ctx)
        assert "Alpha uses Kubernetes" in context_text
        assert "doc_001" in context_text

    def test_graph_nodes_included(self) -> None:
        ctx = self._make_context(
            graph_nodes=[{
                "text": "Kubernetes cluster info.",
                "node_type": "System",
                "node_id": "sys_k8s",
            }],
        )
        context_text = format_context_items(ctx)
        assert "Kubernetes cluster" in context_text
        assert "sys_k8s" in context_text


# ---------------------------------------------------------------------------
# LLM client tests (mock-based, no real API calls)
# ---------------------------------------------------------------------------


class TestGenerationResult:
    def test_dataclass_defaults(self) -> None:
        r = GenerationResult(text="Hello", model="test")
        assert r.prompt_tokens == 0
        assert r.cost_usd == 0.0
        assert r.metadata == {}


class TestLLMClientInterface:
    def test_openai_client_provider(self) -> None:
        client = OpenAIClient(api_key="test")
        assert client.provider == "openai"
        assert client.model == "gpt-5.2"

    def test_deepseek_client_provider(self) -> None:
        client = DeepSeekClient(api_key="test")
        assert client.provider == "deepseek"
        assert client.model == "deepseek-chat"

    def test_cost_tracking_initial(self) -> None:
        client = OpenAIClient(api_key="test")
        assert client.total_cost_usd == 0.0
        assert client.total_calls == 0


# ---------------------------------------------------------------------------
# GenerationMetrics tests
# ---------------------------------------------------------------------------


class TestGenerationMetricsDataclass:
    def test_defaults(self) -> None:
        m = GenerationMetrics()
        assert m.ecr == 0.0
        assert m.ils == 0.0
        assert m.fcr == 0.0
        assert m.grr == 0.0

    def test_to_dict(self) -> None:
        m = GenerationMetrics(ecr=0.5, ils=0.3, fcr=0.1, grr=0.0)
        d = m.to_dict()
        assert d["ecr"] == 0.5
        assert d["fcr"] == 0.1
