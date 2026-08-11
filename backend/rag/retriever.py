"""Retrieval from Qdrant.  (M2)

Always returns citations alongside passages. An agent that cannot attribute a
claim should not be making it — and the Manager tier's whole value over the
Front Desk is that it can point at a source.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TOP_K = 5
MIN_SCORE = 0.35  # TODO(M2+): tune against the real corpus; this is a guess


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def _qdrant_url() -> str:
    return os.environ.get("QDRANT_URL", "http://localhost:6333")


def _qdrant_api_key() -> str | None:
    return os.environ.get("QDRANT_API_KEY") or None


@dataclass
class RetrievedPassage:
    """A search hit with everything needed to cite it."""

    text: str
    source: str
    location: str
    score: float

    def citation(self) -> str:
        """Human-readable, e.g. 'handbook.pdf, p.14' or a page URL."""
        is_url = self.source.startswith(("http://", "https://"))
        name = self.source if is_url else Path(self.source).name
        if self.location and self.location != "(no heading)" and self.location != self.source:
            return f"{name}, {self.location}"
        return name


async def search(
    query: str,
    collection: str,
    top_k: int = DEFAULT_TOP_K,
    source_filter: str | None = None,
) -> list[RetrievedPassage]:
    """Embed the query, search Qdrant, filter by MIN_SCORE.

    TODO(M2+): hybrid search — dense + sparse/BM25. Pure dense retrieval is weak
      on exact identifiers (error codes, SKUs, part numbers), which is a large
      share of real support queries.

    Returning an EMPTY list is a valid, important result: it tells the agent the
    knowledge base does not cover this, which is grounds for escalation. Never
    pad results to reach top_k — low-score filler is how RAG starts hallucinating.
    """
    from ollama import AsyncClient
    from qdrant_client import AsyncQdrantClient, models

    from backend.config.loader import get_config

    config = get_config()
    ollama_client = AsyncClient(host=_ollama_base_url())
    embed_response = await ollama_client.embed(model=config.models.embedding, input=[query])
    vector = embed_response.embeddings[0]

    qdrant = AsyncQdrantClient(url=_qdrant_url(), api_key=_qdrant_api_key())
    try:
        if not await qdrant.collection_exists(collection):
            return []

        query_filter = None
        if source_filter:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="source", match=models.MatchValue(value=source_filter)
                    )
                ]
            )

        result = await qdrant.query_points(
            collection_name=collection,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
            score_threshold=MIN_SCORE,
        )
    finally:
        await qdrant.close()

    return [
        RetrievedPassage(
            text=point.payload["text"],
            source=point.payload["source"],
            location=point.payload["location"],
            score=point.score,
        )
        for point in result.points
    ]


def format_for_agent(passages: list[RetrievedPassage]) -> str:
    """Render passages with inline citation markers.

    Format so the model naturally carries markers into its answer. Say
    explicitly in the tool description that unsourced claims are not acceptable.
    """
    if not passages:
        return (
            "No relevant passages were found in the knowledge base for this query. "
            "Do not answer from general knowledge — tell the customer this isn't "
            "something you have documentation for, or escalate."
        )

    blocks = [
        f"[{i}] (source: {p.citation()}, score: {p.score:.2f})\n{p.text}"
        for i, p in enumerate(passages, start=1)
    ]
    blocks.append(
        "When you use any of the passages above, cite it inline with its [n] marker "
        "and name the source. Do not state anything as fact that isn't backed by one "
        "of these passages."
    )
    return "\n\n".join(blocks)


async def health(collection: str) -> bool:
    """Collection exists and has points. Surfaced in /api/health — "RAG is
    configured but the collection is empty" is a common and confusing failure."""
    from qdrant_client import AsyncQdrantClient

    client = AsyncQdrantClient(url=_qdrant_url(), api_key=_qdrant_api_key())
    try:
        if not await client.collection_exists(collection):
            return False
        info = await client.get_collection(collection)
        return bool(info.points_count and info.points_count > 0)
    finally:
        await client.close()
