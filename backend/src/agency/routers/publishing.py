"""Publishing API — immediate publish, schedule, calendar."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import ContentPiece, PlatformAccount
from agency.permissions import Capability, require_cap
from agency.services.billing import billing
from agency.services.content_approval import (
    ContentGateError,
    ensure_client_active,
    ensure_publishable,
    ensure_schedulable,
)
from agency.services.publishing import publisher
from agency.services.scheduler import scheduler

router = APIRouter(prefix="/publishing", tags=["Publishing"])


class ScheduleRequest(BaseModel):
    scheduled_at: datetime


def _merge_metadata(piece: ContentPiece, updates: dict) -> None:
    base = dict(piece.metadata_ or {})
    base.update(updates)
    piece.metadata_ = base


def _piece_to_calendar_item(piece: ContentPiece) -> dict:
    return {
        "id": str(piece.id),
        "title": piece.title,
        "body": piece.body,
        "platform": piece.platform,
        "hashtags": list(piece.hashtags or []),
        "status": piece.status,
        "scheduled_at": piece.scheduled_at.isoformat() if piece.scheduled_at else None,
        "published_at": piece.published_at.isoformat() if piece.published_at else None,
        "client_id": str(piece.client_id),
        "campaign_id": str(piece.campaign_id) if piece.campaign_id else None,
    }


# CAPABILITY GATE: publishing posts to a client's live account, so it is
# owner/admin only — a ``member`` may approve copy but may not push it out.
# The gate lives here and nowhere deeper: ``services/scheduler.py::_publish_piece``
# runs on a timer with no user in scope, so the same check inside
# ``services/publishing.py`` would stop scheduled posts going out at 3am.
@router.post(
    "/{content_id}/publish",
    dependencies=[Depends(require_cap(Capability.PUBLISH_WRITE))],
)
async def publish_now(
    content_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Publish now. Only ``approved``/``scheduled`` content; otherwise
    409 ``{"code": "not_approved", "status": <current>}``."""
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.org_id == org_id,
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    # APPROVAL GATE: this posts to a client's live account. Only content that went
    # through moderated approval may be published — anything else (including an
    # already-published piece, so a double click cannot double-post) is a 409.
    try:
        ensure_publishable(piece)
        await ensure_client_active(db, piece)
    except ContentGateError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None

    if not await billing.check_quota(db, org_id, resource="posts"):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "Monthly post limit reached for your plan. Upgrade to publish more.",
        )

    # TENANCY: the ``org_id`` filter is load-bearing, not defence-in-depth — without it a
    # PlatformAccount row belonging to another tenant but carrying this client's id would
    # be selected here and the post published with that tenant's token.
    # ``first()`` (not ``scalar_one_or_none``) because an org may legitimately hold more
    # than one account for a client+platform; newest connection wins instead of a 500.
    acc_result = await db.execute(
        select(PlatformAccount)
        .where(
            PlatformAccount.org_id == org_id,
            PlatformAccount.client_id == piece.client_id,
            PlatformAccount.platform == piece.platform,
            PlatformAccount.status == "connected",
        )
        .order_by(PlatformAccount.created_at.desc())
    )
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No connected platform account for this content's platform",
        )

    content_data = {
        "body": piece.body,
        "hashtags": piece.hashtags or [],
        "title": piece.title,
    }
    credentials = {
        "access_token": account.access_token_enc,
        "page_id": account.account_handle,
    }

    pub_result = await publisher.publish(piece.platform, content_data, credentials)

    if pub_result.get("success"):
        piece.status = "published"
        piece.published_at = datetime.now(UTC)
        _merge_metadata(
            piece,
            {
                "post_id": pub_result.get("post_id"),
                "post_url": pub_result.get("url"),
                # A post that went out is no longer blocked or failing. Leaving
                # either behind would label a live post with a stale warning.
                "publish_blocked": None,
                "publish_error": None,
            },
        )
        await billing.record_post_published(db, org_id)
    else:
        piece.status = "failed"
        _merge_metadata(piece, {"publish_error": pub_result.get("error")})

    await db.commit()

    if not pub_result.get("success"):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            pub_result.get("error", "Publish failed"),
        )

    return {
        "status": "published",
        "content_id": str(content_id),
        "post_id": pub_result.get("post_id"),
        "url": pub_result.get("url"),
    }


# CAPABILITY GATE: scheduling is publishing with a delay — the scheduler posts
# whatever is ``scheduled`` when it comes due — so it needs the same capability.
@router.post(
    "/{content_id}/schedule",
    dependencies=[Depends(require_cap(Capability.PUBLISH_WRITE))],
)
async def schedule_content(
    content_id: UUID,
    body: ScheduleRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Schedule (or reschedule). Only ``approved``/``scheduled`` content; otherwise
    409 ``{"code": "not_approved", "status": <current>}``. Platforms with no working
    publisher → 409 ``{"code": "platform_unavailable"}``."""
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.org_id == org_id,
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    # APPROVAL GATE: the scheduler publishes whatever is ``scheduled`` when it comes
    # due, so scheduling is the last point a human-approval check can happen.
    try:
        ensure_schedulable(piece)
        await ensure_client_active(db, piece)
    except ContentGateError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None

    out = await scheduler.schedule_content(db, content_id, body.scheduled_at)
    if out.get("error"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, out["error"])
    return out


@router.get("/calendar")
async def get_calendar(
    start: datetime = Query(..., description="Range start (UTC)"),
    end: datetime = Query(..., description="Range end (UTC)"),
    client_id: UUID | None = Query(None, description="Only this client's posts"),
    include_pending: bool = Query(
        False, description="Also return drafts/approved posts with a planned day, and failed ones"
    ),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    # ``client_id`` needs no separate ownership check: the query is already
    # ``org_id``-filtered, so a foreign client id simply matches nothing.
    pieces = await scheduler.get_calendar(
        db, org_id, start, end, client_id=client_id, include_pending=include_pending
    )
    return {"items": [_piece_to_calendar_item(p) for p in pieces]}
