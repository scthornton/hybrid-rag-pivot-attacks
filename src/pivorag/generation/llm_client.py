"""LLM client abstraction for multi-provider generation evaluation.

Concrete implementations for OpenAI (GPT-4o), Anthropic (Claude Sonnet),
and DeepSeek (V3). Each client handles rate limiting, retries, and cost
tracking through a common interface.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Result from a single LLM generation call."""

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMClient(ABC):
    """Abstract base for LLM API clients."""

    def __init__(
        self,
        model: str,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.temperature = temperature
        self.total_cost_usd = 0.0
        self.total_calls = 0

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider name (e.g. 'openai', 'anthropic', 'deepseek')."""

    @abstractmethod
    def generate(self, prompt: str, system: str = "") -> GenerationResult:
        """Generate a completion for the given prompt."""

    def _retry_with_backoff(self, fn: Any) -> Any:
        """Call fn with exponential backoff on transient errors."""
        for attempt in range(self.max_retries):
            try:
                return fn()
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                delay = self.retry_delay * (2 ** attempt)
                logger.warning(
                    "%s API error (attempt %d/%d): %s — retrying in %.1fs",
                    self.provider, attempt + 1, self.max_retries, e, delay,
                )
                time.sleep(delay)
        return None  # unreachable, but satisfies type checker


class OpenAIClient(LLMClient):
    """OpenAI API client (GPT-4o and compatible models)."""

    # Pricing per 1M tokens (as of 2025)
    INPUT_COST_PER_M = 2.50
    OUTPUT_COST_PER_M = 10.00

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, **kwargs)
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url
        self._client = None

    @property
    def provider(self) -> str:
        return "openai"

    def _get_client(self) -> Any:
        if self._client is None:
            import openai
            self._client = openai.OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    def generate(self, prompt: str, system: str = "") -> GenerationResult:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        start = time.perf_counter()

        def _call() -> Any:
            client = self._get_client()
            return client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=2048,
            )

        response = self._retry_with_backoff(_call)
        elapsed_ms = (time.perf_counter() - start) * 1000

        choice = response.choices[0]
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        cost = (
            prompt_tokens * self.INPUT_COST_PER_M / 1_000_000
            + completion_tokens * self.OUTPUT_COST_PER_M / 1_000_000
        )

        self.total_cost_usd += cost
        self.total_calls += 1

        return GenerationResult(
            text=choice.message.content or "",
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            latency_ms=elapsed_ms,
        )


class AnthropicClient(LLMClient):
    """Anthropic API client (Claude models)."""

    INPUT_COST_PER_M = 3.00
    OUTPUT_COST_PER_M = 15.00

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        api_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, **kwargs)
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = None

    @property
    def provider(self) -> str:
        return "anthropic"

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def generate(self, prompt: str, system: str = "") -> GenerationResult:
        start = time.perf_counter()

        def _call() -> Any:
            client = self._get_client()
            return client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system or "You are a helpful assistant.",
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
            )

        response = self._retry_with_backoff(_call)
        elapsed_ms = (time.perf_counter() - start) * 1000

        text = response.content[0].text if response.content else ""
        usage = response.usage
        prompt_tokens = usage.input_tokens if usage else 0
        completion_tokens = usage.output_tokens if usage else 0
        cost = (
            prompt_tokens * self.INPUT_COST_PER_M / 1_000_000
            + completion_tokens * self.OUTPUT_COST_PER_M / 1_000_000
        )

        self.total_cost_usd += cost
        self.total_calls += 1

        return GenerationResult(
            text=text,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            latency_ms=elapsed_ms,
        )


class DeepSeekClient(LLMClient):
    """DeepSeek API client (V3 via OpenAI-compatible endpoint)."""

    INPUT_COST_PER_M = 0.27
    OUTPUT_COST_PER_M = 1.10

    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, **kwargs)
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self._inner: OpenAIClient | None = None

    @property
    def provider(self) -> str:
        return "deepseek"

    def generate(self, prompt: str, system: str = "") -> GenerationResult:
        if self._inner is None:
            self._inner = OpenAIClient(
                model=self.model,
                api_key=self._api_key,
                base_url="https://api.deepseek.com/v1",
                max_retries=self.max_retries,
                retry_delay=self.retry_delay,
                temperature=self.temperature,
            )

        result = self._inner.generate(prompt, system)
        # Recalculate cost with DeepSeek pricing
        cost = (
            result.prompt_tokens * self.INPUT_COST_PER_M / 1_000_000
            + result.completion_tokens * self.OUTPUT_COST_PER_M / 1_000_000
        )
        result.cost_usd = cost
        result.model = self.model

        self.total_cost_usd += cost
        self.total_calls += 1
        return result
