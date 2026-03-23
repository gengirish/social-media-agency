"""Publishing API — immediate publish, schedule, calendar."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import ContentPiece, PlatformAccount
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
        "status": piece.status,
        "scheduled_at": piece.scheduled_at.isoformat() if piece.scheduled_at else None,
        "published_at": piece.published_at.isoformat() if piece.published_at else None,
        "client_id": str(piece.client_id),
        "campaign_id": str(piece.campaign_id) if piece.campaign_id else None,
    }


@router.post("/{content_id}/publish")
async def publish_now(
    content_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.org_id == org_id,
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    acc_result = await db.execute(
        select(PlatformAccount).where(
            PlatformAccount.client_id == piece.client_id,
            PlatformAccount.platform == piece.platform,
            PlatformAccount.status == "connected",
        )
    )
    account = acc_result.scalar_one_or_none()
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
        piece.published_at = datetime.now(timezone.utc)
        _merge_metadata(
            piece,
            {
                "post_id": pub_result.get("post_id"),
                "post_url": pub_result.get("url"),
            },
        )
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


@router.post("/{content_id}/schedule")
async def schedule_content(
    content_id: UUID,
    body: ScheduleRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.org_id == org_id,
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    out = await scheduler.schedule_content(db, content_id, body.scheduled_at)
    if out.get("error"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, out["error"])
    return out


@router.get("/calendar")
async def get_calendar(
    start: datetime = Query(..., description="Range start (UTC)"),
    end: datetime = Query(..., description="Range end (UTC)"),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    pieces = await scheduler.get_calendar(db, org_id, start, end)
    return {"items": [_piece_to_calendar_item(p) for p in pieces]}
