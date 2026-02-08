"""Context assembler: formats RetrievalContext into LLM prompts.

Takes the retrieval output from a pipeline and assembles it into
a standard RAG prompt suitable for any LLM provider.
"""

from __future__ import annotations

from pivorag.pipelines.base import RetrievalContext

_RAG_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question based ONLY on "
    "the provided context. If the context does not contain enough information "
    "to answer the question, say so clearly. Do not use any outside knowledge."
)

_CONTEXT_TEMPLATE = (
    "Context:\n"
    "---\n"
    "{context_text}\n"
    "---\n\n"
    "Question: {query}\n\n"
    "Answer:"
)


def format_context_items(ctx: RetrievalContext) -> str:
    """Extract text from chunks and graph nodes into a single context string."""
    parts: list[str] = []

    for i, chunk in enumerate(ctx.chunks, 1):
        text = chunk.get("text", "")
        source = chunk.get("doc_id", "unknown")
        parts.append(f"[Document {i} — {source}]\n{text}")

    for j, node in enumerate(ctx.graph_nodes, len(ctx.chunks) + 1):
        text = node.get("text", node.get("properties", {}).get("text", ""))
        node_type = node.get("node_type", "unknown")
        node_id = node.get("node_id", "unknown")
        if text:
            parts.append(f"[Graph Node {j} — {node_type}:{node_id}]\n{text}")

    return "\n\n".join(parts)


def assemble_prompt(ctx: RetrievalContext) -> tuple[str, str]:
    """Build a (system_prompt, user_prompt) pair from retrieval context.

    Returns a tuple of (system, user) strings suitable for passing to
    any LLMClient.generate() call.
    """
    context_text = format_context_items(ctx)
    user_prompt = _CONTEXT_TEMPLATE.format(
        context_text=context_text,
        query=ctx.query,
    )
    return _RAG_SYSTEM_PROMPT, user_prompt
