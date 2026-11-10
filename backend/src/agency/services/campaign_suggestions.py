"""Campaign suggestions — 2–3 ready-to-use briefs for the New Campaign form.

The user picks a client, asks for suggestions, picks one; the form fills and
they still edit it and press Launch themselves (product rule 2). Nothing here
creates a campaign or saves anything: like Amplify's ``preview`` the result
lives only in the response.

Sequence (the shared generator pattern, minus ``save_asset``):

    client (org-resolved, 404) → brand profile (409) → quota (402)
    → angles planned in code → model call (502) → disconnected? (409, nothing charged)
    → per-suggestion validation → fewer than 2 survive? (502) → charge → commit

Angles are assigned **in code** (:func:`plan_angles`), like
``repurpose.plan_atoms``: the model writes one brief per assigned angle and the
validator forces each brief's ``angle`` back to the one it was given, so a
response cannot come back as three variations of the same campaign.

Product rule 4 — no invented numbers — is enforced on ``objective`` and
``rationale`` by :func:`claims_predicted_result`: a suggestion that forecasts an
outcome ("expected 30% lift", "will reach 10k people", a predicted CTR) is
dropped, not edited. A stated goal ("grow demo bookings") is fine.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents.lifecycle_email import llm_text
from agency.agents.utils import parse_llm_json
from agency.models.schemas import CampaignSuggestionRequest, reject_field_label
from agency.models.tables import Campaign
from agency.services.brand_context import brand_prompt_block, get_org_client, load_brand_context
from agency.services.create_kits import require_brand_profile
from agency.services.generation_quota import charge_generation, require_generation_quota
from agency.services.llm_provider import get_worker_llm
from agency.services.tracing import trace_config

logger = structlog.get_logger()

CancelCheck = Callable[[], Awaitable[bool]]

SUGGESTION_TEMPERATURE = 0.7

#: The closed angle enum, in the order they are offered.
ANGLES: tuple[str, ...] = ("launch_offer", "thought_leadership", "community", "timely")
#: How many angles one request asks the model for.
ANGLES_PER_REQUEST = 3
#: Fewer surviving suggestions than this is a failed generation (502, no charge).
MIN_SUGGESTIONS = 2
#: Past campaigns shown to the model so it does not repeat one.
PAST_CAMPAIGN_LIMIT = 10

#: Organic channels only. Paid ad networks stay opt-in on the brief form and are
#: never proposed by a model (CF-04, ``agents/ad_copy.py``): an ad channel spends
#: a budget nobody approved.
ORGANIC_CHANNELS: tuple[str, ...] = ("linkedin", "twitter", "instagram", "facebook", "tiktok")
_CHANNEL_ALIASES: dict[str, str] = {
    "x": "twitter",
    "x (twitter)": "twitter",
    "twitter/x": "twitter",
}

NAME_MIN, NAME_MAX = 3, 80
OBJECTIVE_MIN, OBJECTIVE_MAX = 10, 500
RATIONALE_MAX = 400
AUDIENCE_MAX = 500
CONTEXT_MAX = 2000
KEY_MESSAGE_MAX = 300
KEY_MESSAGES_MAX_ITEMS = 5

ANGLE_BRIEFS: dict[str, str] = {
    "launch_offer": (
        "a launch or offer campaign around something the brand sells or is releasing. "
        "Only reference products, offers or prices that appear in the brand context or the "
        "user's note; otherwise use a bracketed placeholder like [Offer details]"
    ),
    "thought_leadership": (
        "a thought-leadership campaign: the brand's point of view, expertise or lessons, "
        "aimed at earning trust rather than selling"
    ),
    "community": (
        "a community campaign: customers, users or the local/industry community at the "
        "centre — conversations, stories, participation"
    ),
    "timely": (
        "a timely campaign tied to something that actually falls inside the window — the "
        "season, a widely observed date, the brand's active campaign or the user's note. "
        "Never invent an event, launch, partnership or news item"
    ),
}

#: Words that suggest which angle a past campaign took. Used only to decide which
#: angle to leave out, so a rough match is enough.
_ANGLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "launch_offer": (
        "launch", "offer", "discount", "promo", "promotion", "sale", "release", "introducing",
        "trial", "deal", "pricing", "new product", "product",
    ),
    "thought_leadership": (
        "thought leadership", "insight", "insights", "expert", "expertise", "guide", "education",
        "educate", "webinar", "report", "lessons", "how to", "authority", "pov",
    ),
    "community": (
        "community", "customer stories", "customers", "users", "ugc", "ambassador", "members",
        "meetup", "spotlight", "advocacy", "testimonial", "testimonials",
    ),
    "timely": (
        "season", "seasonal", "holiday", "holidays", "christmas", "diwali", "black friday",
        "new year", "summer", "winter", "back to school", "festival", "anniversary", "trend",
        "trending",
    ),
}

#: Dropped when no past campaign points elsewhere: it is the angle that leans
#: hardest on outside events, which the product has no live data about.
DEFAULT_DROPPED_ANGLE = "timely"


# ---------------------------------------------------------------------------
# Angle planning — pure
# ---------------------------------------------------------------------------
def resembles_angle(text: str) -> str | None:
    """The angle ``text`` (a past campaign's name + objective) most looks like, or ``None``.

    Counts whole-word keyword hits per angle; ties go to the earlier angle in
    :data:`ANGLES`. No hit at all is ``None``.
    """
    lowered = text.lower()
    best: str | None = None
    best_score = 0
    for angle in ANGLES:
        score = sum(
            1
            for kw in _ANGLE_KEYWORDS[angle]
            if re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", lowered)
        )
        if score > best_score:
            best, best_score = angle, score
    return best


def plan_angles(past_campaigns: list[dict[str, Any]]) -> list[str]:
    """Three distinct angles for this request, in :data:`ANGLES` order.

    Drops the angle the **most recent** past campaign most resembles, so the
    suggestions do not open with a rerun of what the client just did. With no
    past campaign, or one that matches nothing, :data:`DEFAULT_DROPPED_ANGLE`
    is dropped. Deterministic: same history, same angles.
    """
    dropped = DEFAULT_DROPPED_ANGLE
    if past_campaigns:
        latest = past_campaigns[0]
        match = resembles_angle(f"{latest.get('name', '')} {latest.get('objective', '')}")
        if match is not None:
            dropped = match
    return [a for a in ANGLES if a != dropped][:ANGLES_PER_REQUEST]


# ---------------------------------------------------------------------------
# No invented numbers — pure
# ---------------------------------------------------------------------------
#: A quantity that reads as a result: a percentage, a multiplier, a k/m/million
#: count, a money amount or a number of four or more digits. A bare "3" (as in
#: "3 posts a week") is not one.
_NUMBER = (
    r"(?:\$\s*\d[\d,.]*|\d[\d,.]*\s*(?:%|percent\b|x\b|k\b|m\b|million\b|thousand\b)"
    r"|\d{1,3}(?:,\d{3})+|\d{4,})"
)
#: Words that turn a number into a forecast of what the campaign will achieve.
_FORECAST_CUE = re.compile(
    r"\b(?:expect(?:ed|s)?|projected|projection|predict(?:ed|s|ion)?|forecast(?:ed|s)?"
    r"|estimated?|likely\s+to|on\s+track\s+to|guarantee(?:d|s)?"
    r"|(?:will|should|could|would)\s+(?:help\s+)?(?:reach|generate|drive|increase|boost|grow"
    r"|double|triple|achieve|yield|lift|attract|earn|result\s+in|lead\s+to|hit|exceed|gain))\b",
    re.IGNORECASE,
)
#: A named performance metric next to a number is a prediction on its own — the
#: product never predicts CTR, CPC, ROAS or engagement (product rule 4).
_METRIC_WITH_NUMBER = re.compile(
    rf"(?:\b(?:ctr|cpc|cpm|cpa|roas|roi|click[- ]through(?:\s+rate)?|engagement\s+rate"
    rf"|conversion\s+rate|open\s+rate|impressions)\b[^.;\n]{{0,40}}{_NUMBER}"
    rf"|{_NUMBER}[^.;\n]{{0,40}}\b(?:ctr|cpc|cpm|cpa|roas|roi|click[- ]through(?:\s+rate)?"
    rf"|engagement\s+rate|conversion\s+rate|open\s+rate|impressions)\b)",
    re.IGNORECASE,
)
#: "will double sign-ups" forecasts without a digit.
_WORDED_FORECAST = re.compile(
    r"\b(?:will|should|could|would)\s+(?:help\s+)?(?:double|triple|quadruple|10x|2x|3x)\b",
    re.IGNORECASE,
)
_DIGIT = re.compile(r"\d")


def claims_predicted_result(text: str) -> bool:
    """True when ``text`` forecasts an outcome rather than stating a goal.

    Checked sentence by sentence. A sentence is a forecast when it:

    * pairs a number with a forecast cue ("expected", "projected", "will reach",
      "should drive", "likely to", ...), or
    * puts a performance metric (CTR, ROAS, engagement rate, impressions, ...)
      within a few words of a number, or
    * says the campaign will double/triple something.

    "Grow demo bookings by 20%" is a goal and passes; "expected to grow demo
    bookings by 20%" is a forecast and does not.
    """
    if not text:
        return False
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text):
        if _WORDED_FORECAST.search(sentence) or _METRIC_WITH_NUMBER.search(sentence):
            return True
        if _DIGIT.search(sentence) and _FORECAST_CUE.search(sentence):
            return True
    return False


# ---------------------------------------------------------------------------
# Validation — the model output is never trusted to have obeyed
# ---------------------------------------------------------------------------
class SuggestionRejectedError(ValueError):
    """One suggestion is unusable; the others may still be returned."""


def _clip(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` chars at a sentence, else a word, boundary."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    sentence_end = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if sentence_end >= limit // 2:
        return head[: sentence_end + 1].strip()
    space = head.rfind(" ")
    return (head[:space] if space > 0 else head).rstrip(" ,;:-")


def _string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def _not_label(value: str, field: str) -> str:
    try:
        return reject_field_label(value, field)
    except ValueError as exc:
        raise SuggestionRejectedError(f"{field} is a form label") from exc


def normalise_channels(raw: Any) -> list[str]:
    """Organic channels only, lower-cased and de-duplicated. Anything else is dropped."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        name = item.strip().lower()
        name = _CHANNEL_ALIASES.get(name, name)
        if name in ORGANIC_CHANNELS and name not in out:
            out.append(name)
    return out


def _parse_date(value: Any) -> date | None:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def repair_dates(raw_start: Any, raw_end: Any, window: tuple[date, date]) -> tuple[date, date]:
    """Dates clamped into the window; missing or unparseable ones take the window's edge."""
    lo, hi = window
    start = _parse_date(raw_start) or lo
    end = _parse_date(raw_end) or hi
    start = min(max(start, lo), hi)
    end = min(max(end, lo), hi)
    return start, max(start, end)


def validate_suggestion(
    data: Any, angle: str, window: tuple[date, date], past_names: set[str]
) -> dict[str, Any]:
    """One suggestion, repaired where safe, or :class:`SuggestionRejectedError`."""
    if not isinstance(data, dict):
        raise SuggestionRejectedError("not an object")

    name = _not_label(_string(data, "campaign_name"), "campaign_name")
    if not NAME_MIN <= len(name) <= NAME_MAX:
        raise SuggestionRejectedError("campaign_name length")
    if name.lower() in past_names:
        raise SuggestionRejectedError("repeats a past campaign's name")

    objective = _not_label(_string(data, "objective"), "objective")
    objective = _clip(objective, OBJECTIVE_MAX)
    if len(objective) < OBJECTIVE_MIN:
        raise SuggestionRejectedError("objective too short")

    rationale = _clip(_string(data, "rationale"), RATIONALE_MAX)
    if not rationale:
        raise SuggestionRejectedError("rationale missing")

    if claims_predicted_result(objective) or claims_predicted_result(rationale):
        raise SuggestionRejectedError("claims a predicted result")

    audience = _clip(_not_label(_string(data, "target_audience"), "target_audience"), AUDIENCE_MAX)
    context = _clip(
        _not_label(_string(data, "additional_context"), "additional_context"), CONTEXT_MAX
    )
    # Key messages and context reach the brief too, so a forecast there is the same
    # rule-4 problem: a forecasting message is dropped, forecasting context drops all.
    if claims_predicted_result(context):
        raise SuggestionRejectedError("claims a predicted result")

    raw_messages = data.get("key_messages")
    messages: list[str] = []
    if isinstance(raw_messages, list):
        for m in raw_messages:
            if not isinstance(m, str) or not m.strip() or claims_predicted_result(m):
                continue
            try:
                messages.append(_clip(_not_label(m.strip(), "key_messages"), KEY_MESSAGE_MAX))
            except SuggestionRejectedError:
                continue  # a label in the list is dropped, not the whole suggestion
    messages = messages[:KEY_MESSAGES_MAX_ITEMS]
    if not messages:
        raise SuggestionRejectedError("no key messages")

    channels = normalise_channels(data.get("channels"))
    if not channels:
        raise SuggestionRejectedError("no organic channels")

    start, end = repair_dates(data.get("start_date"), data.get("end_date"), window)
    return {
        "angle": angle,  # forced: the model does not choose angles
        "campaign_name": name,
        "objective": objective,
        "target_audience": audience,
        "key_messages": messages,
        "channels": channels,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "additional_context": context,
        "rationale": rationale,
    }


def _items(raw: Any) -> list[Any]:
    if isinstance(raw, dict):
        raw = raw.get("suggestions")
    return raw if isinstance(raw, list) else []


def validate_suggestions(
    raw: Any,
    angles: list[str],
    window: tuple[date, date],
    past_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Every usable suggestion, one per assigned angle, in angle order.

    An item is matched to its angle by the ``angle`` it reports when that is one
    of the assigned angles, otherwise by position. Its ``angle`` is then forced
    to the assigned one. Unusable items are dropped and logged; the caller
    decides whether enough survived.
    """
    items = _items(raw)
    past = past_names or set()
    by_angle: dict[str, Any] = {}
    unclaimed: list[Any] = []
    for item in items:
        reported = item.get("angle") if isinstance(item, dict) else None
        if isinstance(reported, str) and reported in angles and reported not in by_angle:
            by_angle[reported] = item
        else:
            unclaimed.append(item)
    for angle in angles:
        if angle not in by_angle and unclaimed:
            by_angle[angle] = unclaimed.pop(0)

    out: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for angle in angles:
        if angle not in by_angle:
            continue
        try:
            suggestion = validate_suggestion(by_angle[angle], angle, window, past)
        except SuggestionRejectedError as exc:
            logger.info("campaign_suggestion_dropped", angle=angle, reason=str(exc))
            continue
        key = suggestion["campaign_name"].lower()
        if key in seen_names:
            logger.info("campaign_suggestion_dropped", angle=angle, reason="duplicate name")
            continue
        seen_names.add(key)
        out.append(suggestion)
    return out


# ---------------------------------------------------------------------------
# Data + prompt
# ---------------------------------------------------------------------------
async def load_past_campaigns(
    db: AsyncSession, *, org_id: UUID, client_id: UUID, limit: int = PAST_CAMPAIGN_LIMIT
) -> list[dict[str, Any]]:
    """The client's most recent campaigns, newest first.

    Filters on **both** ``org_id`` and ``client_id``: there is no row-level
    security, and a row stamped with another org but this client's id must not
    leak another tenant's campaign into this prompt.
    """
    rows = (
        await db.execute(
            select(Campaign.name, Campaign.objective, Campaign.start_date, Campaign.end_date)
            .where(Campaign.org_id == org_id, Campaign.client_id == client_id)
            .order_by(Campaign.start_date.desc(), Campaign.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "name": r.name or "",
            "objective": r.objective or "",
            "start_date": r.start_date.isoformat() if r.start_date else "",
            "end_date": r.end_date.isoformat() if r.end_date else "",
        }
        for r in rows
    ]


SYSTEM_PROMPT = (
    "You are a campaign strategist proposing marketing campaigns for the brand described by "
    "the user. A human will review, edit and launch whichever one they pick. Never invent "
    "customers, metrics, prices, partnerships, events or quotes that are not in the brand "
    "context or the user's note. Never forecast results: no predicted reach, lift, CTR, "
    "engagement, conversions or ROI — state goals, not predictions. Return ONLY JSON, no "
    "markdown fences."
)


def build_prompt(
    brand: dict[str, Any],
    *,
    angles: list[str],
    window: tuple[date, date],
    past_campaigns: list[dict[str, Any]],
    hint: str | None,
) -> str:
    start, end = window
    past = (
        "\n".join(
            f"- {p['name']} ({p['start_date']} to {p['end_date']}): {p['objective'][:200]}"
            for p in past_campaigns
        )
        or "- none yet"
    )
    note = f"\n\n## The user's note\n{hint}\n" if hint else ""
    angle_lines = "\n".join(f'{i + 1}. "{a}" — {ANGLE_BRIEFS[a]}' for i, a in enumerate(angles))
    return (
        f"## Brand\n{brand_prompt_block(brand)}\n"
        "(Where an active campaign is listed, let it shape the suggestions where it fits.)\n\n"
        f"## Campaign window\n{start.isoformat()} to {end.isoformat()} (inclusive). Every "
        "campaign's start_date and end_date must fall inside it.\n\n"
        f"## Past campaigns for this client (do not repeat these)\n{past}"
        f"{note}\n\n"
        f"## Write exactly {len(angles)} campaigns, one per angle, in this order\n"
        f"{angle_lines}\n\n"
        "Each must be genuinely different from the others and from the past campaigns.\n"
        "Rules:\n"
        f"- campaign_name: {NAME_MIN}-{NAME_MAX} characters.\n"
        f"- objective: one or two sentences, {OBJECTIVE_MIN}-{OBJECTIVE_MAX} characters, a goal "
        "(e.g. \"grow demo bookings among ops leads\"), never a forecast.\n"
        f"- key_messages: 1-{KEY_MESSAGES_MAX_ITEMS} short messages.\n"
        f"- channels: only from {', '.join(ORGANIC_CHANNELS)}. No paid ad channels.\n"
        "- dates: YYYY-MM-DD inside the window.\n"
        "- additional_context: guardrails and notes for the writers (what to avoid, what to "
        "reference).\n"
        f"- rationale: at most {RATIONALE_MAX} characters — why this campaign for this brand "
        "now. No predicted numbers.\n\n"
        'Return ONLY JSON: {"suggestions": [{"angle": string, "campaign_name": string, '
        '"objective": string, "target_audience": string, "key_messages": string[], '
        '"channels": string[], "start_date": string, "end_date": string, '
        '"additional_context": string, "rationale": string}]}'
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def reply_diagnostics(response: Any, text: str, raw: Any) -> dict[str, Any]:
    """Shape of a model reply, for the log line of a failed generation.

    Which model answered matters because the tier's fallbacks switch providers
    silently: a primary that errors is replaced without any log. The text head is
    capped and goes only to server logs, never to the client.
    """
    meta = getattr(response, "response_metadata", None) or {}
    usage = getattr(response, "usage_metadata", None) or {}
    content = getattr(response, "content", None)
    blocks = (
        [b.get("type") if isinstance(b, dict) else type(b).__name__ for b in content]
        if isinstance(content, list)
        else type(content).__name__
    )
    return {
        "reply_model": meta.get("model") or meta.get("model_name"),
        "stop_reason": meta.get("stop_reason") or meta.get("finish_reason"),
        "output_tokens": usage.get("output_tokens"),
        "content_blocks": blocks,
        "text_len": len(text),
        "parsed_shape": sorted(raw.keys())[:5] if isinstance(raw, dict) else type(raw).__name__,
        "text_head": text[:300],
    }


def _bad_gateway(message: str) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, message)


def _cancelled() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {"code": "cancelled", "message": "Cancelled — nothing was saved and no quota was used."},
    )


async def suggest_campaigns(
    db: AsyncSession,
    *,
    org_id: UUID,
    body: CampaignSuggestionRequest,
    cancelled: CancelCheck | None = None,
) -> dict[str, Any]:
    """Generate 2–3 briefs. Saves nothing; charges one generation on success only."""
    client = await get_org_client(db, body.client_id, org_id)
    await require_brand_profile(db, client, org_id)
    await require_generation_quota(db, org_id)

    assert body.start_date is not None and body.end_date is not None  # resolved by the schema
    window = (body.start_date, body.end_date)
    brand = await load_brand_context(db, client, org_id)
    past = await load_past_campaigns(db, org_id=org_id, client_id=client.id)  # type: ignore[arg-type]
    angles = plan_angles(past)
    prompt = build_prompt(
        brand, angles=angles, window=window, past_campaigns=past, hint=body.hint
    )

    try:
        llm = get_worker_llm(SUGGESTION_TEMPERATURE)
        response = await llm.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)],
            config=trace_config("campaign-suggestions", org_id=org_id),
        )
        text = llm_text(response)
        raw = parse_llm_json(text)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("campaign_suggestions_failed", org_id=str(org_id), error=str(exc))
        raise _bad_gateway("Generation failed; no quota was used. Try again.") from None

    if cancelled is not None and await cancelled():
        logger.info("campaign_suggestions_cancelled", org_id=str(org_id))
        raise _cancelled()

    suggestions = validate_suggestions(
        raw, angles, window, {p["name"].strip().lower() for p in past if p["name"]}
    )
    if len(suggestions) < MIN_SUGGESTIONS:
        logger.warning(
            "campaign_suggestions_unusable",
            org_id=str(org_id),
            usable=len(suggestions),
            angles=angles,
            **reply_diagnostics(response, text, raw),
        )
        raise _bad_gateway(
            "The model did not return enough usable suggestions; no quota was used. Try again."
        )

    await charge_generation(db, org_id)
    await db.commit()
    return {
        "client_id": str(client.id),
        "window": {"start_date": window[0].isoformat(), "end_date": window[1].isoformat()},
        "suggestions": suggestions,
    }
