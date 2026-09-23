"""Create › Email — Cadence's Email/Lifecycle agent.

Generates one lifecycle campaign per call and stores it as a ``creative_asset``
of kind ``email_campaign``. Listing, reading and deleting go through the generic
``/assets`` router. Nothing here sends email: CampaignForge drafts campaigns,
the human sends them from their own email tool.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents.lifecycle_email import generate_email_campaign
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.services.brand_context import get_org_client, load_brand_context
from agency.services.create_kits import (
    generate_asset,
    require_brand_profile,
    validate_email_campaign,
)

router = APIRouter(prefix="/create/email", tags=["Create › Email"])

CampaignType = Literal["welcome", "onboarding", "reengagement", "update", "milestone"]


class EmailGenerateRequest(BaseModel):
    client_id: UUID
    campaign_type: CampaignType


@router.post("/generate")
async def generate(
    body: EmailGenerateRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """One campaign. Charges one generation only when a complete campaign came back."""
    client = await get_org_client(db, body.client_id, org_id)
    await require_brand_profile(db, client, org_id)
    brand = await load_brand_context(db, client, org_id)

    async def produce() -> Any:
        return await generate_email_campaign(body.campaign_type, brand)

    return await generate_asset(
        db,
        org_id=org_id,
        client=client,
        kind="email_campaign",
        produce=produce,
        validate=lambda raw: validate_email_campaign(raw, body.campaign_type),
        created_by=user.get("sub"),
    )
