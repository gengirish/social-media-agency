"""Shared low-level client for the Exa search API.

One client, one retry policy, one "unavailable" contract — used by
``services/trends.py`` and ``agents/competitive_intel.py``. Anything that needs
retrieved web material must go through here rather than growing a second,
divergent HTTP client.

DATA RELIABILITY: this module only ever returns what Exa returned. It has no
sample data and no fallback. When the key is missing or the call fails, callers
get an explicit ``{"status": "unavailable", "reason": ...}`` payload (see
:func:`unavailable`) and are expected to render that state rather than
substituting model-generated or invented content.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
import structlog

from agency.config import get_settings

logger = structlog.get_logger()

EXA_SEARCH_URL = "https://api.exa.ai/search"
DEFAULT_TIMEOUT = 15.0
MAX_RETRIES = 2

SETUP_HINT = (
    "Set EXA_API_KEY in the backend environment (get a key at https://exa.ai) "
    "and restart the API."
)


def get_api_key() -> str:
    """The configured Exa key, stripped. Empty string means "not configured"."""
    return get_settings().exa_api_key.strip()


def unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Build an explicit unavailable payload (never invented content)."""
    return {"status": "unavailable", "reason": reason, **extra}


def http_error_reason(error: httpx.HTTPStatusError) -> str:
    """Human-readable reason for an Exa HTTP failure, with a setup hint on auth errors."""
    code = error.response.status_code
    if code in (401, 403):
        return f"Exa rejected the API key (HTTP {code}). {SETUP_HINT}"
    return f"Exa search API returned HTTP {code}."


async def with_retries[T](
    op: Callable[[], Awaitable[T]],
    *,
    label: str,
    max_retries: int = MAX_RETRIES,
) -> T:
    """Run an async HTTP op with backoff on transient errors.

    4xx responses (other than 429) are permanent — a bad key or a rejected query
    will not recover, so they are raised immediately.
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await op()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if 400 <= code < 500 and code != 429:
                raise
            last_error = e
            logger.warning(
                "exa_http_retry", label=label, attempt=attempt, status=code, error=str(e)
            )
            if attempt >= max_retries:
                raise
            await asyncio.sleep(0.5 * (2**attempt))
        except (httpx.RequestError, httpx.TimeoutException) as e:
            last_error = e
            logger.warning("exa_http_retry", label=label, attempt=attempt, error=str(e))
            if attempt >= max_retries:
                raise
            await asyncio.sleep(0.5 * (2**attempt))
    if last_error is not None:  # pragma: no cover
        raise last_error
    raise RuntimeError(f"{label}: retries exhausted without a result")  # pragma: no cover


async def search(
    api_key: str,
    payload: dict[str, Any],
    *,
    label: str = "exa_search",
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """POST /search against Exa and return the decoded body (retried on transient errors)."""
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=timeout) as client:

        async def do_search() -> dict[str, Any]:
            resp = await client.post(EXA_SEARCH_URL, json=payload, headers=headers)
            resp.raise_for_status()
            body = resp.json()
            return body if isinstance(body, dict) else {}

        return await with_retries(do_search, label=label)


def results_of(body: dict[str, Any]) -> list[Any]:
    """The ``results`` list from an Exa body, or an empty list."""
    raw = body.get("results")
    return raw if isinstance(raw, list) else []


def host(url: str) -> str | None:
    """Publisher host for a URL, ``www.`` stripped."""
    try:
        netloc = urlparse(url).netloc
    except ValueError:
        return None
    return netloc.removeprefix("www.") or None


def parse_published(value: Any) -> datetime | None:
    """Parse Exa's ``publishedDate`` into an aware datetime, or None if absent/garbage."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def normalize_url(url: str) -> str | None:
    """Canonical form of a URL, used to match a claimed citation to a retrieved source.

    Deliberately strict: scheme and host are normalized (and ``www.`` dropped), the
    fragment is discarded and a single trailing slash is trimmed, but the path and
    query are otherwise preserved. Two different pages on the same domain therefore
    never collapse onto one another — a homepage URL cannot stand in for an article.
    """
    if not isinstance(url, str):
        return None
    candidate = url.strip()
    if not candidate:
        return None
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), netloc, path, "", parsed.query, ""))


def is_resolvable_url(url: Any) -> bool:
    """True when a URL is well-formed enough to be worth showing as a citation."""
    return isinstance(url, str) and normalize_url(url) is not None
