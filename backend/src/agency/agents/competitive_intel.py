"""Competitive intelligence agent — retrieval first, model second.

DATA RELIABILITY: this agent does not ask a model what it "knows" about a
competitor. It retrieves real, dated, public documents through the shared Exa
client (:mod:`agency.services.exa_client`), hands that retrieved text to the LLM,
and then **drops every finding that cannot be matched back to one of the
retrieved documents**. The drop is enforced in :func:`ground_findings` — in
code, not in the prompt — because a prompt is a request and a filter is a
guarantee.

Result shape::

    {
        "status": "ok",
        "source": "exa_search",
        "retrieved_at": "2026-08-17T09:00:00+00:00",
        "competitors": ["Acme"],
        "queries": {"Acme": "..."},          # exact query sent to Exa, for auditability
        "sources": [
            {
                "id": "S1",
                "competitor": "Acme",
                "title": "...",
                "url": "https://...",        # verifiable
                "domain": "acme.com",
                "published_date": "2026-07-02T00:00:00.000Z" | None,
                "retrieved_at": "2026-08-17T09:00:00+00:00",
                "excerpt": "..." | None,
            }
        ],
        "findings": [
            {
                "competitor": "Acme",
                "category": "messaging_theme",
                "claim": "...",
                "evidence": "...",           # text taken from the retrieved page
                "source_id": "S1",
                "source_url": "https://...", # copied from the SOURCE, never the model
                "source_title": "...",
                "source_domain": "acme.com",
                "published_date": "..." | None,
                "retrieved_at": "2026-08-17T09:00:00+00:00",
            }
        ],
        "dropped_unsourced_count": 2,
        "dropped_unsourced": [{"claim": "...", "claimed_source_url": None}],
        "recommendations": {"counter_campaigns": [...], "strategy": "..."},
        "fields_not_provided": [...],
        "provenance": "...",
    }

When ``EXA_API_KEY`` is blank, when Exa returns nothing usable, or when no model
finding survives the source filter, the result is
``{"status": "unavailable", "reason": ..., "findings": []}``. There is no
ungrounded-LLM fallback: that fallback is the failure mode this module exists to
remove.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from agency.services import exa_client
from agency.services.llm_provider import get_worker_llm

logger = structlog.get_logger()

#: Cap on competitors scanned per request — each one costs an Exa call.
MAX_COMPETITORS = 3
RESULTS_PER_COMPETITOR = 6
EXCERPT_CHARS = 1200
LOOKBACK_DAYS = 540
MAX_FINDINGS = 15

#: A "name" longer than this is prose (a positioning sentence), not a competitor.
MAX_NAME_WORDS = 6
MAX_NAME_CHARS = 80

_SPLIT_RE = re.compile(r"[\n;,|]+|(?:\s+vs\.?\s+)", re.IGNORECASE)
_LEADING_NOISE_RE = re.compile(r"^\s*(?:[-*•–—]+|\d+[.)])\s*")

#: Claims a web-search API cannot substantiate. Named, not silently guessed.
FIELDS_NOT_PROVIDED = [
    "traffic",
    "ad_spend",
    "share_of_voice",
    "keyword_rankings",
    "revenue",
]

CATEGORIES = {
    "messaging_theme",
    "content_gap",
    "positioning",
    "offer",
    "channel",
    "launch",
}
DEFAULT_CATEGORY = "observation"

PROVENANCE_NOTE = (
    "Every finding is tied to a document retrieved from Exa web search and is "
    "labelled with that document's URL, publication date (when the publisher "
    "provides one) and the retrieval timestamp. Model claims that could not be "
    "matched to a retrieved document were dropped, not published. Exa returns "
    "no traffic, spend, share-of-voice or ranking data, so those are omitted."
)

NO_COMPETITOR_HINT = (
    "Pass an explicit competitor list in the request body "
    '(e.g. {"competitors": "Acme, Globex"}) or set the client\'s brand profile '
    "competitor field to a comma-separated list of names."
)


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Explicit unavailable payload — never invented findings."""
    return exa_client.unavailable(reason, findings=[], **extra)


def parse_competitors(competitor_info: str) -> list[str]:
    """Extract competitor names from free-form input.

    Splits on the separators a human actually uses, strips bullets/numbering, and
    keeps only short name-like fragments. Prose ("we differentiate on service
    quality") yields no names — which surfaces as an honest "not available"
    instead of a search for a sentence.
    """
    if not isinstance(competitor_info, str):
        return []

    names: list[str] = []
    seen: set[str] = set()
    for chunk in _SPLIT_RE.split(competitor_info):
        candidate = _LEADING_NOISE_RE.sub("", chunk or "").strip()
        # "Acme - the incumbent" / "Acme: enterprise tier" → "Acme"
        candidate = re.split(r"\s+[-–—]\s+|\s*:\s+", candidate)[0].strip()
        candidate = candidate.strip("\"'.()[] \t")
        if not candidate or len(candidate) > MAX_NAME_CHARS:
            continue
        if len(candidate.split()) > MAX_NAME_WORDS:
            continue
        if len(candidate) < 2:
            continue
        key = candidate.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(candidate)
        if len(names) >= MAX_COMPETITORS:
            break
    return names


def build_query(name: str, industry: str = "") -> str:
    """The exact search string sent to Exa, surfaced in the response for auditability."""
    sector = f" in the {industry} industry" if industry.strip() else ""
    return (
        f"{name}{sector}: recent marketing campaigns, product announcements, "
        "positioning and brand messaging"
    )


def _map_source(
    raw: Any, *, competitor: str, source_id: str, retrieved_at: str
) -> dict[str, Any] | None:
    """Map one Exa result to a source record, or None when it carries nothing usable."""
    if not isinstance(raw, dict):
        return None
    url = (raw.get("url") or "").strip()
    if not exa_client.is_resolvable_url(url):
        return None
    title = (raw.get("title") or "").strip()
    text = raw.get("text")
    excerpt = text.strip()[:EXCERPT_CHARS] if isinstance(text, str) and text.strip() else None
    if not title and not excerpt:
        return None

    published_raw = raw.get("publishedDate")
    return {
        "id": source_id,
        "competitor": competitor,
        "title": title or url,
        "url": url,
        "domain": exa_client.host(url),
        "published_date": published_raw if isinstance(published_raw, str) else None,
        "retrieved_at": retrieved_at,
        "excerpt": excerpt,
    }


async def _search_competitor(api_key: str, name: str, industry: str) -> dict[str, Any]:
    """One Exa search for one competitor, with page text where the publisher allows it."""
    start_date = (datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    payload: dict[str, Any] = {
        "query": build_query(name, industry),
        "numResults": RESULTS_PER_COMPETITOR,
        "type": "auto",
        "startPublishedDate": start_date,
        "contents": {"text": {"maxCharacters": EXCERPT_CHARS}},
    }
    return await exa_client.search(api_key, payload, label="competitive_search")


async def gather_sources(
    api_key: str, names: list[str], industry: str
) -> tuple[list[dict[str, Any]], dict[str, str], list[str], int | None]:
    """Retrieve real documents for each competitor.

    Returns ``(sources, queries, errors, auth_status)``. ``auth_status`` is set
    when Exa rejects the key, which is fatal for the whole scan.
    """
    sources: list[dict[str, Any]] = []
    queries: dict[str, str] = {}
    errors: list[str] = []
    retrieved_at = datetime.now(UTC).isoformat()

    for name in names:
        queries[name] = build_query(name, industry)
        try:
            body = await _search_competitor(api_key, name, industry)
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.warning("competitive_exa_http_error", competitor=name, status=status_code)
            if status_code in (401, 403):
                return [], queries, [exa_client.http_error_reason(e)], status_code
            errors.append(f"{name}: {exa_client.http_error_reason(e)}")
            continue
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("competitive_exa_request_error", competitor=name, error=str(e))
            errors.append(f"{name}: Exa search request failed: {e}")
            continue
        except Exception as e:  # noqa: BLE001 — never fabricate on unexpected errors
            logger.error("competitive_exa_unexpected_error", competitor=name, error=str(e))
            errors.append(f"{name}: Exa search failed: {e}")
            continue

        for raw in exa_client.results_of(body):
            source = _map_source(
                raw,
                competitor=name,
                source_id=f"S{len(sources) + 1}",
                retrieved_at=retrieved_at,
            )
            if source is not None:
                sources.append(source)

    return sources, queries, errors, None


def _render_sources(sources: list[dict[str, Any]]) -> str:
    blocks = []
    for source in sources:
        published = source["published_date"] or "publication date not provided"
        excerpt = source["excerpt"] or "(no page text retrieved)"
        blocks.append(
            f"[{source['id']}] competitor: {source['competitor']}\n"
            f"title: {source['title']}\n"
            f"url: {source['url']}\n"
            f"published: {published}\n"
            f"text: {excerpt}"
        )
    return "\n\n".join(blocks)


def build_prompt(brand_context: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    """Prompt the model to *summarize retrieved text*, not to recall facts."""
    return f"""You are a competitive intelligence analyst for a marketing agency.

Brand: {brand_context.get("brand_name", "Unknown")}
Industry: {brand_context.get("industry", "Unknown")}

Below are documents retrieved from a live web search. They are the ONLY evidence
you may use. Do not use anything you remember about these companies.

{_render_sources(sources)}

For each finding, state what the retrieved document shows and cite it by its
source id. Every finding MUST have a "source_id" from the list above and its
matching "source_url". Findings whose citation does not match a retrieved
document are discarded by the caller, so an uncited observation is wasted output.
Do not invent URLs. Do not cite a company homepage in place of the document.

Return JSON only:
{{
    "findings": [
        {{
            "source_id": "S1",
            "source_url": "<the exact url shown for that source>",
            "competitor": "...",
            "category": "messaging_theme|content_gap|positioning|offer|channel|launch",
            "claim": "what the document shows about the competitor",
            "evidence": "the phrase or detail in the document that supports it"
        }}
    ],
    "counter_campaigns": [
        {{
            "name": "...",
            "objective": "...",
            "channels": ["..."],
            "key_message": "...",
            "based_on": ["S1"]
        }}
    ],
    "strategy": "recommended response strategy, grounded in the findings above"
}}"""


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of the JSON object from a model response."""
    if not isinstance(text, str):
        return None
    body = text.strip()
    if "```" in body:
        parts = body.split("```")
        if len(parts) >= 2:
            body = parts[1]
            if body.lstrip().lower().startswith("json"):
                body = body.lstrip()[4:]
    body = body.strip()
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(body[start : end + 1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def ground_findings(
    raw_findings: Any, sources: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep only findings that resolve to a retrieved source. Returns ``(kept, dropped)``.

    This is the enforcement point for the whole module:

    * a claimed ``source_url`` counts only if it normalizes to the exact URL of a
      retrieved document — a plausible-looking or homepage URL resolves to nothing
      and the finding is dropped;
    * a ``source_id`` is honoured only when the model supplied no URL at all;
    * the emitted ``source_url`` is copied from the retrieved source record, so
      what a caller sees is a URL that was actually fetched, never a model string.
    """
    by_url: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for record in sources:
        normalized = exa_client.normalize_url(record["url"])
        if normalized:
            by_url.setdefault(normalized, record)
        by_id[str(record["id"]).upper()] = record

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for raw in raw_findings if isinstance(raw_findings, list) else []:
        if not isinstance(raw, dict):
            continue
        claim = str(raw.get("claim") or "").strip()
        if not claim:
            continue

        claimed_url = str(raw.get("source_url") or "").strip()
        claimed_id = str(raw.get("source_id") or "").strip().upper()

        cited: dict[str, Any] | None
        if claimed_url:
            claimed_normalized = exa_client.normalize_url(claimed_url)
            cited = by_url.get(claimed_normalized) if claimed_normalized else None
        else:
            cited = by_id.get(claimed_id) if claimed_id else None

        if cited is None:
            dropped.append({"claim": claim, "claimed_source_url": claimed_url or None})
            continue

        category = str(raw.get("category") or "").strip().lower()
        evidence = str(raw.get("evidence") or "").strip()
        kept.append(
            {
                "competitor": cited["competitor"],
                "category": category if category in CATEGORIES else DEFAULT_CATEGORY,
                "claim": claim,
                "evidence": evidence or None,
                "source_id": cited["id"],
                "source_url": cited["url"],
                "source_title": cited["title"],
                "source_domain": cited["domain"],
                "published_date": cited["published_date"],
                "retrieved_at": cited["retrieved_at"],
            }
        )
        if len(kept) >= MAX_FINDINGS:
            break

    return kept, dropped


def _ground_counter_campaigns(
    raw_campaigns: Any, sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keep campaign ideas, but resolve their ``based_on`` ids to real source URLs."""
    by_id = {str(s["id"]).upper(): s for s in sources}
    campaigns: list[dict[str, Any]] = []
    for raw in raw_campaigns if isinstance(raw_campaigns, list) else []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        based_on = raw.get("based_on")
        ids = [str(i).strip().upper() for i in based_on] if isinstance(based_on, list) else []
        channels = raw.get("channels")
        campaigns.append(
            {
                "name": name,
                "objective": str(raw.get("objective") or "").strip() or None,
                "channels": [str(c) for c in channels] if isinstance(channels, list) else [],
                "key_message": str(raw.get("key_message") or "").strip() or None,
                "based_on_urls": [by_id[i]["url"] for i in ids if i in by_id],
            }
        )
    return campaigns


async def run_competitive_scan(
    competitor_info: str,
    brand_context: dict[str, Any],
) -> dict[str, Any]:
    """Scan named competitors against retrieved public sources.

    Order matters: no key or no retrieved source means no LLM call at all. The
    model is only ever invoked to summarize text that was actually fetched.
    """
    names = parse_competitors(competitor_info or "")
    if not names:
        logger.info("competitive_no_competitor_named")
        return _unavailable(
            f"No competitor names could be identified from the request. {NO_COMPETITOR_HINT}",
            sources=[],
        )

    api_key = exa_client.get_api_key()
    if not api_key:
        logger.info("competitive_exa_not_configured", competitors=names)
        return _unavailable(
            "Competitive intelligence needs a retrieval source and Exa is not "
            f"configured. {exa_client.SETUP_HINT}",
            competitors=names,
            sources=[],
        )

    industry = str(brand_context.get("industry") or "")
    sources, queries, errors, auth_status = await gather_sources(api_key, names, industry)

    if auth_status is not None:
        return _unavailable(
            errors[0] if errors else f"Exa rejected the API key (HTTP {auth_status}).",
            competitors=names,
            queries=queries,
            http_status=auth_status,
            sources=[],
        )

    if not sources:
        reason = "Exa returned no usable sources for these competitors."
        if errors:
            reason = f"{reason} " + " ".join(errors)
        logger.info("competitive_no_sources", competitors=names)
        return _unavailable(
            reason,
            competitors=names,
            queries=queries,
            sources=[],
            retrieval_errors=errors,
        )

    llm = get_worker_llm()
    prompt = build_prompt(brand_context, sources)
    try:
        response = await llm.ainvoke(prompt)
    except Exception as e:  # noqa: BLE001 — an LLM failure must not become fake intel
        logger.error("competitive_llm_error", error=str(e))
        return _unavailable(
            f"Retrieved {len(sources)} sources but the analysis model failed: {e}",
            competitors=names,
            queries=queries,
            sources=sources,
            retrieval_errors=errors,
        )

    text = response.content if hasattr(response, "content") else str(response)
    parsed = parse_json_object(text if isinstance(text, str) else str(text))
    if parsed is None:
        logger.warning("competitive_llm_unparseable")
        return _unavailable(
            "The analysis model did not return usable JSON, so no sourced finding "
            "could be produced. The retrieved sources are listed for manual review.",
            competitors=names,
            queries=queries,
            sources=sources,
            retrieval_errors=errors,
        )

    findings, dropped = ground_findings(parsed.get("findings"), sources)
    if dropped:
        logger.warning(
            "competitive_dropped_unsourced_findings", count=len(dropped), kept=len(findings)
        )

    if not findings:
        return _unavailable(
            f"No finding could be tied to a retrieved source ({len(dropped)} unsourced "
            "claim(s) were dropped). The retrieved sources are listed for manual review.",
            competitors=names,
            queries=queries,
            sources=sources,
            dropped_unsourced_count=len(dropped),
            dropped_unsourced=dropped,
            retrieval_errors=errors,
        )

    strategy = str(parsed.get("strategy") or "").strip() or None
    logger.info(
        "competitive_scan_ok",
        competitors=names,
        sources=len(sources),
        findings=len(findings),
        dropped=len(dropped),
    )
    return {
        "status": "ok",
        "source": "exa_search",
        "retrieved_at": sources[0]["retrieved_at"],
        "competitors": names,
        "queries": queries,
        "sources": sources,
        "findings": findings,
        "dropped_unsourced_count": len(dropped),
        "dropped_unsourced": dropped,
        "recommendations": {
            "counter_campaigns": _ground_counter_campaigns(
                parsed.get("counter_campaigns"), sources
            ),
            "strategy": strategy,
            "note": (
                "Counter-campaigns and strategy are agency recommendations derived "
                "from the cited findings — they are advice, not retrieved facts."
            ),
        },
        "retrieval_errors": errors,
        "fields_not_provided": FIELDS_NOT_PROVIDED,
        "provenance": PROVENANCE_NOTE,
    }
