"""Knowledge ingestion: documents and web pages -> Qdrant.  (M2)

    uv run python -m backend.rag.ingest --config company_config.json

⚠ Must be IDEMPOTENT. Point IDs are content hashes, so re-running after adding
  one document re-embeds unchanged chunks to the same IDs rather than creating
  duplicates. Duplicated chunks quietly poison retrieval — the same passage
  crowds out diverse results and the agent sounds oddly repetitive.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

if TYPE_CHECKING:
    from backend.config.schema import CompanyConfig

logger = logging.getLogger("coc.rag.ingest")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# Crawler limits — deliberately conservative. This is a support-doc crawler, not
# a general-purpose one: depth 2 covers "site -> section -> article" without
# wandering into the rest of a company's website.
CRAWL_DEPTH_LIMIT = 2
CRAWL_PAGE_CAP = 50
CRAWL_DELAY_SECONDS = 0.5


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
    """Deterministic point ID from sha256(source + text).

    Same content at the same source -> same ID -> upsert overwrites instead of
    duplicating. This one function is what makes re-runs safe.

    Qdrant point IDs must be an unsigned int or a UUID, so the digest is folded
    into a UUID rather than used as a raw hex string.
    """
    digest = hashlib.sha256(f"{source}::{text}".encode()).hexdigest()
    return str(uuid.UUID(digest[:32]))


def _content_hash(text: str, source: str) -> str:
    return hashlib.sha256(f"{source}::{text}".encode()).hexdigest()


def _split_text(text: str) -> list[str]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    return [piece.strip() for piece in splitter.split_text(text) if piece.strip()]


def _make_chunks(text: str, source: str, location: str) -> list[Chunk]:
    return [
        Chunk(
            text=piece, source=source, location=location, content_hash=_content_hash(piece, source)
        )
        for piece in _split_text(text)
    ]


# --- loaders --------------------------------------------------------------


def load_pdf(path: Path) -> list[Chunk]:
    """pypdf, one chunk group per page, page number into `location`."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    chunks: list[Chunk] = []
    for page_num, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        chunks.extend(_make_chunks(text, str(path), f"p.{page_num}"))
    return chunks


def load_markdown(path: Path) -> list[Chunk]:
    """Split on headings so chunks align with sections; nearest heading into
    `location`. Heading-aligned chunks retrieve noticeably better than
    fixed-width splits on structured docs."""
    from langchain_text_splitters import MarkdownHeaderTextSplitter

    text = path.read_text(encoding="utf-8")
    headers_to_split_on = [("#", "h1"), ("##", "h2"), ("###", "h3")]
    sections = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, strip_headers=False
    ).split_text(text)

    if not sections:
        return _make_chunks(text, str(path), "(no heading)")

    chunks: list[Chunk] = []
    for section in sections:
        heading = (
            section.metadata.get("h3")
            or section.metadata.get("h2")
            or section.metadata.get("h1")
            or "(no heading)"
        )
        chunks.extend(_make_chunks(section.page_content, str(path), heading))
    return chunks


def load_text(path: Path) -> list[Chunk]:
    """Plain text: no structure to align to, just fixed-width chunks."""
    return _make_chunks(path.read_text(encoding="utf-8"), str(path), "(no heading)")


_LOADERS_BY_SUFFIX = {
    ".pdf": load_pdf,
    ".md": load_markdown,
    ".markdown": load_markdown,
    ".txt": load_text,
}


def _load_one(path: Path) -> list[Chunk]:
    loader = _LOADERS_BY_SUFFIX.get(path.suffix.lower())
    if loader is None:
        logger.warning("Skipping %s: unsupported extension %r", path, path.suffix)
        return []
    return loader(path)


def load_directory(path: Path) -> list[Chunk]:
    """Recurse, dispatch by extension (.pdf/.md/.txt), skip the rest with a
    logged warning rather than silently."""
    chunks: list[Chunk] = []
    for file_path in sorted(path.rglob("*")):
        if file_path.is_file():
            chunks.extend(_load_one(file_path))
    return chunks


def load_path(path_str: str) -> list[Chunk]:
    """Entry point used by `ingest()`: a single file or a directory."""
    path = Path(path_str)
    if not path.exists():
        logger.warning("Knowledge document path does not exist, skipping: %s", path_str)
        return []
    if path.is_dir():
        return load_directory(path)
    return _load_one(path)


# --- crawler ----------------------------------------------------------------


def extract_page(html: str, url: str) -> tuple[str, list[str]]:
    """Strip boilerplate, return (main text, absolute links found on the page)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    # Links live in nav/header as often as in the body, so collect them BEFORE
    # stripping boilerplate tags — stripping first (as an earlier version of
    # this function did) silently drops every link inside a <nav>.
    links = [urljoin(url, a["href"]) for a in soup.find_all("a", href=True)]

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text("\n", strip=True) if main else ""
    return text, links


async def crawl(urls: list[str], allowed_domain: str | set[str]) -> list[Chunk]:
    """Fetch and extract main content, breadth-first from `urls`.

    - httpx + BeautifulSoup, strip nav/footer/script
    - stay on `allowed_domain`; do not follow off-domain links
    - depth limit (2), page cap, and polite rate limiting
    - `location` = URL fragment or the nearest heading
    """
    import httpx

    allowed = {allowed_domain} if isinstance(allowed_domain, str) else set(allowed_domain)
    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(u, 0) for u in urls]
    chunks: list[Chunk] = []

    async with httpx.AsyncClient(
        timeout=15.0, follow_redirects=True, headers={"User-Agent": "CoC-RAG-Ingest/1.0"}
    ) as client:
        while queue and len(seen) < CRAWL_PAGE_CAP:
            url, depth = queue.pop(0)
            if url in seen or urlparse(url).netloc not in allowed:
                continue
            seen.add(url)

            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Crawl failed for %s: %s", url, exc)
                continue

            text, links = extract_page(response.text, url)
            location = urlparse(url).fragment or url
            chunks.extend(_make_chunks(text, url, location))

            if depth < CRAWL_DEPTH_LIMIT:
                for link in links:
                    link = link.split("#", 1)[0]
                    if link not in seen and urlparse(link).netloc in allowed:
                        queue.append((link, depth + 1))

            await asyncio.sleep(CRAWL_DELAY_SECONDS)

    return chunks


# --- embedding + upsert ---------------------------------------------------


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def _qdrant_url() -> str:
    return os.environ.get("QDRANT_URL", "http://localhost:6333")


def _qdrant_api_key() -> str | None:
    return os.environ.get("QDRANT_API_KEY") or None


async def embed_chunks(chunks: list[Chunk], model: str, batch_size: int = 32) -> list[list[float]]:
    """Batch through Ollama embeddings.

    Batch — one HTTP call per chunk is painfully slow on a handbook-sized corpus.
    """
    from ollama import AsyncClient

    if not chunks:
        return []

    client = AsyncClient(host=_ollama_base_url())
    vectors: list[list[float]] = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        response = await client.embed(model=model, input=[c.text for c in batch])
        vectors.extend(response.embeddings)
    return vectors


async def upsert(chunks: list[Chunk], vectors: list[list[float]], collection: str) -> None:
    """Create the collection if absent, then upsert by stable_id.

    Payload: text, source, location, content_hash — everything the retriever
    needs to build a citation without a second lookup.
    """
    from qdrant_client import AsyncQdrantClient, models

    if not chunks:
        return
    if len(chunks) != len(vectors):
        msg = f"chunks/vectors length mismatch: {len(chunks)} vs {len(vectors)}"
        raise ValueError(msg)

    client = AsyncQdrantClient(url=_qdrant_url(), api_key=_qdrant_api_key())
    try:
        if not await client.collection_exists(collection):
            await client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(
                    size=len(vectors[0]), distance=models.Distance.COSINE
                ),
            )

        points = [
            models.PointStruct(
                id=stable_id(chunk.text, chunk.source),
                vector=vector,
                payload={
                    "text": chunk.text,
                    "source": chunk.source,
                    "location": chunk.location,
                    "content_hash": chunk.content_hash,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        await client.upsert(collection_name=collection, points=points)
    finally:
        await client.close()


async def ingest(config: CompanyConfig) -> None:
    """Full pipeline — load, crawl, chunk, embed, upsert.

    Report counts per source at the end. "Ingested 412 chunks from 3 documents
    and 27 pages" is how someone notices their PDF silently failed to parse.
    """
    chunks: list[Chunk] = []
    per_source_counts: list[tuple[str, int]] = []

    for doc_path in config.knowledge.documents:
        loaded = load_path(doc_path)
        per_source_counts.append((doc_path, len(loaded)))
        chunks.extend(loaded)

    crawl_urls = [str(u) for u in config.knowledge.crawl_urls]
    if crawl_urls:
        allowed_domains = {config.company.domain} | {urlparse(u).netloc for u in crawl_urls}
        crawled = await crawl(crawl_urls, allowed_domains)
        per_source_counts.append((f"{len(crawl_urls)} crawl seed URL(s)", len(crawled)))
        chunks.extend(crawled)

    if not chunks:
        logger.warning(
            "No chunks produced — nothing to ingest. Check knowledge.documents and "
            "knowledge.crawl_urls in the config."
        )
        return

    vectors = await embed_chunks(chunks, config.models.embedding)
    await upsert(chunks, vectors, config.knowledge.qdrant_collection)

    n_docs = len(config.knowledge.documents)
    logger.info(
        "Ingested %d chunks from %d documents and %d crawl seed(s) into collection %r",
        len(chunks),
        n_docs,
        len(crawl_urls),
        config.knowledge.qdrant_collection,
    )
    for source, count in per_source_counts:
        logger.info("  %s -> %d chunks", source, count)


async def _dry_run(config: CompanyConfig) -> None:
    """Load and chunk only — no embedding, no crawl, no network."""
    chunks: list[Chunk] = []
    for doc_path in config.knowledge.documents:
        loaded = load_path(doc_path)
        logger.info("[dry-run] %s -> %d chunks", doc_path, len(loaded))
        chunks.extend(loaded)
    logger.info(
        "[dry-run] %d total chunks from %d documents (crawl and embedding skipped)",
        len(chunks),
        len(config.knowledge.documents),
    )


def main() -> None:
    """argparse --config, --collection, --dry-run; run ingest()."""
    parser = argparse.ArgumentParser(description="Ingest company knowledge into Qdrant.")
    parser.add_argument(
        "--config", default="company_config.json", help="Path to company_config.json"
    )
    parser.add_argument(
        "--collection", default=None, help="Override knowledge.qdrant_collection from config"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Load and chunk documents only; skip embed/upsert"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from backend.config.loader import load_config

    config = load_config(Path(args.config))
    if args.collection:
        config = config.model_copy(
            update={
                "knowledge": config.knowledge.model_copy(
                    update={"qdrant_collection": args.collection}
                )
            }
        )

    if args.dry_run:
        asyncio.run(_dry_run(config))
    else:
        asyncio.run(ingest(config))


if __name__ == "__main__":
    main()
