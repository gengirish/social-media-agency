"""General-purpose web search for the agents, on top of the shared Exa client.

``services/trends.py`` and ``agents/competitive_intel.py`` each own a *narrow*
Exa query shaped for one job. This module is the broad one: an agent that needs
to ground a claim, check a fact, or pull real sources on an arbitrary topic calls
:func:`gather_sources` and puts the result in its prompt.

It follows the house pattern — retrieve, then prompt. Agents here are not
tool-calling; nothing binds tools to the LLM. ``competitive_intel.gather_sources``
fetches first and hands sources to ``get_worker_llm()``, and this mirrors that so
there is one idiom rather than two.

REQUEST SHAPE. Exa's own guidance (``.agents/skills/build-with-exa``) is that the
recommended request is the query plus token-efficient highlights and *nothing
else*, and that over-decorating it is the most common integration mistake. So:

    {"query": ..., "type": "auto", "contents": {"highlights": true}}

``numResults`` is sent because a fixed per-call budget is a deliberate product
decision here (agents run inside a paid pipeline), not boilerplate. Everything
else — ``category``, domain allow/blocklists, ``startPublishedDate`` — is
deliberately absent. Recency belongs in the caller's query phrasing; a hard
published-date filter silently drops undated and misdated pages, which is the
wrong default for grounding. :func:`gather_sources` exposes ``published_after``
for the genuine case where a caller must enforce a bounded window.

DATA RELIABILITY: like every Exa path in this codebase, this returns only what
Exa returned. No sample data, no fallback, no model-generated stand-ins. A
missing key or a failed call yields an explicit ``{"status": "unavailable", ...}``
payload that the caller must render as an empty state.
"""

from datetime import datetime
from typing import Any

import httpx
import structlog

from agency.services import exa_client

logger = structlog.get_logger()

#: Results per call. A budget, not a preference — Exa's server default is 10 and
#: every result costs tokens downstream when it reaches an agent's prompt.
DEFAULT_RESULTS = 6

#: Upper bound a caller may ask for, so one agent cannot flood a prompt.
MAX_RESULTS = 25


def _highlights_of(raw: dict[str, Any]) -> list[str]:
    """The result's highlight strings, dropping blanks.

    Exa returns ``highlights`` as a list of strings. A page it could not extract
    comes back with the field absent or empty rather than as an error, so an
    empty list here means "no content for this source", not "call failed".
    """
    raw_highlights = raw.get("highlights")
    if not isinstance(raw_highlights, list):
        return []
    return [h.strip() for h in raw_highlights if isinstance(h, str) and h.strip()]


def _normalize(raw: Any) -> dict[str, Any] | None:
    """One Exa result as a source dict, or None if it is not usable.

    A result with no resolvable URL is dropped: it cannot be cited, and an
    uncitable source is worse than one fewer source in a grounding prompt.
    """
    if not isinstance(raw, dict):
        return None
    # The isinstance check is redundant at runtime — ``is_resolvable_url`` does it
    # too — but it is what narrows ``url`` from ``Any | None`` to ``str`` for the
    # type checker, so the ``host``/``parse_published`` calls below stay checked
    # rather than silently accepting None.
    url = raw.get("url")
    if not isinstance(url, str) or not exa_client.is_resolvable_url(url):
        return None

    published = exa_client.parse_published(raw.get("publishedDate"))
    title = raw.get("title")
    return {
        "title": title.strip() if isinstance(title, str) and title.strip() else url,
        "url": url,
        "publisher": exa_client.host(url),
        "published_at": published.isoformat() if published else None,
        "highlights": _highlights_of(raw),
    }


async def gather_sources(
    query: str,
    *,
    limit: int = DEFAULT_RESULTS,
    published_after: datetime | None = None,
    label: str = "web_search",
) -> dict[str, Any]:
    """Search the web for ``query`` and return citable sources.

    Args:
        query: Retrieval intent only. Put recency here ("latest", "recent") rather
            than reaching for a date filter. Do not put instructions like "only"
            or "exclude" in it — this endpoint does no synthesis, so such clauses
            just degrade retrieval.
        limit: Results to request, clamped to ``MAX_RESULTS``.
        published_after: Only when the caller must enforce a *stated* window. This
            is a hard filter that drops undated pages, so leave it None for
            ordinary "recent news" phrasing.
        label: Log label, so a retry storm can be traced to its caller.

    Returns:
        ``{"status": "ok", "query": ..., "sources": [...], "provenance": "exa_search"}``
        or an explicit ``{"status": "unavailable", "reason": ...}``. ``sources``
        may legitimately be empty when Exa found nothing — that is ``ok`` with an
        empty list, not ``unavailable``, and callers must tell the two apart.
    """
    cleaned = query.strip()
    if not cleaned:
        return exa_client.unavailable("No search query was provided.")

    api_key = exa_client.get_api_key()
    if not api_key:
        # The variable to set is logged for whoever runs the server, not shown
        # to whoever is using the app (CF-16).
        logger.info("web_search_exa_not_configured", fix=exa_client.SETUP_HINT)
        return exa_client.unavailable(exa_client.NOT_CONFIGURED_REASON)

    payload: dict[str, Any] = {
        "query": cleaned,
        "type": "auto",
        "contents": {"highlights": True},
        "numResults": max(1, min(limit, MAX_RESULTS)),
    }
    if published_after is not None:
        payload["startPublishedDate"] = published_after.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    try:
        body = await exa_client.search(api_key, payload, label=label)
    except httpx.HTTPStatusError as e:
        logger.warning("web_search_http_error", label=label, status=e.response.status_code)
        return exa_client.unavailable(exa_client.http_error_reason(e))
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.warning("web_search_unreachable", label=label, error=str(e))
        return exa_client.unavailable(f"Could not reach the Exa search API: {e}")

    sources = [s for s in (_normalize(r) for r in exa_client.results_of(body)) if s]
    logger.info(
        "web_search_ok",
        label=label,
        requested=payload["numResults"],
        returned=len(sources),
    )
    return {
        "status": "ok",
        "query": cleaned,
        "sources": sources,
        "provenance": "exa_search",
    }


def format_for_prompt(result: dict[str, Any]) -> str:
    """Render :func:`gather_sources` output as prompt text an agent can cite from.

    Every source is numbered and carries its URL, so the model has something real
    to attribute a claim to. On an unavailable or empty result this returns an
    explicit "no sources" line rather than an empty string: a blank section reads
    to the model as "nothing to say here", whereas a stated absence discourages it
    from filling the gap from memory.
    """
    if result.get("status") != "ok":
        reason = result.get("reason") or "Web search was unavailable."
        return f"NO WEB SOURCES AVAILABLE: {reason}\nDo not invent sources or statistics."

    sources = result.get("sources") or []
    if not sources:
        return (
            f'NO WEB SOURCES FOUND for "{result.get("query", "")}".\n'
            "Do not invent sources or statistics."
        )

    lines: list[str] = []
    for i, s in enumerate(sources, 1):
        meta = " · ".join(p for p in (s.get("publisher"), s.get("published_at")) if p)
        lines.append(f"[{i}] {s['title']}" + (f" ({meta})" if meta else ""))
        lines.append(f"    {s['url']}")
        for h in s.get("highlights", []):
            lines.append(f"    > {h}")
    return "\n".join(lines)
