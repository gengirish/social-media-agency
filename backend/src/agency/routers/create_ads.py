"""Create › Ads — Google RSA asset sets and Meta ad copy.

Copy and structure only: no ad account is connected, nothing here creates a
campaign, sets a budget or spends money, and no endpoint returns a CTR, CPC or
ROAS figure. Generated sets are saved as ``creative_asset`` rows of kind
``ad_set``; listing, renaming and deleting go through the generic ``/assets``
router.

Flow: resolve client against org → quota check → generate → guardrails +
advisory moderation (fails open) → save_asset → charge 1 generation → commit.
A failed or malformed generation is a 502 and charges nothing.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents.ads import ad_set_title
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.services.ad_guardrails import AD_LIMITS, META_CTA_OPTIONS
from agency.services.ad_sets import build_ad_set, known_competitor_names
from agency.services.brand_context import get_org_client, load_brand_context
from agency.services.creative_assets import asset_out, save_asset
from agency.services.generation_quota import charge_generation, require_generation_quota

logger = structlog.get_logger()

router = APIRouter(prefix="/create/ads", tags=["Create: Ads"])


class GenerateAdsRequest(BaseModel):
    client_id: UUID
    network: Literal["google", "meta"]


@router.get("/spec")
async def spec(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """The limits and CTA presets the checks use, so the UI shows the same numbers."""
    return {"limits": AD_LIMITS, "meta_cta_options": list(META_CTA_OPTIONS)}


@router.post("/generate")
async def generate(
    body: GenerateAdsRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Generate and save one ad set. Charges one generation, only on success."""
    client = await get_org_client(db, body.client_id, org_id)
    await require_generation_quota(db, org_id)

    brand = await load_brand_context(db, client, org_id)
    competitors = await known_competitor_names(db, org_id, client.id)  # type: ignore[arg-type]
    try:
        payload = await build_ad_set(body.network, brand, competitors)
    except Exception as exc:
        logger.error(
            "ad_generation_failed", org_id=str(org_id), network=body.network, error=str(exc)
        )
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Couldn't generate ad copy right now; no quota was used. Try again.",
        ) from None

    asset = await save_asset(
        db,
        org_id=org_id,
        client_id=client.id,  # type: ignore[arg-type]
        kind="ad_set",
        title=ad_set_title(body.network, payload),
        payload=payload,
        created_by=user.get("sub"),
    )
    await charge_generation(db, org_id)
    await db.commit()
    await db.refresh(asset)
    return asset_out(asset)
