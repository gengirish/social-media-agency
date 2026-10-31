"""Public REST API — org-scoped routes authenticated via X-API-Key."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from agency.dependencies import get_db
from agency.models.tables import Campaign, ContentPiece
from agency.services.handoff import HANDOFF_STATUSES, client_names, handoff_item

router = APIRouter(prefix="/public", tags=["Public API"])


def get_api_key_org_id(request: Request) -> UUID:
    org_id = getattr(request.state, "api_key_org_id", None)
    if org_id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "API key authentication required",
        )
    return org_id


@router.get("/me")
async def public_me(
    org_id: UUID = Depends(get_api_key_org_id),
):
    """Return the organization associated with the API key."""
    return {"org_id": str(org_id)}


@router.get("/campaigns")
async def public_list_campaigns(
    db=Depends(get_db),
    org_id: UUID = Depends(get_api_key_org_id),
):
    """List campaigns for the API key's organization."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.org_id == org_id)
        .order_by(Campaign.created_at.desc())
        .limit(50)
    )
    campaigns = result.scalars().all()
    return {
        "items": [
            {
                "id": str(c.id),
                "name": c.name,
                "status": c.status,
                "channels": c.channels,
                "start_date": str(c.start_date) if c.start_date else None,
                "end_date": str(c.end_date) if c.end_date else None,
            }
            for c in campaigns
        ],
    }


@router.get("/content")
async def public_list_content(
    db=Depends(get_db),
    org_id: UUID = Depends(get_api_key_org_id),
    content_status: str = Query("approved", alias="status"),
    client_id: UUID | None = None,
    since: datetime | None = Query(
        None, description="Only items updated at or after this ISO-8601 time"
    ),
    limit: int = Query(50, ge=1, le=100),
):
    """Approved posts, newest change first — the polling exit to an agency's scheduler.

    ``status`` is ``approved`` (default), ``scheduled`` or ``published``. Anything
    else is 400: a draft has not been moderated or approved, and this endpoint
    exists to feed tools that post. Items are the ``services/handoff.py`` shape, the
    same object the ``content.approved`` webhook carries under ``content``.
    """
    if content_status not in HANDOFF_STATUSES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {
                "code": "status_not_handed_off",
                "allowed": sorted(HANDOFF_STATUSES),
            },
        )
    q = select(ContentPiece).where(
        ContentPiece.org_id == org_id, ContentPiece.status == content_status
    )
    if client_id is not None:
        q = q.where(ContentPiece.client_id == client_id)
    if since is not None:
        q = q.where(ContentPiece.updated_at >= since)
    q = q.order_by(ContentPiece.updated_at.desc(), ContentPiece.id).limit(limit)

    pieces = list((await db.execute(q)).scalars().all())
    names = await client_names(db, org_id, {p.client_id for p in pieces})
    return {
        "items": [
            handoff_item(p, client_name=names.get(str(p.client_id))) for p in pieces
        ],
    }
