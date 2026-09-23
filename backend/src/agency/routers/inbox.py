"""Inbox — live X mentions / LinkedIn comments, reply suggestions, human-sent replies.

Tenancy: ``client_id`` is resolved against the caller's org before anything
else, and platform accounts are selected with BOTH ``org_id`` and ``client_id``
(the ``oauth`` / ``publish_now`` incident: an unscoped account lookup would read
— or reply with — another tenant's token). Reply targets are never taken from
the request: the item must be present in that account's own fetched inbox.

Replies are real posts on a client's live account, so ``POST /inbox/reply`` only
runs on an explicit human click, runs moderation first (product rule 3), and
writes an audit_log entry.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents.inbox_reply import generate_reply_suggestion
from agency.dependencies import get_current_user_id, get_db, get_org_id
from agency.models.tables import PlatformAccount
from agency.services import inbox as inbox_service
from agency.services import moderation
from agency.services.audit import log_action
from agency.services.brand_context import get_org_client, load_brand_context
from agency.services.generation_quota import charge_generation, require_generation_quota

logger = structlog.get_logger()

router = APIRouter(prefix="/inbox", tags=["Inbox"])

MAX_MESSAGE_TEXT = 5000
MAX_REPLY_TEXT = 3000


def _valid_item_key(value: str) -> str:
    platform, _, native = value.partition(":")
    if platform not in inbox_service.INBOX_PLATFORMS or not native:
        raise ValueError("item_id must look like '<platform>:<id>' for an inbox platform")
    return value


class ItemStateRequest(BaseModel):
    client_id: UUID
    item_id: str = Field(min_length=3, max_length=255)
    read: bool | None = None
    handled: bool | None = None

    _check = field_validator("item_id")(_valid_item_key)


class SuggestRequest(BaseModel):
    client_id: UUID
    platform: Literal["twitter", "linkedin"]
    type: Literal["mention", "comment", "dm"] = "mention"
    author: str = Field(default="", max_length=300)
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_TEXT)


class ReplyRequest(BaseModel):
    client_id: UUID
    account_id: UUID
    item_id: str = Field(min_length=3, max_length=255)
    text: str = Field(min_length=1, max_length=MAX_REPLY_TEXT)
    override: bool = False

    _check = field_validator("item_id")(_valid_item_key)


@router.get("")
async def get_inbox(
    client_id: UUID = Query(...),
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Live items + a per-account status for every inbox platform."""
    client = await get_org_client(db, client_id, org_id)
    result = await inbox_service.load_client_inbox(
        db, org_id=org_id, client_id=client.id, refresh=refresh
    )
    await db.commit()  # persists a refreshed X token, if one was rotated
    return result


@router.patch("/items/state")
async def set_item_state(
    body: ItemStateRequest,
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
    user_id: UUID = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Mark an item read / handled. Only triage state is stored, never the item."""
    client = await get_org_client(db, body.client_id, org_id)
    row = await inbox_service.set_item_state(
        db,
        org_id=org_id,
        client_id=client.id,
        item_key=body.item_id,
        user_id=user_id,
        read=body.read,
        handled=body.handled,
    )
    await db.commit()
    return {"item_id": body.item_id, "read": bool(row.is_read), "handled": bool(row.handled)}


@router.post("/suggest-reply")
async def suggest_reply(
    body: SuggestRequest,
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """One reply suggestion (or an escalation flag). Charges one generation."""
    client = await get_org_client(db, body.client_id, org_id)
    await require_generation_quota(db, org_id)
    brand = await load_brand_context(db, client, org_id)
    try:
        result = await generate_reply_suggestion(
            message_text=body.text,
            platform=body.platform,
            item_type=body.type,
            author=body.author,
            brand=brand,
        )
    except Exception as exc:
        logger.error("inbox_suggest_failed", org_id=str(org_id), error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Couldn't generate a suggestion; no quota was used."
        ) from None
    if result is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The model returned no usable suggestion; no quota was used. Try again.",
        )
    await charge_generation(db, org_id)
    await db.commit()
    return {
        "suggestion": result.suggestion,
        "needs_personal_attention": result.needs_personal_attention,
    }


@router.post("/reply")
async def send_reply(
    body: ReplyRequest,
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
    user_id: UUID = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Post a reply for real. Moderation first; flagged → 409 unless ``override``."""
    client = await get_org_client(db, body.client_id, org_id)
    account = (
        await db.execute(
            select(PlatformAccount).where(
                PlatformAccount.id == body.account_id,
                PlatformAccount.org_id == org_id,
                PlatformAccount.client_id == client.id,
                PlatformAccount.status == "connected",
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    platform = str(account.platform)
    if not body.item_id.startswith(f"{platform}:"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found for this account")
    if not inbox_service.reply_supported(platform):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "reply_unsupported",
                "message": f"Replying on {platform} isn't available from CampaignForge.",
            },
        )

    item = await inbox_service.find_item(db, account, body.item_id)
    if item is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "That message isn't in this account's inbox any more. Refresh and try again.",
        )

    # MODERATION BEFORE PUBLISH (product rule 3): same judgement every post gets.
    brand_context = await moderation.load_brand_context(db, client.id, org_id)
    mod = await moderation.moderate_content(body.text, platform, brand_context)
    if mod.issues and not body.override:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"code": "moderation_flagged", "issues": mod.issues}
        )
    moderation_record: dict[str, Any] = {
        "status": "overridden" if mod.issues else mod.status,
        "issues": mod.issues,
        "llm_checked": mod.llm_checked,
    }
    if mod.issues:
        moderation_record["override_by"] = str(user_id)

    audit_details: dict[str, Any] = {
        "client_id": str(client.id),
        "account_id": str(account.id),
        "platform": platform,
        "in_reply_to": body.item_id,
        "in_reply_to_url": item.get("url"),
        "text": body.text,
        "moderation": moderation_record,
    }
    try:
        posted = await inbox_service.post_reply(db, account, item, body.text)
    except inbox_service.PlatformCallError as exc:
        await log_action(
            db,
            org_id,
            user_id,
            "inbox.reply_failed",
            resource_type="inbox_item",
            resource_id=body.item_id,
            details={**audit_details, "status": exc.status, "error": exc.message},
        )
        await db.commit()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            {"code": "reply_failed", "status": exc.status, "message": exc.message},
        ) from None

    await log_action(
        db,
        org_id,
        user_id,
        "inbox.reply",
        resource_type="inbox_item",
        resource_id=body.item_id,
        details={**audit_details, "reply_id": posted["reply_id"], "reply_url": posted["url"]},
    )
    await inbox_service.set_item_state(
        db,
        org_id=org_id,
        client_id=client.id,
        item_key=body.item_id,
        user_id=user_id,
        read=True,
        handled=True,
        reply_id=posted["reply_id"],
        reply_url=posted["url"],
    )
    await db.commit()
    logger.info(
        "inbox_reply_sent",
        org_id=str(org_id),
        platform=platform,
        moderation=moderation_record["status"],
    )
    return {
        "status": "sent",
        "reply_id": posted["reply_id"],
        "url": posted["url"],
        "moderation": {"status": moderation_record["status"], "issues": mod.issues},
    }
