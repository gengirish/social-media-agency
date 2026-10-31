"""Review links — the agency side: make, list and revoke a client's review link.

The client side (opening the link, deciding) is ``routers/portal.py``. Logic lives
in ``services/client_review.py``; this router only translates.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agency.dependencies import get_current_user_id, get_db, get_org_id
from agency.permissions import Capability, require_cap
from agency.services.client_review import (
    DEFAULT_TTL_DAYS,
    MAX_TTL_DAYS,
    ReviewLinkError,
    create_review_link,
    list_review_links,
    revoke_review_link,
)

router = APIRouter(tags=["Review Links"])

#: A review link hands the power to approve a client's posts to someone outside the
#: workspace, so making or revoking one takes the power it delegates. ``member``
#: holds ``content.approve``; ``viewer`` does not and cannot share.
_SHARE_GATE = Depends(require_cap(Capability.CONTENT_APPROVE))


class ReviewLinkCreate(BaseModel):
    campaign_id: UUID | None = None
    ttl_days: int = Field(default=DEFAULT_TTL_DAYS, ge=1, le=MAX_TTL_DAYS)


@router.post("/clients/{client_id}/review-links", dependencies=[_SHARE_GATE])
async def create_link(
    client_id: UUID,
    body: ReviewLinkCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Make a link. ``token`` and ``path`` are returned **once** — only a hash is kept.

    ``path`` is relative (``/review/<token>``): the browser that asked knows the app's
    own origin, and building it here would tie the link to whichever CORS origin the
    backend happens to list first.
    """
    try:
        link, token = await create_review_link(
            db,
            org_id=org_id,
            client_id=client_id,
            campaign_id=body.campaign_id,
            created_by=user_id,
            ttl_days=body.ttl_days,
        )
    except ReviewLinkError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
    return {"link": link, "token": token, "path": f"/review/{token}"}


@router.get("/clients/{client_id}/review-links")
async def list_links(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    try:
        return {"items": await list_review_links(db, org_id=org_id, client_id=client_id)}
    except ReviewLinkError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None


@router.post("/review-links/{link_id}/revoke", dependencies=[_SHARE_GATE])
async def revoke_link(
    link_id: UUID,
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    try:
        return {"link": await revoke_review_link(db, org_id=org_id, link_id=link_id)}
    except ReviewLinkError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
