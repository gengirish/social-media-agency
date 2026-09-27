"""Shared plumbing for Create › Email and Create › Launch (Cadence parity).

Every generator here follows one sequence, so the order lives in one place:

    client (org-resolved, 404) → brand profile (409) → quota (402)
    → model call (502 on failure) → shape validation (502 on malformed output)
    → ``save_asset`` → ``charge_generation`` → commit

A malformed or failed generation is never partially saved and never charged —
charging for our failure would bill the user for it.

Nothing produced here is sent anywhere. CampaignForge has no email service
provider, Product Hunt, press-list, Discord/Slack or CRM integration for these
outputs: they are drafts the human copies into the tool they already use
(product rule 1). ``services/email_service.py`` is the app's own transactional
mail (AgentMail) and is deliberately not used to send marketing email to a
client's customers.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import BrandProfile, Client
from agency.services.creative_assets import asset_out, save_asset
from agency.services.generation_quota import charge_generation, require_generation_quota

logger = structlog.get_logger()

BRAND_PROFILE_REQUIRED = "brand_profile_required"

#: Cadence's EMAIL_CAMPAIGN_TYPES, verbatim: type → what the email is for.
EMAIL_CAMPAIGN_TYPES: dict[str, str] = {
    "welcome": (
        "a Day-0 welcome email sent right after signup — first impression, sets "
        "expectations, one clear next step"
    ),
    "onboarding": (
        "a Day-3-5 onboarding nudge for users who signed up but haven't taken the key "
        "activation action yet"
    ),
    "reengagement": (
        "a win-back email for users who were active but have gone quiet — re-establish "
        "value, low-pressure ask"
    ),
    "update": (
        "a product update/newsletter announcing a new feature or improvement to the "
        "existing user base"
    ),
    "milestone": (
        "a celebratory email marking a usage milestone the user just hit — reinforce "
        "the win, suggest a natural next step"
    ),
}

#: Launch-screen modes → the asset kind each one saves as.
LAUNCH_MODES: dict[str, str] = {
    "launch_kit": "launch_kit",
    "community_kit": "community_kit",
    "outreach_pitch": "outreach_pitch",
}

MAX_FIELD_CHARS = 6000
MAX_LIST_ITEMS = 10


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------
async def require_brand_profile(db: AsyncSession, client: Client, org_id: UUID) -> None:
    """409 unless the client has a brand profile — Cadence's ``profile.approved`` gate.

    Generating from an empty profile produces generic copy the prompts are
    written to avoid; the UI links to Setup › Profile on this code.
    """
    exists = (
        await db.execute(
            select(BrandProfile.id).where(
                BrandProfile.client_id == client.id, BrandProfile.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": BRAND_PROFILE_REQUIRED,
                "message": "Set up this client's brand profile before generating.",
            },
        )


# ---------------------------------------------------------------------------
# Shape validation — the model output is never trusted to have obeyed
# ---------------------------------------------------------------------------
class ShapeError(ValueError):
    """The model returned JSON that does not match the requested shape."""


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _pick(data: dict[str, Any], key: str) -> Any:
    """The camelCase key the prompt asks for, or its snake_case spelling."""
    if key in data:
        return data[key]
    return data.get(_snake(key))


def _text(data: dict[str, Any], key: str) -> str:
    value = _pick(data, key)
    if not isinstance(value, str) or not value.strip():
        raise ShapeError(f"{key} must be a non-empty string")
    return value.strip()[:MAX_FIELD_CHARS]


def _text_list(data: dict[str, Any], key: str, *, min_items: int = 1) -> list[str]:
    value = _pick(data, key)
    if not isinstance(value, list):
        raise ShapeError(f"{key} must be a list")
    items = [str(v).strip()[:MAX_FIELD_CHARS] for v in value if isinstance(v, str) and v.strip()]
    if len(items) < min_items:
        raise ShapeError(f"{key} needs at least {min_items} non-empty item(s)")
    return items[:MAX_LIST_ITEMS]


def _qa_list(data: dict[str, Any], key: str) -> list[dict[str, str]]:
    value = _pick(data, key)
    if not isinstance(value, list):
        raise ShapeError(f"{key} must be a list")
    out: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            q, a = item.get("question"), item.get("answer")
            if isinstance(q, str) and q.strip() and isinstance(a, str) and a.strip():
                out.append({"question": q.strip(), "answer": a.strip()})
    if not out:
        raise ShapeError(f"{key} needs at least one question/answer pair")
    return out[:MAX_LIST_ITEMS]


def _require_dict(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ShapeError("expected a JSON object")
    return raw


def validate_email_campaign(raw: Any, campaign_type: str) -> dict[str, Any]:
    data = _require_dict(raw)
    return {
        "campaign_type": campaign_type,
        "subject_line": _text(data, "subjectLine"),
        "subject_line_b": _text(data, "subjectLineB"),
        "preview_text": _text(data, "previewText"),
        "segment_note": _text(data, "segmentNote"),
        "send_time_note": _text(data, "sendTimeNote"),
        "body": _text(data, "body"),
    }


def validate_prfaq(raw: Any) -> dict[str, Any]:
    data = _require_dict(raw)
    return {
        "press_release_headline": _text(data, "pressReleaseHeadline"),
        "press_release_body": _text(data, "pressReleaseBody"),
        "customer_faq": _qa_list(data, "customerFAQ"),
        "internal_faq": _qa_list(data, "internalFAQ"),
        "weakest_claim": _text(data, "weakestClaim"),
        "sharper_version_note": _text(data, "sharperVersionNote"),
    }


def validate_launch_kit(raw: Any) -> dict[str, Any]:
    data = _require_dict(raw)
    return {
        "tagline": _text(data, "tagline"),
        "ph_description": _text(data, "phDescription"),
        "maker_comment": _text(data, "makerComment"),
        "launch_timing_note": _text(data, "launchTimingNote"),
        "why_now_hook": _text(data, "whyNowHook"),
        "press_pitch_subject": _text(data, "pressPitchSubject"),
        "press_pitch_body": _text(data, "pressPitchBody"),
    }


def validate_community_kit(raw: Any) -> dict[str, Any]:
    data = _require_dict(raw)
    return {
        "channel_structure": _text_list(data, "channelStructure"),
        "welcome_message": _text(data, "welcomeMessage"),
        "engagement_prompts": _text_list(data, "engagementPrompts"),
        "event_announcement_template": _text(data, "eventAnnouncementTemplate"),
        "moderation_note": _text(data, "moderationNote"),
    }


def validate_outreach_pitch(raw: Any) -> dict[str, Any]:
    data = _require_dict(raw)
    return {
        "target_type": _text(data, "targetType"),
        "subject": _text(data, "subject"),
        "pitch_body": _text(data, "pitchBody"),
        "specific_ask": _text(data, "specificAsk"),
        "economics_note": _text(data, "economicsNote"),
    }


#: Asset title per kind — what the list search matches on.
ASSET_TITLE_KEY: dict[str, str] = {
    "email_campaign": "subject_line",
    "launch_kit": "tagline",
    "outreach_pitch": "subject",
}


def asset_title(kind: str, payload: dict[str, Any]) -> str:
    if kind == "community_kit":
        channels = payload.get("channel_structure") or []
        return str(channels[0]) if channels else "Community kit"
    return str(payload.get(ASSET_TITLE_KEY.get(kind, ""), "") or kind)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
async def run_generation(
    *,
    org_id: UUID,
    label: str,
    produce: Callable[[], Awaitable[Any]],
    validate: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    """Call the model and validate its output; 502 (no charge) on either failure."""
    try:
        raw = await produce()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"{label}_generation_failed", org_id=str(org_id), error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Generation failed; no quota was used. Try again."
        ) from None
    try:
        return validate(raw)
    except ShapeError as exc:
        logger.warning(f"{label}_generation_malformed", org_id=str(org_id), error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The model returned an incomplete draft; no quota was used. Try again.",
        ) from None


async def generate_asset(
    db: AsyncSession,
    *,
    org_id: UUID,
    client: Client,
    kind: str,
    produce: Callable[[], Awaitable[Any]],
    validate: Callable[[Any], dict[str, Any]],
    created_by: Any = None,
) -> dict[str, Any]:
    """Quota → generate → validate → save → charge → commit. Client must be org-resolved."""
    await require_generation_quota(db, org_id)
    payload = await run_generation(org_id=org_id, label=kind, produce=produce, validate=validate)
    asset = await save_asset(
        db,
        org_id=org_id,
        client_id=client.id,  # type: ignore[arg-type]
        kind=kind,
        title=asset_title(kind, payload),
        payload=payload,
        created_by=created_by,
    )
    await charge_generation(db, org_id)
    await db.commit()
    await db.refresh(asset)
    return asset_out(asset)
