"""LLM generation layer for end-to-end RAG evaluation.

Provides LLM client abstractions, context assembly, and generation
metrics (ECR, ILS, FCR, GRR) to measure how leaked retrieval context
contaminates generated answers.
"""

from pivorag.generation.llm_client import AnthropicClient, DeepSeekClient, LLMClient, OpenAIClient

__all__ = [
    "AnthropicClient",
    "DeepSeekClient",
    "LLMClient",
    "OpenAIClient",
]
