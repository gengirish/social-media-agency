"""RAG knowledge base — semantic retrieval and honest mode labelling.

Two things are under test, and the second matters as much as the first:

1. Retrieval is genuinely semantic — a query sharing *no words* with a document
   still retrieves it. The fake embedder below makes that deterministic; no
   embedding API is ever called.
2. Every response says which mode served it. A keyword hit must never be
   presentable as a semantic one, and "nothing configured" must never look like
   "nothing found".

Runs against an in-memory SQLite database (``knowledge_embedding`` carries a
SQLite variant for exactly this reason), so the ranking is exercised through
real SQL rows rather than a stub.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agency.models.tables import Base, KnowledgeEmbedding
from agency.services import knowledge_base as kb

# ---------------------------------------------------------------------------
# A deterministic, offline embedder
# ---------------------------------------------------------------------------
# Each concept is one dimension. A text embeds to its concept counts, so two
# texts about the same concept are close even with zero words in common — which
# is the whole property keyword matching cannot have.
CONCEPTS: dict[str, list[str]] = {
    "email": ["newsletter", "drip", "nurture", "broadcast", "inbox", "subscriber", "mail"],
    "seo": ["backlink", "serp", "crawl", "ranking", "organic", "search", "index"],
    "paid": ["bidding", "cpc", "auction", "impression", "budget", "spend", "click"],
}
CONCEPT_ORDER = list(CONCEPTS)


@dataclass
class FakeEmbedder:
    """Concept-count embedder. Deterministic, offline, no API key."""

    provider: str = "fake"
    model: str = "fake-concept-v1"
    dim: int = len(CONCEPT_ORDER)
    calls: int = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        vectors = []
        for t in texts:
            words = {w.strip(".,;:!?()").lower() for w in t.split()}
            vectors.append(
                [float(len(words & set(CONCEPTS[c]))) for c in CONCEPT_ORDER]
            )
        return vectors


class ExplodingEmbedder(FakeEmbedder):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embeddings endpoint returned 503")


# Deliberately share no words with any query used below.
SKILL_FILES = {
    "email/newsletter-engine.md": (
        "Newsletter drip sequences. Nurture flows deliver a broadcast to an inbox "
        "on schedule. Drip, nurture, broadcast, newsletter, inbox."
    ),
    "seo/backlink-playbook.md": (
        "Backlink acquisition improves serp position. Crawl signals and ranking "
        "factors drive organic discovery. Backlink, serp, crawl, ranking, organic."
    ),
    "paid/auction-tuning.md": (
        "Bidding strategy tuning for an auction. Manage cpc and impression pacing "
        "inside a budget. Bidding, cpc, auction, impression, budget."
    ),
}

# No lexical overlap with any document, but unambiguously about email.
SEMANTIC_QUERY = "grow subscriber base via mail"


# ---------------------------------------------------------------------------
# Fixtures (self-contained — this module does not use conftest.py)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_caches():
    kb.reset_caches()
    yield
    kb.reset_caches()


@pytest.fixture
def skills_dir(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "skills"
    for rel, body in SKILL_FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    monkeypatch.setattr(kb, "_skills_dir", lambda: root)
    kb.reset_caches()
    return root


@pytest.fixture
async def session_factory():
    """In-memory SQLite holding only ``knowledge_embedding``."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[KnowledgeEmbedding.__table__])

    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def indexed(session_factory, skills_dir, monkeypatch):
    """A populated index plus the embedder that built it."""
    embedder = FakeEmbedder()
    async with session_factory() as db:
        stats = await kb.index_knowledge_base(db, embedder)
    assert stats["documents"] == len(SKILL_FILES)
    assert stats["chunks"] >= len(SKILL_FILES)

    monkeypatch.setattr(kb, "get_embedder", lambda: embedder)
    return embedder


# ---------------------------------------------------------------------------
# Acceptance: semantic retrieval with zero lexical overlap
# ---------------------------------------------------------------------------
async def test_query_with_no_shared_words_still_finds_the_right_document(
    session_factory, indexed
):
    async with session_factory() as db:
        results = await kb.retrieve_knowledge(SEMANTIC_QUERY, k=3, session=db)

    assert results.retrieval_mode == kb.VECTOR
    assert results, "semantic retrieval returned nothing"
    assert results[0]["source_path"] == "email/newsletter-engine.md"
    assert results[0]["relevance_score"] > 0.9


async def test_that_query_really_has_no_lexical_overlap(skills_dir, monkeypatch):
    """Guards the test above: keyword scoring finds nothing for that query."""
    monkeypatch.setattr(kb, "get_embedder", lambda: None)
    results = await kb.retrieve_knowledge(SEMANTIC_QUERY, k=3)

    assert results.retrieval_mode == kb.KEYWORD
    assert list(results) == []


async def test_different_concepts_rank_to_different_documents(session_factory, indexed):
    async with session_factory() as db:
        seo = await kb.retrieve_knowledge("improve organic search index", k=1, session=db)
        paid = await kb.retrieve_knowledge("reduce spend per click", k=1, session=db)

    assert seo[0]["source_path"] == "seo/backlink-playbook.md"
    assert paid[0]["source_path"] == "paid/auction-tuning.md"


# ---------------------------------------------------------------------------
# Mode labelling
# ---------------------------------------------------------------------------
async def test_vector_mode_is_labelled_on_the_set_and_on_every_item(session_factory, indexed):
    async with session_factory() as db:
        results = await kb.retrieve_knowledge(SEMANTIC_QUERY, k=3, session=db)

    assert results.retrieval_mode == kb.VECTOR
    assert results.is_semantic is True
    assert results.provider == "fake"
    assert results.model == "fake-concept-v1"
    assert all(item["retrieval_mode"] == kb.VECTOR for item in results)

    payload = results.as_payload()
    assert payload["retrieval_mode"] == kb.VECTOR
    assert payload["count"] == len(results)


async def test_keyword_mode_is_labelled_on_the_set_and_on_every_item(skills_dir, monkeypatch):
    monkeypatch.setattr(kb, "get_embedder", lambda: None)
    results = await kb.retrieve_knowledge("backlink crawl ranking", k=3)

    assert results.retrieval_mode == kb.KEYWORD
    assert results.is_semantic is False
    assert results, "keyword fallback should still match on shared words"
    assert all(item["retrieval_mode"] == kb.KEYWORD for item in results)
    assert results[0]["source_path"] == "seo/backlink-playbook.md"


async def test_no_provider_configured_is_explicit_never_a_silent_empty_list(
    skills_dir, monkeypatch
):
    monkeypatch.setattr(kb, "get_embedder", lambda: None)
    results = await kb.retrieve_knowledge(SEMANTIC_QUERY, k=3)

    # Empty — but the caller is told exactly why, and in which mode.
    assert list(results) == []
    assert results.retrieval_mode == kb.KEYWORD
    assert results.reason == kb.NO_PROVIDER_REASON
    assert "GOOGLE_API_KEY" in results.reason and "OPENAI_API_KEY" in results.reason
    assert results.as_payload()["reason"] == kb.NO_PROVIDER_REASON


async def test_unindexed_corpus_falls_back_to_labelled_keyword(
    session_factory, skills_dir, monkeypatch
):
    """Provider configured, index empty — the failure names the fix."""
    monkeypatch.setattr(kb, "get_embedder", lambda: FakeEmbedder())

    async with session_factory() as db:
        results = await kb.retrieve_knowledge("backlink crawl ranking", k=3, session=db)

    assert results.retrieval_mode == kb.KEYWORD
    assert "no embeddings indexed" in results.reason
    assert "index_knowledge_base.py" in results.reason


async def test_vector_failure_falls_back_and_says_so(session_factory, skills_dir, monkeypatch):
    monkeypatch.setattr(kb, "get_embedder", lambda: ExplodingEmbedder())

    async with session_factory() as db:
        results = await kb.retrieve_knowledge("backlink crawl ranking", k=3, session=db)

    assert results.retrieval_mode == kb.KEYWORD
    assert "vector search failed" in results.reason
    assert "503" in results.reason
    assert results[0]["source_path"] == "seo/backlink-playbook.md"


async def test_empty_query_is_labelled_not_bare(skills_dir, monkeypatch):
    called: list[int] = []

    def _embedder():
        called.append(1)
        return FakeEmbedder()

    monkeypatch.setattr(kb, "get_embedder", _embedder)
    results = await kb.retrieve_knowledge("   ", k=3)

    assert list(results) == []
    assert results.retrieval_mode == kb.KEYWORD
    assert results.reason == "empty query"
    assert called == [], "an empty query must not cost an embedding call"


# ---------------------------------------------------------------------------
# Provider resolution — blank key disables, no silent defaults
# ---------------------------------------------------------------------------
@dataclass
class FakeSettings:
    google_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openai_base_url: str = ""
    llm_provider_order: str = ""


def _with_settings(monkeypatch, **kwargs: Any) -> None:
    monkeypatch.setattr(kb, "get_settings", lambda: FakeSettings(**kwargs))


def test_anthropic_is_not_offered_as_an_embedding_provider():
    """Anthropic has no embeddings endpoint — listing it would guarantee 404s."""
    assert "anthropic" not in kb.EMBEDDING_MODELS
    assert "openrouter" not in kb.EMBEDDING_MODELS
    assert "bonsai" not in kb.EMBEDDING_MODELS


def test_blank_keys_disable_every_provider(monkeypatch, skills_dir):
    _with_settings(monkeypatch, anthropic_api_key="sk-ant-set")
    assert kb.resolve_embedding_provider() == ""

    described = kb.describe_knowledge_base()
    assert described["semantic_retrieval_available"] is False
    assert described["reason"] == kb.NO_PROVIDER_REASON
    assert described["embedding_provider"] is None
    assert described["documents_loaded"] == len(SKILL_FILES)


def test_first_configured_provider_wins(monkeypatch):
    _with_settings(monkeypatch, openai_api_key="sk-openai")
    assert kb.resolve_embedding_provider() == "openai"

    _with_settings(monkeypatch, openai_api_key="sk-openai", google_api_key="g-key")
    assert kb.resolve_embedding_provider() == "google"


def test_provider_order_is_honoured(monkeypatch):
    _with_settings(
        monkeypatch,
        openai_api_key="sk-openai",
        google_api_key="g-key",
        llm_provider_order="anthropic,openai,google",
    )
    assert kb.resolve_embedding_provider() == "openai"


def test_unknown_provider_order_falls_back_to_the_default(monkeypatch):
    _with_settings(monkeypatch, google_api_key="g-key", llm_provider_order="anthropic,bonsai")
    assert kb.resolve_embedding_provider() == "google"


def test_no_embedder_is_built_without_a_key(monkeypatch):
    _with_settings(monkeypatch)
    kb.reset_caches()
    assert kb.get_embedder() is None


# ---------------------------------------------------------------------------
# Vector mechanics
# ---------------------------------------------------------------------------
def test_zero_padding_does_not_change_cosine_similarity():
    a = [0.3, -0.7, 0.5]
    b = [0.1, 0.9, -0.2]
    raw = kb.cosine_similarity(a, b)
    padded = kb.cosine_similarity(kb.pad_vector(a), kb.pad_vector(b))
    assert math.isclose(raw, padded, rel_tol=1e-12)


def test_pad_vector_reaches_the_storage_width():
    assert len(kb.pad_vector([1.0, 2.0])) == kb.EMBEDDING_STORAGE_DIM


def test_pad_vector_refuses_to_truncate():
    with pytest.raises(ValueError, match="exceeds"):
        kb.pad_vector([0.0] * (kb.EMBEDDING_STORAGE_DIM + 1))


def test_cosine_of_a_zero_vector_is_zero():
    assert kb.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_chunking_overlaps_so_boundaries_are_not_lost():
    body = "x" * 3000
    chunks = kb.chunk_text(body, size=1000, overlap=200)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    assert sum(len(c) for c in chunks) > len(body)  # overlap means re-coverage


def test_short_documents_stay_one_chunk():
    assert kb.chunk_text("a short skill note") == ["a short skill note"]
    assert kb.chunk_text("   ") == []


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------
async def test_reindexing_replaces_rather_than_duplicates(session_factory, skills_dir):
    embedder = FakeEmbedder()
    async with session_factory() as db:
        first = await kb.index_knowledge_base(db, embedder)
        second = await kb.index_knowledge_base(db, embedder)

        rows = (await db.execute(select(KnowledgeEmbedding))).scalars().all()

    assert first["chunks"] == second["chunks"] == len(rows)
    assert {r.embedding_provider for r in rows} == {"fake"}
    assert {r.embedding_dim for r in rows} == {len(CONCEPT_ORDER)}
    assert all(len(r.embedding) == kb.EMBEDDING_STORAGE_DIM for r in rows)


async def test_rows_from_another_model_are_never_mixed_in(session_factory, skills_dir, monkeypatch):
    """Vectors from two models are not comparable, so old rows go invisible."""
    async with session_factory() as db:
        await kb.index_knowledge_base(db, FakeEmbedder(model="old-model-v0"))

    switched = FakeEmbedder(model="new-model-v1")
    monkeypatch.setattr(kb, "get_embedder", lambda: switched)

    async with session_factory() as db:
        results = await kb.retrieve_knowledge(SEMANTIC_QUERY, k=3, session=db)

    assert results.retrieval_mode == kb.KEYWORD
    assert "new-model-v1" in results.reason


async def test_indexing_an_empty_library_reports_zero(session_factory, tmp_path):
    async with session_factory() as db:
        stats = await kb.index_knowledge_base(db, FakeEmbedder(), skills_dir=tmp_path / "nope")
    assert stats == {"documents": 0, "chunks": 0, "model": "fake-concept-v1"}


# ---------------------------------------------------------------------------
# Caller contract (agents/strategy.py reads title + content off each item)
# ---------------------------------------------------------------------------
async def test_items_keep_the_shape_the_strategy_agent_consumes(session_factory, indexed):
    async with session_factory() as db:
        results = await kb.retrieve_knowledge(SEMANTIC_QUERY, k=2, session=db)

    assert isinstance(results, list)
    for item in results:
        assert set(item) >= {
            "title",
            "category",
            "source_path",
            "content",
            "relevance_score",
            "retrieval_mode",
        }
        assert isinstance(item["title"], str) and item["title"]
        assert isinstance(item["content"], str) and item["content"]
