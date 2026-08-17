"""One-shot indexer for the RAG knowledge base.

Embeds every markdown file in the marketing skill library into
``knowledge_embedding``. Run it once after deploy, and again whenever the skill
library or the embedding provider changes — nothing is embedded on the request
path except the query itself.

    cd backend
    python scripts/index_knowledge_base.py

Prerequisites, both of which the script checks and reports on rather than
assuming:

1. ``CREATE EXTENSION IF NOT EXISTS vector;`` has been run on the target
   database (Neon supports pgvector but it is not enabled by default).
2. An embedding provider is configured — ``GOOGLE_API_KEY`` (or
   ``GEMINI_API_KEY``) or ``OPENAI_API_KEY``.

Without either, retrieval still works but reports ``retrieval_mode: "keyword"``
on every response. It never claims to be semantic.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import text  # noqa: E402

from agency.models.database import get_engine, get_session_factory  # noqa: E402
from agency.services.knowledge_base import (  # noqa: E402
    NO_PROVIDER_REASON,
    get_embedder,
    index_knowledge_base,
)


async def _pgvector_present() -> bool:
    async with get_engine().connect() as conn:
        row = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
        return row.first() is not None


async def main() -> int:
    embedder = get_embedder()
    if embedder is None:
        print(f"ABORT: {NO_PROVIDER_REASON}")
        return 2

    try:
        if not await _pgvector_present():
            print(
                "ABORT: the 'vector' extension is not enabled on this database.\n"
                "       Run: CREATE EXTENSION IF NOT EXISTS vector;\n"
                "       (Neon supports it, but it must be enabled per database.)"
            )
            return 3
    except Exception as exc:
        print(f"ABORT: could not reach the database ({type(exc).__name__}: {exc})")
        return 4

    print(f"Embedding with provider={embedder.provider} model={embedder.model} dim={embedder.dim}")
    async with get_session_factory()() as session:
        stats = await index_knowledge_base(session, embedder)

    print(
        f"Indexed {stats['chunks']} chunks from {stats['documents']} documents "
        f"({stats.get('model')})."
    )
    if stats["chunks"] == 0:
        print("WARNING: nothing was indexed — retrieval will report retrieval_mode='keyword'.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
