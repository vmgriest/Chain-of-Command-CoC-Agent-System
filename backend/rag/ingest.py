"""Knowledge ingestion: documents and web pages -> Qdrant.  (M2)

    python -m backend.rag.ingest --config company_config.json

⚠ Must be IDEMPOTENT. Point IDs are content hashes, so re-running after adding
  one document re-embeds unchanged chunks to the same IDs rather than creating
  duplicates. Duplicated chunks quietly poison retrieval — the same passage
  crowds out diverse results and the agent sounds oddly repetitive.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.config.schema import CompanyConfig

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


@dataclass
class Chunk:
    """One embeddable unit, carrying enough metadata to cite it later.

    `source` and `location` exist so the agent can say "per the handbook, p.14"
    instead of asserting a fact from nowhere.
    """

    text: str
    source: str  # file path or URL
    location: str  # page number, heading, or anchor
    content_hash: str


def stable_id(text: str, source: str) -> str:
    """TODO(M2): deterministic point ID from sha256(source + text).

    Same content at the same source -> same ID -> upsert overwrites instead of
    duplicating. This one function is what makes re-runs safe.
    """
    raise NotImplementedError


# --- loaders --------------------------------------------------------------


def load_pdf(path: Path) -> list[Chunk]:
    """TODO(M2): pypdf, one chunk group per page, page number into `location`."""
    raise NotImplementedError


def load_markdown(path: Path) -> list[Chunk]:
    """TODO(M2): split on headings so chunks align with sections; nearest heading
    into `location`. Heading-aligned chunks retrieve noticeably better than
    fixed-width splits on structured docs."""
    raise NotImplementedError


def load_directory(path: Path) -> list[Chunk]:
    """TODO(M2): recurse, dispatch by extension (.pdf/.md/.txt), skip the rest
    with a logged warning rather than silently."""
    raise NotImplementedError


async def crawl(urls: list[str], allowed_domain: str) -> list[Chunk]:
    """TODO(M2): fetch and extract main content.

      - httpx + BeautifulSoup, strip nav/footer/script
      - stay on `allowed_domain`; do not follow off-domain links
      - depth limit (2), page cap, and polite rate limiting
      - `location` = URL fragment or the nearest heading
    """
    raise NotImplementedError


# --- embedding + upsert ---------------------------------------------------


async def embed_chunks(chunks: list[Chunk], model: str) -> list[list[float]]:
    """TODO(M2): batch through Ollama embeddings.

    Batch — one HTTP call per chunk is painfully slow on a handbook-sized corpus.
    """
    raise NotImplementedError


async def upsert(chunks: list[Chunk], vectors: list[list[float]], collection: str) -> None:
    """TODO(M2): create the collection if absent, then upsert by stable_id.

    Payload: text, source, location, content_hash — everything the retriever
    needs to build a citation without a second lookup.
    """
    raise NotImplementedError


async def ingest(config: CompanyConfig) -> None:
    """TODO(M2): full pipeline — load, crawl, chunk, embed, upsert.

    Report counts per source at the end. "Ingested 412 chunks from 3 documents
    and 27 pages" is how someone notices their PDF silently failed to parse.
    """
    raise NotImplementedError


def main() -> None:
    """TODO(M2): argparse --config, --collection, --dry-run; run ingest()."""
    raise NotImplementedError


if __name__ == "__main__":
    main()

_ = (argparse, hashlib)  # staged for the implementations above
