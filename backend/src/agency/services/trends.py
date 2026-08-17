"""Trend intelligence service — trending topics sourced live from the Exa search API.

DATA RELIABILITY: this module NEVER fabricates trend data. There is no hardcoded
topic list and no fallback sample data. Every returned item is a real Exa search
result carrying its own ``url`` so a reader can verify it.

Result shape::

    {
        "status": "ok",
        "source": "exa_search",
        "platform": "linkedin" | None,
        "query": "...",              # exact query sent to Exa
        "fetched_at": "2026-08-17T09:00:00+00:00",
        "fields_not_provided": ["volume", "category"],
        "provenance": "...",
        "items": [
            {
                "topic": "...",           # Exa result title
                "url": "https://...",     # verifiable source
                "source": "example.com",  # publisher host
                "platform": "linkedin" | None,
                "published_date": "2026-08-11T00:00:00.000Z" | None,
                "recency_days": 6 | None, # derived from published_date, NOT volume
                "relevance_score": 0.31 | None,   # Exa's own score, when returned
                "provenance": "exa_search",
            },
            ...
        ],
    }

When ``EXA_API_KEY`` is blank, or the Exa call fails, the result is
``{"status": "unavailable", "reason": ..., "items": []}`` — mirroring the
convention in ``services/platform_metrics.py``. Callers must render that state
rather than substituting invented topics.

Note on ``volume`` and ``category``: Exa is a web-search API. It returns neither
search volume nor a marketing category, so both fields are omitted and listed in
``fields_not_provided``. ``recency_days`` is the only derived field and it is
computed from Exa's ``publishedDate`` — it is a recency signal, not a volume.
"""

# ``asyncio`` is not called here directly — the retry backoff lives in
# ``exa_client`` — but it stays imported so the sleep used by this module's HTTP
# path remains patchable as ``trends.asyncio.sleep``.
import asyncio  # noqa: F401
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from agency.services import exa_client
from agency.services.exa_client import (
    DEFAULT_TIMEOUT,
    EXA_SEARCH_URL,
    SETUP_HINT,
)

logger = structlog.get_logger()

__all__ = [
    "DEFAULT_TIMEOUT",
    "EXA_SEARCH_URL",
    "SETUP_HINT",
    "SUPPORTED_PLATFORMS",
    "build_query",
    "get_trending_topics",
]

_MAX_RETRIES = exa_client.MAX_RETRIES
_RESULT_LIMIT = 10
_LOOKBACK_DAYS = 30

#: Platforms the trends tab offers. Values are the human labels used in the query.
SUPPORTED_PLATFORMS: dict[str, str] = {
    "twitter": "X (Twitter)",
    "linkedin": "LinkedIn",
    "instagram": "Instagram",
    "facebook": "Facebook",
}

#: Exa returns web results, not audience metrics. Both of these are honestly absent.
FIELDS_NOT_PROVIDED = ["volume", "category"]

PROVENANCE_NOTE = (
    "Topics are live Exa search results. Exa does not report search volume or a "
    "marketing category, so those fields are omitted; 'recency_days' is derived "
    "from each result's published date."
)


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Build an explicit unavailable result (never fake topics)."""
    return exa_client.unavailable(reason, items=[], **extra)


def build_query(platform: str | None) -> str:
    """The exact search string sent to Exa, surfaced in the response for auditability."""
    if platform:
        label = SUPPORTED_PLATFORMS[platform]
        return (
            f"trending marketing topics and content themes on {label} "
            "that brands are talking about right now"
        )
    return (
        "trending social media marketing topics and content themes "
        "that brands are talking about right now"
    )


def _recency_days(published: datetime | None, *, now: datetime) -> int | None:
    """Days since publication — a real signal derived from Exa's own metadata."""
    if published is None:
        return None
    return max(0, (now - published).days)


def _map_result(raw: Any, platform: str | None, *, now: datetime) -> dict[str, Any] | None:
    """Map one Exa result onto a trend item, or None if it carries no usable topic."""
    if not isinstance(raw, dict):
        return None
    topic = (raw.get("title") or "").strip()
    url = (raw.get("url") or "").strip()
    if not topic or not url:
        return None

    published_raw = raw.get("publishedDate")
    published = exa_client.parse_published(published_raw)
    score = raw.get("score")

    return {
        "topic": topic,
        "url": url,
        "source": exa_client.host(url),
        "platform": platform,
        "published_date": published_raw if isinstance(published_raw, str) else None,
        "recency_days": _recency_days(published, now=now),
        "relevance_score": float(score) if isinstance(score, int | float) else None,
        "provenance": "exa_search",
    }


async def _search_exa(api_key: str, query: str) -> dict[str, Any]:
    """POST /search against Exa (shared client) and return the decoded body."""
    start_date = (datetime.now(UTC) - timedelta(days=_LOOKBACK_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    payload: dict[str, Any] = {
        "query": query,
        "numResults": _RESULT_LIMIT,
        "type": "auto",
        "category": "news",
        "startPublishedDate": start_date,
    }
    return await exa_client.search(api_key, payload, label="trends_search")


async def get_trending_topics(platform: str | None = None) -> dict[str, Any]:
    """Fetch trending topics from Exa for a platform (or social marketing generally).

    Returns an ``ok`` payload with real, source-linked topics, or an explicit
    ``unavailable`` payload. It never returns invented topics.
    """
    platform = (platform or "").strip().lower() or None
    if platform and platform not in SUPPORTED_PLATFORMS:
        return _unavailable(
            f"Unsupported platform '{platform}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_PLATFORMS))}.",
            platform=platform,
        )

    api_key = exa_client.get_api_key()
    if not api_key:
        logger.info("trends_exa_not_configured", platform=platform)
        return _unavailable(
            f"Trend data source (Exa) is not configured. {SETUP_HINT}",
            platform=platform,
        )

    query = build_query(platform)
    try:
        body = await _search_exa(api_key, query)
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        logger.warning("trends_exa_http_error", platform=platform, status=status_code)
        return _unavailable(
            exa_client.http_error_reason(e), platform=platform, http_status=status_code
        )
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.warning("trends_exa_request_error", platform=platform, error=str(e))
        return _unavailable(f"Exa search API request failed: {e}", platform=platform)
    except Exception as e:  # noqa: BLE001 — defensive: never fabricate on unexpected errors
        logger.error("trends_exa_unexpected_error", platform=platform, error=str(e))
        return _unavailable(f"Exa search failed: {e}", platform=platform)

    now = datetime.now(UTC)
    results = exa_client.results_of(body)
    items = [
        item
        for item in (_map_result(raw, platform, now=now) for raw in results)
        if item is not None
    ]

    if not items:
        logger.info("trends_exa_empty", platform=platform, query=query)
        return _unavailable(
            "Exa returned no usable results for this query.",
            platform=platform,
            query=query,
        )

    logger.info("trends_exa_ok", platform=platform, count=len(items))
    return {
        "status": "ok",
        "source": "exa_search",
        "platform": platform,
        "query": query,
        "fetched_at": now.isoformat(),
        "fields_not_provided": FIELDS_NOT_PROVIDED,
        "provenance": PROVENANCE_NOTE,
        "items": items,
    }
