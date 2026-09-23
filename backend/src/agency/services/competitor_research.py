"""Live web research for the comparison page and niche scan, via the shared Exa client.

Returns what Exa returned or an explicit ``unavailable`` record — never
invented material. The caller saves this record on the asset
(``payload.webResearch``) so the card can say whether the output was grounded
in live documents or written without any.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from agency.agents import competitive_intel
from agency.services import exa_client

logger = structlog.get_logger()

#: Documents handed to the model per competitor (Exa returns up to 6).
SOURCES_PER_COMPETITOR = 4

NO_KEY_REASON = "Web search is not configured for this workspace (EXA_API_KEY is not set)."


def _public(source: dict[str, Any]) -> dict[str, Any]:
    """What the card shows: enough to verify, without the page text."""
    return {
        "id": source.get("id"),
        "competitor": source.get("competitor"),
        "title": source.get("title"),
        "url": source.get("url"),
        "domain": source.get("domain"),
        "publishedDate": source.get("published_date"),
    }


async def research_competitors(names: list[str], industry: str) -> dict[str, Any]:
    """``{"status", "reason", "sources" (full, for the prompt), "public", "retrievedAt"}``."""
    retrieved_at = datetime.now(UTC).isoformat()
    api_key = exa_client.get_api_key()
    if not api_key:
        return {
            "status": "unavailable",
            "reason": NO_KEY_REASON,
            "sources": [],
            "public": [],
            "retrievedAt": retrieved_at,
        }
    try:
        sources, _queries, errors, auth_status = await competitive_intel.gather_sources(
            api_key, names, industry
        )
    except Exception as exc:  # noqa: BLE001 — degrade to "unavailable", never fabricate
        logger.warning("content_research_failed", error=str(exc))
        sources, errors, auth_status = [], [f"Web search failed: {exc}"], None

    kept: list[dict[str, Any]] = []
    per: dict[str, int] = {}
    for s in sources:
        comp = str(s.get("competitor"))
        if per.get(comp, 0) < SOURCES_PER_COMPETITOR:
            per[comp] = per.get(comp, 0) + 1
            kept.append(s)

    if not kept:
        reason = "; ".join(errors) if errors else "Web search returned no usable documents."
        if auth_status:
            reason = errors[0] if errors else "Web search rejected the API key."
        return {
            "status": "unavailable",
            "reason": reason,
            "sources": [],
            "public": [],
            "retrievedAt": retrieved_at,
        }
    missing = [n for n in names if n not in per]
    return {
        "status": "ok",
        "reason": (f"No documents found for: {', '.join(missing)}." if missing else None),
        "sources": kept,
        "public": [_public(s) for s in kept],
        "retrievedAt": retrieved_at,
    }


def sources_note(research: dict[str, Any], model_note: str) -> str:
    """The provenance line saved on the asset. Set in code; the model's note is appended."""
    if research.get("status") == "ok":
        n = len(research.get("public") or [])
        head = f"Based on {n} document{'s' if n != 1 else ''} retrieved by live web search."
        if research.get("reason"):
            head += f" {research['reason']}"
    else:
        head = (
            f"No live web data: {research.get('reason') or 'web search was unavailable'} "
            "Written from the model's general knowledge only, which may be outdated or wrong; "
            "verify every point about a named competitor before acting on it."
        )
    return f"{head} {model_note}".strip() if model_note else head
