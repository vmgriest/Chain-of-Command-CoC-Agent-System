"""RAG ingestion + retrieval tests.  (M2)

Loaders and the crawler's HTML handling are tested against real content (the
example docs shipped in docs/) rather than synthetic strings — that's what
caught the nav-link-stripping-order bug during development. Embedding/Qdrant
calls are faked; those are network boundaries the M1 test suite deliberately
never touches (see tests/conftest.py's own docstring).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"

# ---------------------------------------------------------------------------
# stable_id
# ---------------------------------------------------------------------------


def test_stable_id_is_deterministic() -> None:
    from backend.rag.ingest import stable_id

    a = stable_id("some passage text", "handbook.pdf")
    b = stable_id("some passage text", "handbook.pdf")
    assert a == b


def test_stable_id_differs_by_source_and_text() -> None:
    from backend.rag.ingest import stable_id

    base = stable_id("some passage text", "handbook.pdf")
    assert stable_id("different text", "handbook.pdf") != base
    assert stable_id("some passage text", "other.pdf") != base


def test_stable_id_is_a_valid_uuid() -> None:
    import uuid

    from backend.rag.ingest import stable_id

    # Qdrant point IDs must be an unsigned int or a UUID string — this is the
    # constraint that makes the sha256-fold-into-UUID trick necessary.
    uuid.UUID(stable_id("x", "y"))  # raises ValueError if malformed


# ---------------------------------------------------------------------------
# loaders — exercised against the real example content in docs/
# ---------------------------------------------------------------------------


def test_load_pdf_extracts_all_handbook_pages() -> None:
    from backend.rag.ingest import load_pdf

    chunks = load_pdf(DOCS / "handbook.pdf")
    assert len(chunks) >= 4  # one handbook section per page, at minimum
    locations = {c.location for c in chunks}
    assert locations == {"p.1", "p.2", "p.3", "p.4"}
    all_text = " ".join(c.text for c in chunks)
    # Facts unique to the example handbook, not general model knowledge —
    # these are what let the demo prove Manager answers from the PDF and
    # Front Desk (no RAG tool) cannot.
    assert "E-317" in all_text
    assert "ARW-#####" in all_text or "ARW-" in all_text


def test_load_markdown_splits_on_headings() -> None:
    from backend.rag.ingest import load_markdown

    chunks = load_markdown(DOCS / "policies" / "shipping.md")
    locations = {c.location for c in chunks}
    assert "Domestic Shipping" in locations
    assert "International Shipping" in locations
    domestic = next(c for c in chunks if c.location == "Domestic Shipping")
    assert "FastShip" in domestic.text


def test_load_directory_dispatches_by_extension(tmp_path: Path) -> None:
    from backend.rag.ingest import load_directory

    (tmp_path / "a.md").write_text("# Heading\ncontent", encoding="utf-8")
    (tmp_path / "b.txt").write_text("plain text content", encoding="utf-8")
    (tmp_path / "c.unsupported").write_text("skip me", encoding="utf-8")

    chunks = load_directory(tmp_path)
    sources = {Path(c.source).name for c in chunks}
    assert sources == {"a.md", "b.txt"}


def test_load_path_missing_file_warns_and_returns_empty(caplog: pytest.LogCaptureFixture) -> None:
    from backend.rag.ingest import load_path

    with caplog.at_level("WARNING"):
        chunks = load_path("does/not/exist.pdf")
    assert chunks == []
    assert "does not exist" in caplog.text


# ---------------------------------------------------------------------------
# crawler
# ---------------------------------------------------------------------------


def test_extract_page_finds_links_inside_nav() -> None:
    """Regression test: an earlier version stripped <nav>/<header> BEFORE
    collecting links, silently dropping every link that lived in site nav."""
    from backend.rag.ingest import extract_page

    html = (DOCS / "example_site" / "index.html").read_text(encoding="utf-8")
    text, links = extract_page(html, "http://localhost:8080/")
    assert any(link.endswith("faq.html") for link in links)
    assert any(link.endswith("contact.html") for link in links)
    assert "Welcome to Acme Robotics Support" in text
    # Boilerplate must not leak into the extracted text.
    assert "Home" not in text  # nav link text


class _FakeResponse:
    def __init__(self, text: str, url: str, status_code: int = 200) -> None:
        self.text = text
        self.url = url
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("error", request=None, response=self)  # type: ignore[arg-type]


class _FakeHTTPXClient:
    """Stands in for httpx.AsyncClient: serves fixed pages by URL, no network."""

    def __init__(self, pages: dict[str, str], **_kwargs: object) -> None:
        self._pages = pages

    async def __aenter__(self) -> _FakeHTTPXClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def get(self, url: str) -> _FakeResponse:
        if url not in self._pages:
            return _FakeResponse("", url, status_code=404)
        return _FakeResponse(self._pages[url], url)


@pytest.mark.asyncio
async def test_crawl_stays_on_allowed_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    pages = {
        "http://example.test/": (
            '<html><body><a href="/page2">in-domain</a>'
            '<a href="http://other.test/evil">off-domain</a>Home text</body></html>'
        ),
        "http://example.test/page2": "<html><body>Second page text</body></html>",
    }

    def _client_factory(**kwargs: object) -> _FakeHTTPXClient:
        return _FakeHTTPXClient(pages, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory)
    monkeypatch.setattr("backend.rag.ingest.CRAWL_DELAY_SECONDS", 0)

    from backend.rag.ingest import crawl

    chunks = await crawl(["http://example.test/"], "example.test")
    sources = {c.source for c in chunks}
    assert sources == {"http://example.test/", "http://example.test/page2"}
    assert not any("other.test" in s for s in sources)


# ---------------------------------------------------------------------------
# embedding + upsert (Ollama / Qdrant faked — network boundary)
# ---------------------------------------------------------------------------


class _FakeEmbedResponse:
    def __init__(self, n: int, dim: int = 4) -> None:
        self.embeddings = [[float(i)] * dim for i in range(n)]


class _FakeOllamaClient:
    def __init__(self, **_kwargs: object) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, model: str, input: list[str]) -> _FakeEmbedResponse:  # noqa: A002
        self.calls.append(input)
        return _FakeEmbedResponse(len(input))


@pytest.mark.asyncio
async def test_embed_chunks_batches_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.rag import ingest as ingest_module

    fake_client = _FakeOllamaClient()
    monkeypatch.setattr("ollama.AsyncClient", lambda **kw: fake_client)

    chunks = [
        ingest_module.Chunk(text=f"chunk {i}", source="s", location="l", content_hash=str(i))
        for i in range(5)
    ]
    vectors = await ingest_module.embed_chunks(chunks, "nomic-embed-text", batch_size=2)

    assert len(vectors) == 5
    assert [len(c) for c in fake_client.calls] == [2, 2, 1]  # batched, not one-per-chunk


@pytest.mark.asyncio
async def test_embed_chunks_empty_list_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    """No chunks -> no Ollama call at all (an empty ingest run must not error)."""
    from backend.rag import ingest as ingest_module

    def _boom(**_kw: object) -> None:
        msg = "should not be called for an empty chunk list"
        raise AssertionError(msg)

    monkeypatch.setattr("ollama.AsyncClient", _boom)
    assert await ingest_module.embed_chunks([], "nomic-embed-text") == []


class _FakeQdrantClient:
    def __init__(self, **_kwargs: object) -> None:
        self.created: list[tuple[str, int]] = []
        self.upserted_points: list = []
        self._exists = False

    async def collection_exists(self, name: str) -> bool:
        return self._exists

    async def create_collection(self, collection_name: str, vectors_config: object) -> None:
        self.created.append((collection_name, vectors_config.size))
        self._exists = True

    async def upsert(self, collection_name: str, points: list) -> None:
        self.upserted_points.extend(points)

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_upsert_creates_collection_then_upserts_with_stable_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.rag import ingest as ingest_module

    fake_client = _FakeQdrantClient()
    monkeypatch.setattr("qdrant_client.AsyncQdrantClient", lambda **kw: fake_client)

    chunks = [ingest_module.Chunk(text="hello", source="s.md", location="l", content_hash="h")]
    vectors = [[0.1, 0.2, 0.3]]

    await ingest_module.upsert(chunks, vectors, "test_collection")

    assert fake_client.created == [("test_collection", 3)]
    assert len(fake_client.upserted_points) == 1
    assert fake_client.upserted_points[0].id == ingest_module.stable_id("hello", "s.md")


@pytest.mark.asyncio
async def test_upsert_rerun_reuses_same_point_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """The idempotency guarantee: re-ingesting identical content produces the
    SAME point id both times, so re-running upsert overwrites rather than
    duplicating."""
    from backend.rag import ingest as ingest_module

    fake_client = _FakeQdrantClient()
    monkeypatch.setattr("qdrant_client.AsyncQdrantClient", lambda **kw: fake_client)

    chunks = [ingest_module.Chunk(text="hello", source="s.md", location="l", content_hash="h")]
    await ingest_module.upsert(chunks, [[0.1, 0.2]], "c")
    await ingest_module.upsert(chunks, [[0.1, 0.2]], "c")

    ids = {p.id for p in fake_client.upserted_points}
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_upsert_empty_chunks_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.rag import ingest as ingest_module

    def _boom(**_kw: object) -> None:
        msg = "should not connect to Qdrant for an empty upsert"
        raise AssertionError(msg)

    monkeypatch.setattr("qdrant_client.AsyncQdrantClient", _boom)
    await ingest_module.upsert([], [], "c")  # must not raise


@pytest.mark.asyncio
async def test_ingest_warns_and_returns_when_nothing_to_ingest(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, config
) -> None:
    from backend.rag import ingest as ingest_module

    empty_config = config.model_copy(
        update={
            "knowledge": config.knowledge.model_copy(update={"documents": [], "crawl_urls": []})
        }
    )

    def _boom(*_a: object, **_kw: object) -> None:
        msg = "must not attempt to embed when there is nothing to ingest"
        raise AssertionError(msg)

    monkeypatch.setattr(ingest_module, "embed_chunks", _boom)
    with caplog.at_level("WARNING"):
        await ingest_module.ingest(empty_config)
    assert "nothing to ingest" in caplog.text.lower()


# ---------------------------------------------------------------------------
# retriever
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_empty_list_when_collection_missing(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    from backend.rag import retriever as retriever_module

    class _MissingCollectionClient:
        def __init__(self, **_kw: object) -> None:
            pass

        async def collection_exists(self, _name: str) -> bool:
            return False

        async def close(self) -> None:
            pass

    monkeypatch.setattr("backend.config.loader.get_config", lambda: config)
    monkeypatch.setattr("ollama.AsyncClient", lambda **kw: SimpleNamespace(embed=_fake_embed_one))
    monkeypatch.setattr("qdrant_client.AsyncQdrantClient", lambda **kw: _MissingCollectionClient())

    results = await retriever_module.search("anything", "missing_collection")
    assert results == []


async def _fake_embed_one(model: str, input: list[str]):  # noqa: A002
    return SimpleNamespace(embeddings=[[0.1, 0.2, 0.3]])


@pytest.mark.asyncio
async def test_search_maps_qdrant_points_to_passages(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    from backend.rag import retriever as retriever_module

    point = SimpleNamespace(
        payload={"text": "the answer", "source": "handbook.pdf", "location": "p.2"}, score=0.81
    )

    class _HitClient:
        def __init__(self, **_kw: object) -> None:
            pass

        async def collection_exists(self, _name: str) -> bool:
            return True

        async def query_points(self, **_kw: object):
            return SimpleNamespace(points=[point])

        async def close(self) -> None:
            pass

    monkeypatch.setattr("backend.config.loader.get_config", lambda: config)
    monkeypatch.setattr("ollama.AsyncClient", lambda **kw: SimpleNamespace(embed=_fake_embed_one))
    monkeypatch.setattr("qdrant_client.AsyncQdrantClient", lambda **kw: _HitClient())

    results = await retriever_module.search("warranty", "acme_support")
    assert len(results) == 1
    assert results[0].text == "the answer"
    assert results[0].citation() == "handbook.pdf, p.2"


def test_citation_uses_url_directly_for_crawled_pages() -> None:
    from backend.rag.retriever import RetrievedPassage

    passage = RetrievedPassage(
        text="t",
        source="http://localhost:8080/faq.html",
        location="http://localhost:8080/faq.html",
        score=0.5,
    )
    assert passage.citation() == "http://localhost:8080/faq.html"


def test_format_for_agent_empty_result_tells_agent_not_to_guess() -> None:
    from backend.rag.retriever import format_for_agent

    text = format_for_agent([])
    assert "No relevant passages" in text
    assert "do not answer from general knowledge" in text.lower()


def test_format_for_agent_includes_citation_markers() -> None:
    from backend.rag.retriever import RetrievedPassage, format_for_agent

    passages = [RetrievedPassage(text="fact one", source="handbook.pdf", location="p.1", score=0.9)]
    text = format_for_agent(passages)
    assert "[1]" in text
    assert "handbook.pdf" in text
    assert "fact one" in text


# ---------------------------------------------------------------------------
# Manager tier real tools
# ---------------------------------------------------------------------------


def test_manager_build_wires_real_tools_not_stubs() -> None:
    from backend.graph.tiers import manager

    compiled = manager.build("llama3:8b")
    assert "tools" in compiled.get_graph().nodes


def test_allowed_scrape_domains_includes_company_domain_and_crawl_hosts(config) -> None:
    from backend.graph.tiers import manager

    domains = manager.allowed_scrape_domains()
    assert config.company.domain in domains
    assert "localhost:8080" in domains


@pytest.mark.asyncio
async def test_scrape_url_refuses_off_allowlist_domain(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    from backend.graph.tiers import manager

    monkeypatch.setattr("backend.config.loader.get_config", lambda: config)
    scrape_url = next(t for t in manager.real_tools() if t.name == "scrape_url")
    result = await scrape_url.ainvoke({"url": "http://evil.example.com/steal"})
    assert "Refused" in result


@pytest.mark.asyncio
async def test_run_code_tool_delegates_to_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.graph.tiers import manager

    async def _fake_run(code: str, language: str = "python") -> str:
        return f"ran: {code}"

    monkeypatch.setattr("backend.mcp.sandbox.run_sandboxed_code", _fake_run)
    run_code = next(t for t in manager.real_tools() if t.name == "run_code")
    result = await run_code.ainvoke({"snippet": "print(1+1)"})
    assert result == "ran: print(1+1)"
