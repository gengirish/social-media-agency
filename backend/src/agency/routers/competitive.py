"""Competitive intelligence router — competitor scanning and insights."""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import Client

router = APIRouter(prefix="/competitive", tags=["Competitive Intelligence"])


@router.post("/clients/{client_id}/scan")
async def trigger_competitive_scan(
    client_id: UUID,
    body: dict | None = Body(default=None),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Trigger a competitive intelligence scan for a client."""
    result = await db.execute(
        select(Client)
        .where(Client.id == client_id, Client.org_id == org_id)
        .options(selectinload(Client.brand_profile))
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    competitor_info = (body or {}).get("competitors", "")
    if not competitor_info and client.brand_profile:
        competitor_info = client.brand_profile.competitor_differentiation or ""

    brand_context = {
        "brand_name": client.brand_name,
        "industry": client.industry or "",
    }

    from agency.agents.competitive_intel import run_competitive_scan

    result_scan = await run_competitive_scan(competitor_info, brand_context)

    return {
        "client_id": str(client_id),
        "client_name": client.brand_name,
        **result_scan,
    }
