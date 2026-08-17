"""RAG knowledge base over the marketing skill library.

Retrieval runs in one of two **disclosed** modes, and every response says which
one served it:

- ``retrieval_mode="vector"`` — the query was embedded and ranked by cosine
  similarity against ``knowledge_embedding``. This is the semantic path: a query
  sharing no words with a document can still retrieve it.
- ``retrieval_mode="keyword"`` — word-overlap scoring over the raw files. Used
  when no embedding provider is configured, when the index is empty, or when the
  vector query fails. Always carries a ``reason``.

The fallback exists because a marketing agent losing its context is worse than
a lexical hit, but it is never allowed to masquerade as semantic retrieval —
callers can read ``retrieval_mode`` off the result set *and* off every item.

Embedding providers follow the same discipline as ``services/llm_provider.py``:
a blank API key disables a provider, and nothing is silently invented. Only
providers with a real embeddings endpoint are listed — see
:data:`EMBEDDING_MODELS`.

Indexing is a separate, explicit step (``backend/scripts/index_knowledge_base.py``).
Nothing is embedded on the read path except the query itself.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import structlog
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from agency.config import get_settings
from agency.models.tables import EMBEDDING_STORAGE_DIM, KnowledgeEmbedding

logger = structlog.get_logger()

VECTOR = "vector"
KEYWORD = "keyword"

# Providers exposing a real embeddings endpoint, in preference order, with the
# model used and its native dimension.
#
# Deliberately absent:
#   * anthropic — has no embeddings API at all (its docs point at Voyage AI).
#   * openrouter, bonsai — chat-completions gateways; no /embeddings route.
#   * nvidia — NIM's retrieval models require an `input_type` field
#     (query vs passage) that the OpenAI SDK does not send, so asymmetric
#     retrieval would silently degrade. Excluded rather than half-supported.
EMBEDDING_MODELS: dict[str, tuple[str, int]] = {
    "google": ("models/text-embedding-004", 768),
    "openai": ("text-embedding-3-small", 1536),
}

DEFAULT_EMBEDDING_ORDER = ("google", "openai")

# Characters per indexed chunk, and the overlap carried into the next chunk so a
# concept split across a boundary is still retrievable from both sides.
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 200
EMBED_BATCH_SIZE = 32

# Upper bound on how much of one skill file is read. The library is markdown
# prose; this only guards against a pathological file.
MAX_DOC_CHARS = 20_000

_knowledge_cache: list[dict[str, Any]] = []
_embedder_cache: Embedder | None = None


# ---------------------------------------------------------------------------
# Result envelope
# ---------------------------------------------------------------------------
class KnowledgeResults(list[dict[str, Any]]):
    """The retrieved entries, carrying the mode that produced them.

    A plain ``list`` subclass so existing callers keep working unchanged, but the
    mode travels with the result even when it is *empty* — an empty list on its
    own would be exactly the silent answer this module is meant to stop giving.
    """

    def __init__(
        self,
        items: list[dict[str, Any]],
        *,
        retrieval_mode: str,
        reason: str = "",
        provider: str = "",
        model: str = "",
    ) -> None:
        super().__init__(items)
        self.retrieval_mode = retrieval_mode
        self.reason = reason
        self.provider = provider
        self.model = model

    @property
    def is_semantic(self) -> bool:
        return self.retrieval_mode == VECTOR

    def as_payload(self) -> dict[str, Any]:
        """Serialisable envelope for API responses and logs."""
        return {
            "retrieval_mode": self.retrieval_mode,
            "reason": self.reason,
            "provider": self.provider,
            "model": self.model,
            "count": len(self),
            "results": list(self),
        }


# ---------------------------------------------------------------------------
# Embedding providers
# ---------------------------------------------------------------------------
class Embedder(Protocol):
    """Everything the index and the retriever need from an embedding backend."""

    provider: str
    model: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class LangChainEmbedder:
    """Adapter over a LangChain embeddings client."""

    provider: str
    model: str
    dim: int
    client: Any

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = await self.client.aembed_documents(texts)
        return [[float(v) for v in vec] for vec in vectors]


def _embedding_order() -> tuple[str, ...]:
    """Preference order, reusing ``LLM_PROVIDER_ORDER`` where it applies."""
    raw = (get_settings().llm_provider_order or "").strip()
    if not raw:
        return DEFAULT_EMBEDDING_ORDER
    chosen = tuple(
        p.strip().lower() for p in raw.split(",") if p.strip().lower() in EMBEDDING_MODELS
    )
    return chosen or DEFAULT_EMBEDDING_ORDER


def _api_key_for(provider: str) -> str:
    s = get_settings()
    return {"google": s.google_api_key, "openai": s.openai_api_key}.get(provider, "")


def resolve_embedding_provider() -> str:
    """First configured embedding provider, or ``""`` if none is."""
    for name in _embedding_order():
        if _api_key_for(name):
            return name
    return ""


NO_PROVIDER_REASON = (
    "no embedding provider configured — set GOOGLE_API_KEY (or GEMINI_API_KEY) "
    "or OPENAI_API_KEY to enable semantic retrieval"
)


def _build_embedder(provider: str) -> Embedder:
    model, dim = EMBEDDING_MODELS[provider]
    key = _api_key_for(provider)

    if provider == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        client: Any = GoogleGenerativeAIEmbeddings(model=model, google_api_key=key)
    else:
        from langchain_openai import OpenAIEmbeddings

        s = get_settings()
        kwargs: dict[str, Any] = {"model": model, "api_key": key}
        if s.openai_base_url:
            kwargs["base_url"] = s.openai_base_url
        client = OpenAIEmbeddings(**kwargs)

    return LangChainEmbedder(provider=provider, model=model, dim=dim, client=client)


def get_embedder() -> Embedder | None:
    """The configured embedder, or ``None`` when no provider has a key.

    ``None`` is the honest answer, not an error: retrieval degrades to a
    keyword mode that says so. Tests monkeypatch this function.
    """
    global _embedder_cache
    if _embedder_cache is not None:
        return _embedder_cache

    provider = resolve_embedding_provider()
    if not provider:
        return None

    try:
        _embedder_cache = _build_embedder(provider)
    except Exception as exc:  # pragma: no cover - import/construction failure path
        logger.warning("embedder_build_failed", provider=provider, error=str(exc))
        return None
    return _embedder_cache


def reset_caches() -> None:
    """Drop the skill-library and embedder caches (tests, re-index scripts)."""
    global _knowledge_cache, _embedder_cache
    _knowledge_cache = []
    _embedder_cache = None


def describe_knowledge_base() -> dict[str, Any]:
    """Diagnostics. Never returns key material."""
    provider = resolve_embedding_provider()
    model, dim = EMBEDDING_MODELS.get(provider, ("", 0))
    return {
        "embedding_provider": provider or None,
        "embedding_model": model or None,
        "embedding_dim": dim or None,
        "storage_dim": EMBEDDING_STORAGE_DIM,
        "semantic_retrieval_available": bool(provider),
        "reason": "" if provider else NO_PROVIDER_REASON,
        "documents_loaded": len(_load_skills_library()),
    }


# ---------------------------------------------------------------------------
# Vector helpers
# ---------------------------------------------------------------------------
def pad_vector(vec: list[float], width: int = EMBEDDING_STORAGE_DIM) -> list[float]:
    """Zero-pad to the storage width. Cosine similarity is unaffected."""
    if len(vec) > width:
        raise ValueError(
            f"embedding of {len(vec)} dims exceeds the {width}-dim storage column; "
            "widen EMBEDDING_STORAGE_DIM and the vector(...) column together"
        )
    return list(vec) + [0.0] * (width - len(vec))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Skill library loading + chunking
# ---------------------------------------------------------------------------
def _skills_dir() -> Path:
    root = Path(__file__).resolve().parents[4]
    specific = root / ".cursor" / "skills" / "marketing-skills-library"
    return specific if specific.exists() else root / ".cursor" / "skills"


def _load_skills_library(skills_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load marketing skills from the skills library directory."""
    global _knowledge_cache
    if skills_dir is None:
        if _knowledge_cache:
            return _knowledge_cache
        skills_dir = _skills_dir()
        cache = True
    else:
        cache = False

    if not skills_dir.exists():
        return []

    entries: list[dict[str, Any]] = []
    for md_file in sorted(skills_dir.rglob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            if len(content) < 50:
                continue
            rel_path = md_file.relative_to(skills_dir)
            rel = rel_path.as_posix()
            entries.append(
                {
                    "id": hashlib.md5(rel.encode()).hexdigest(),
                    "path": rel,
                    "category": rel_path.parts[0] if len(rel_path.parts) > 1 else "general",
                    "content": content[:MAX_DOC_CHARS],
                    "title": md_file.stem.replace("-", " ").replace("_", " ").title(),
                }
            )
        except Exception:
            continue

    if cache:
        _knowledge_cache = entries
        logger.info("knowledge_base_loaded", count=len(entries))
    return entries


def chunk_text(content: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split a document into overlapping character windows."""
    body = content.strip()
    if not body:
        return []
    if len(body) <= size:
        return [body]

    step = max(size - overlap, 1)
    chunks = []
    for start in range(0, len(body), step):
        piece = body[start : start + size].strip()
        if piece:
            chunks.append(piece)
        if start + size >= len(body):
            break
    return chunks


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------
async def index_knowledge_base(
    session: AsyncSession,
    embedder: Embedder,
    skills_dir: Path | None = None,
) -> dict[str, Any]:
    """Embed the skill library into ``knowledge_embedding``.

    Idempotent per model: rows for this ``embedding_model`` are replaced. Rows
    written by another model are left alone so a provider switch can be rolled
    back without re-embedding.
    """
    entries = _load_skills_library(skills_dir)
    if not entries:
        logger.warning("knowledge_index_no_documents", skills_dir=str(skills_dir or _skills_dir()))
        return {"documents": 0, "chunks": 0, "model": embedder.model}

    await session.execute(
        delete(KnowledgeEmbedding).where(KnowledgeEmbedding.embedding_model == embedder.model)
    )

    pending: list[tuple[dict[str, Any], int, str]] = [
        (entry, idx, chunk)
        for entry in entries
        for idx, chunk in enumerate(chunk_text(str(entry["content"])))
    ]

    written = 0
    for start in range(0, len(pending), EMBED_BATCH_SIZE):
        batch = pending[start : start + EMBED_BATCH_SIZE]
        vectors = await embedder.embed([chunk for _, _, chunk in batch])
        for (entry, chunk_index, chunk), vector in zip(batch, vectors, strict=True):
            session.add(
                KnowledgeEmbedding(
                    id=uuid.uuid4(),
                    document_id=str(entry["id"]),
                    source_path=str(entry["path"]),
                    title=str(entry["title"]),
                    category=str(entry["category"]),
                    chunk_index=chunk_index,
                    chunk_text=chunk,
                    embedding_provider=embedder.provider,
                    embedding_model=embedder.model,
                    embedding_dim=len(vector),
                    embedding=pad_vector([float(v) for v in vector]),
                    metadata_={"chars": len(chunk)},
                )
            )
            written += 1

    await session.commit()
    logger.info(
        "knowledge_index_written",
        documents=len(entries),
        chunks=written,
        provider=embedder.provider,
        model=embedder.model,
    )
    return {
        "documents": len(entries),
        "chunks": written,
        "provider": embedder.provider,
        "model": embedder.model,
    }


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def _keyword_results(query: str, k: int, reason: str) -> KnowledgeResults:
    """Word-overlap scoring — the disclosed fallback."""
    entries = _load_skills_library()
    query_words = {w for w in query.lower().split() if w}
    scored: list[tuple[int, dict[str, Any]]] = []

    if query_words and entries:
        for entry in entries:
            content_words = set(str(entry["content"])[:500].lower().split())
            title_words = set(str(entry["title"]).lower().split())
            overlap = len(query_words & (content_words | title_words))
            if overlap > 0:
                scored.append((overlap, entry))
        scored.sort(key=lambda x: x[0], reverse=True)

    items = [
        {
            "title": e["title"],
            "category": e["category"],
            "source_path": e["path"],
            "content": str(e["content"])[:1000],
            "relevance_score": float(score),
            "retrieval_mode": KEYWORD,
        }
        for score, e in scored[:k]
    ]
    return KnowledgeResults(items, retrieval_mode=KEYWORD, reason=reason)


async def _vector_candidates(
    session: AsyncSession, embedder: Embedder, query_vector: list[float], k: int
) -> list[dict[str, Any]]:
    """Top-``k`` chunks by cosine similarity for the active model."""
    try:
        dialect = session.get_bind().dialect.name
    except Exception:  # pragma: no cover - unbound session
        dialect = ""

    if dialect == "postgresql":
        # Cast through text so asyncpg types the parameter as text rather than
        # the `vector` type it has no codec for.
        sql = text(
            """
            SELECT title, category, source_path, chunk_text,
                   1 - (embedding <=> CAST(CAST(:qvec AS text) AS vector)) AS score
            FROM knowledge_embedding
            WHERE embedding_model = :model
            ORDER BY embedding <=> CAST(CAST(:qvec AS text) AS vector)
            LIMIT :limit
            """
        )
        literal = "[" + ",".join(repr(float(v)) for v in pad_vector(query_vector)) + "]"
        rows = await session.execute(
            sql, {"qvec": literal, "model": embedder.model, "limit": k}
        )
        return [
            {
                "title": r.title,
                "category": r.category,
                "source_path": r.source_path,
                "content": r.chunk_text,
                "relevance_score": float(r.score),
            }
            for r in rows
        ]

    # No pgvector operator available (SQLite in tests): rank in Python. Still a
    # genuine cosine ranking over real embeddings, so the mode stays "vector".
    result = await session.execute(
        select(KnowledgeEmbedding).where(KnowledgeEmbedding.embedding_model == embedder.model)
    )
    padded = pad_vector(query_vector)
    ranked = sorted(
        (
            (cosine_similarity(padded, list(row.embedding or [])), row)
            for row in result.scalars().all()
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [
        {
            "title": row.title,
            "category": row.category,
            "source_path": row.source_path,
            "content": row.chunk_text,
            "relevance_score": float(score),
        }
        for score, row in ranked[:k]
    ]


async def retrieve_knowledge(
    query: str, k: int = 3, session: AsyncSession | None = None
) -> KnowledgeResults:
    """Retrieve knowledge entries, cosine-first with a labelled keyword fallback.

    The returned :class:`KnowledgeResults` carries ``retrieval_mode`` (and every
    item repeats it), so no caller can mistake a lexical hit for a semantic one.
    """
    if not query or not query.strip():
        return KnowledgeResults([], retrieval_mode=KEYWORD, reason="empty query")

    embedder = get_embedder()
    if embedder is None:
        return _keyword_results(query, k, NO_PROVIDER_REASON)

    own_session = session is None
    try:
        vector = (await embedder.embed([query]))[0]
        if own_session:
            from agency.models.database import get_session_factory

            async with get_session_factory()() as db:
                items = await _vector_candidates(db, embedder, vector, k)
        else:
            assert session is not None
            items = await _vector_candidates(session, embedder, vector, k)
    except Exception as exc:
        logger.warning("knowledge_vector_search_failed", error=str(exc))
        return _keyword_results(
            query, k, f"vector search failed ({type(exc).__name__}: {exc}) — fell back to keyword"
        )

    if not items:
        return _keyword_results(
            query,
            k,
            f"no embeddings indexed for model {embedder.model!r} — "
            "run backend/scripts/index_knowledge_base.py",
        )

    for item in items:
        item["retrieval_mode"] = VECTOR

    return KnowledgeResults(
        items,
        retrieval_mode=VECTOR,
        provider=embedder.provider,
        model=embedder.model,
    )
