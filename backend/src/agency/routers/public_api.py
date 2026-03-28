"""Public REST API — org-scoped routes authenticated via X-API-Key."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from agency.dependencies import get_db
from agency.models.tables import Campaign

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
