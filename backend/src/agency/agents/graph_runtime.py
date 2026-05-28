"""Singleton compiled campaign graph + LangGraph checkpointer (Postgres or Memory)."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from langgraph.checkpoint.memory import MemorySaver

from agency.agents.graph import build_campaign_graph
from agency.config import get_settings

logger = structlog.get_logger(__name__)

_init_lock = asyncio.Lock()
_compiled_graph: Any = None
_pool: Any = None


def _normalize_psycopg_conninfo(url: str) -> str:
    """Strip SQLAlchemy async driver prefix so psycopg can connect."""
    u = url.strip()
    if u.startswith("postgresql+asyncpg://"):
        return "postgresql://" + u.removeprefix("postgresql+asyncpg://")
    return u


def get_runtime_compiled_graph() -> Any:
    """Return the app-wide compiled graph (must be initialized at startup)."""
    if _compiled_graph is None:
        msg = (
            "Campaign LangGraph is not initialized; "
            "ensure init_campaign_graph_runtime() runs during application startup."
        )
        raise RuntimeError(msg)
    return _compiled_graph


async def init_campaign_graph_runtime() -> None:
    """Open Postgres pool + run checkpoint migrations, or use MemorySaver fallback."""
    global _compiled_graph, _pool

    async with _init_lock:
        if _compiled_graph is not None:
            return

        settings = get_settings()
        raw_neon = (settings.neon_database_url or "").strip()

        if not raw_neon:
            logger.warning(
                "langgraph_checkpointer_memory_fallback",
                reason="neon_database_url_empty",
            )
            _compiled_graph = build_campaign_graph().compile(
                checkpointer=MemorySaver(),
                interrupt_before=["human_review"],
            )
            return

        conninfo = _normalize_psycopg_conninfo(raw_neon)
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg.rows import dict_row
            from psycopg_pool import AsyncConnectionPool

            _pool = AsyncConnectionPool(
                conninfo=conninfo,
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                min_size=1,
                max_size=10,
                open=False,
                timeout=60.0,
            )
            await _pool.open()
            checkpointer = AsyncPostgresSaver(_pool)
            await checkpointer.setup()
            _compiled_graph = build_campaign_graph().compile(
                checkpointer=checkpointer,
                interrupt_before=["human_review"],
            )
            logger.info("langgraph_checkpointer_ready", backend="postgres")
        except Exception as e:
            logger.warning(
                "langgraph_checkpointer_memory_fallback",
                reason="postgres_init_failed",
                error=str(e),
            )
            if _pool is not None:
                await _pool.close()
                _pool = None
            _compiled_graph = build_campaign_graph().compile(
                checkpointer=MemorySaver(),
                interrupt_before=["human_review"],
            )


async def shutdown_campaign_graph_runtime() -> None:
    """Release the connection pool (app shutdown)."""
    global _compiled_graph, _pool

    async with _init_lock:
        if _pool is not None:
            await _pool.close()
            _pool = None
        _compiled_graph = None
