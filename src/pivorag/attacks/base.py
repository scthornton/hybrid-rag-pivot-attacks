"""Base class for all attack implementations.

Defines the attack interface: inject content into the corpus,
then measure retrieval behavior via the evaluation framework.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InjectionPayload:
    """A single unit of injected content."""

    payload_id: str
    text: str
    entities: list[str] = field(default_factory=list)
    target_queries: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AttackResult:
    """Result of executing an attack."""

    attack_name: str
    payloads_injected: int
    total_tokens_injected: int
    target_queries: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAttack(ABC):
    """Abstract base for all retrieval pivot attacks."""

    def __init__(self, injection_budget: int = 10) -> None:
        self.injection_budget = injection_budget

    @abstractmethod
    def generate_payloads(
        self,
        target_queries: list[str],
        corpus_stats: dict[str, Any] | None = None,
    ) -> list[InjectionPayload]:
        """Generate attack payloads within the injection budget."""

    @abstractmethod
    def inject(
        self,
        payloads: list[InjectionPayload],
        vector_index,
        graph_builder,
    ) -> AttackResult:
        """Inject payloads into the vector store and/or graph."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable attack name."""
