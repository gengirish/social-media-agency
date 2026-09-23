"""Setup › Profile and Setup › Accounts for one client — Cadence's IntakeScreen and ConnectScreen.

* ``GET  /setup/{client_id}/profile`` — intake answers, brand voice guide, campaign focus.
* ``PUT  /setup/{client_id}/profile`` — approve the intake (creates or merges; never wipes).
* ``POST /setup/{client_id}/profile/evaluate-answer`` — push-back coaching. Advisory and
  fail-open: a model failure reports ``available: false`` and the UI keeps the answer.
  Not charged — it is a check on the human's own words, not a generation.
* ``POST /setup/{client_id}/brand-voice/generate`` — a draft guide, returned for review and
  **not** saved. 1 generation.
* ``PUT  /setup/{client_id}/brand-voice`` — the human-approved guide, written into the profile.
* ``POST /setup/{client_id}/strategy-lens`` — run the panel, saved as a ``strategy_lens``
  creative asset (latest via ``GET /assets?kind=strategy_lens``). 1 generation.
* ``GET  /setup/{client_id}/accounts`` — this client's connected accounts, plus which
  platforms can be connected at all and the scopes each requests.

Tenancy: ``client_id`` is resolved against the caller's org before anything else.
The website scan itself is the existing ``POST /magic-brief`` (SSRF-guarded).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents.setup_profile import (
    evaluate_answer,
    generate_brand_voice,
    generate_strategy_lens,
)
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import PlatformAccount
from agency.routers.oauth import oauth_platform_status
from agency.services.brand_context import get_org_client, load_brand_context
from agency.services.creative_assets import asset_out, save_asset
from agency.services.generation_quota import charge_generation, require_generation_quota
from agency.services.setup_profile import (
    INTAKE_QUESTIONS,
    TONE_REGISTERS,
    apply_brand_voice,
    approve_intake,
    get_profile,
    intake_answers,
    profile_view,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/setup", tags=["Setup"])

MAX_ANSWER = 600


class ApproveProfileRequest(BaseModel):
    url: str | None = Field(default=None, max_length=500)
    audience: str = Field(min_length=1, max_length=MAX_ANSWER)
    differentiator: str = Field(min_length=1, max_length=MAX_ANSWER)
    tone: str

    @field_validator("tone")
    @classmethod
    def _known_tone(cls, v: str) -> str:
        if v not in TONE_REGISTERS:
            raise ValueError(f"tone must be one of {list(TONE_REGISTERS)}")
        return v

    @field_validator("audience", "differentiator")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v


class EvaluateAnswerRequest(BaseModel):
    question_id: Literal["audience", "differentiator"]
    answer: str = Field(min_length=1, max_length=MAX_ANSWER)


class BrandVoiceRequest(BaseModel):
    voice_description: str = Field(min_length=1, max_length=2000)
    vocabulary_include: list[str] = Field(default_factory=list, max_length=30)
    vocabulary_exclude: list[str] = Field(default_factory=list, max_length=30)
    example_sentence: str = Field(default="", max_length=500)


def _generation_failed(kind: str, org_id: UUID, exc: Exception) -> HTTPException:
    logger.error(f"{kind}_generation_failed", org_id=str(org_id), error=str(exc))
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY, "Generation failed; no quota was used. Try again."
    )


async def _approved_profile_answers(
    db: AsyncSession, client_id: Any, org_id: UUID
) -> dict[str, str]:
    """Brand Voice and Strategy Lens need an approved profile, as Cadence gates them."""
    bp = await get_profile(db, client_id, org_id)
    if bp is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "profile_required", "message": "Approve the brand profile first."},
        )
    return intake_answers(bp)


@router.get("/{client_id}/profile")
async def read_profile(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    client = await get_org_client(db, client_id, org_id)
    return profile_view(client, await get_profile(db, client.id, org_id))


@router.put("/{client_id}/profile")
async def approve_profile(
    client_id: UUID,
    body: ApproveProfileRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    client = await get_org_client(db, client_id, org_id)
    bp = await approve_intake(
        db,
        client,
        org_id,
        url=body.url,
        audience=body.audience,
        differentiator=body.differentiator,
        tone=body.tone,
    )
    await db.commit()
    await db.refresh(bp)
    await db.refresh(client)
    return profile_view(client, bp)


@router.post("/{client_id}/profile/evaluate-answer")
async def coach_answer(
    client_id: UUID,
    body: EvaluateAnswerRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    client = await get_org_client(db, client_id, org_id)
    brand = await load_brand_context(db, client, org_id)
    try:
        result = await evaluate_answer(
            question=INTAKE_QUESTIONS[body.question_id], answer=body.answer.strip(), brand=brand
        )
    except Exception as exc:
        # Never block progress on a failed check — the human has final say.
        logger.warning("answer_coaching_unavailable", org_id=str(org_id), error=str(exc))
        return {"available": False, "is_thin": False, "coaching_note": ""}
    return {"available": True, **result}


@router.post("/{client_id}/brand-voice/generate")
async def draft_brand_voice(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    client = await get_org_client(db, client_id, org_id)
    answers = await _approved_profile_answers(db, client.id, org_id)
    await require_generation_quota(db, org_id)
    brand = await load_brand_context(db, client, org_id)
    try:
        guide = await generate_brand_voice(brand, answers)
    except Exception as exc:  # MalformedGenerationError included
        raise _generation_failed("brand_voice", org_id, exc) from None
    await charge_generation(db, org_id)
    await db.commit()
    return guide


@router.put("/{client_id}/brand-voice")
async def approve_brand_voice(
    client_id: UUID,
    body: BrandVoiceRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    client = await get_org_client(db, client_id, org_id)
    await _approved_profile_answers(db, client.id, org_id)
    bp = await get_profile(db, client.id, org_id)
    if bp is None:  # unreachable: checked just above
        raise HTTPException(status.HTTP_409_CONFLICT, "Approve the brand profile first.")
    apply_brand_voice(
        bp,
        voice_description=body.voice_description,
        vocabulary_include=body.vocabulary_include,
        vocabulary_exclude=body.vocabulary_exclude,
        example_sentence=body.example_sentence,
    )
    await db.commit()
    await db.refresh(bp)
    return profile_view(client, bp)


@router.post("/{client_id}/strategy-lens", status_code=status.HTTP_201_CREATED)
async def run_strategy_lens(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    client = await get_org_client(db, client_id, org_id)
    answers = await _approved_profile_answers(db, client.id, org_id)
    await require_generation_quota(db, org_id)
    brand = await load_brand_context(db, client, org_id)
    try:
        panel = await generate_strategy_lens(brand, answers)
    except Exception as exc:  # MalformedGenerationError included
        raise _generation_failed("strategy_lens", org_id, exc) from None
    asset = await save_asset(
        db,
        org_id=org_id,
        client_id=client.id,
        kind="strategy_lens",
        title=f"Strategy lens panel — {datetime.now(UTC):%Y-%m-%d}",
        payload={**panel, "answers": answers},
        created_by=user.get("sub"),
    )
    await charge_generation(db, org_id)
    await db.commit()
    await db.refresh(asset)
    return asset_out(asset)


@router.get("/{client_id}/accounts")
async def client_accounts(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    client = await get_org_client(db, client_id, org_id)
    rows = (
        await db.execute(
            select(PlatformAccount)
            .where(
                PlatformAccount.org_id == org_id,
                PlatformAccount.client_id == client.id,
                PlatformAccount.status == "connected",
            )
            .order_by(PlatformAccount.created_at.desc())
        )
    ).scalars()
    return {
        "accounts": [
            {
                "id": str(a.id),
                "platform": a.platform,
                "account_handle": a.account_handle,
                "display_name": a.display_name,
                "status": a.status,
                "connected_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in rows
        ],
        "oauth": oauth_platform_status(),
    }
