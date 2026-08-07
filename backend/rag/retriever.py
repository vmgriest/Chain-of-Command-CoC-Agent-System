"""Retrieval from Qdrant.  (M2)

Always returns citations alongside passages. An agent that cannot attribute a
claim should not be making it — and the Manager tier's whole value over the
Front Desk is that it can point at a source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.config.schema import CompanyConfig

DEFAULT_TOP_K = 5
MIN_SCORE = 0.35  # TODO(M2): tune against the real corpus; this is a guess


@dataclass
class RetrievedPassage:
    """A search hit with everything needed to cite it."""

    text: str
    source: str
    location: str
    score: float

    def citation(self) -> str:
        """TODO(M2): human-readable, e.g. 'handbook.pdf, p.14' or the page title."""
        raise NotImplementedError


async def search(
    query: str,
    collection: str,
    top_k: int = DEFAULT_TOP_K,
    source_filter: str | None = None,
) -> list[RetrievedPassage]:
    """TODO(M2): embed the query, search Qdrant, filter by MIN_SCORE.

    TODO(M2): hybrid search — dense + sparse/BM25. Pure dense retrieval is weak
      on exact identifiers (error codes, SKUs, part numbers), which is a large
      share of real support queries.

    Returning an EMPTY list is a valid, important result: it tells the agent the
    knowledge base does not cover this, which is grounds for escalation. Never
    pad results to reach top_k — low-score filler is how RAG starts hallucinating.
    """
    raise NotImplementedError


def format_for_agent(passages: list[RetrievedPassage]) -> str:
    """TODO(M2): render passages with inline citation markers.

    Format so the model naturally carries markers into its answer. Say
    explicitly in the tool description that unsourced claims are not acceptable.
    """
    raise NotImplementedError


# TODO(M2): async def health(collection) -> bool
#   Collection exists and has points. Surfaced in /api/health — "RAG is
#   configured but the collection is empty" is a common and confusing failure.

_ = (CompanyConfig,) if TYPE_CHECKING else None
