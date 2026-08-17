"""Competitive intelligence router — competitor scanning against retrieved sources.

The scan is retrieval-grounded (see :mod:`agency.agents.competitive_intel`). This
router passes the agent payload through unchanged: when Exa is not configured, no
source could be retrieved, or no model claim survived the source filter, the
response is ``{"status": "unavailable", "reason": ..., "findings": []}`` with HTTP
200 — never LLM-guessed competitor claims.
"""

from typing import Any
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
    body: dict[str, Any] | None = Body(default=None),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Trigger a competitive intelligence scan for a client.

    ``competitors`` in the body should be a comma-separated list of competitor
    names; it falls back to the client's brand profile. Every returned finding
    carries the URL and retrieval date of the document it came from.
    """
    result = await db.execute(
        select(Client)
        .where(Client.id == client_id, Client.org_id == org_id)
        .options(selectinload(Client.brand_profile))
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    competitor_info = str((body or {}).get("competitors") or "").strip()
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
