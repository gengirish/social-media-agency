"""Insights — Cadence's computed analytics and the customer advocacy agent, per client.

Thin: the numbers come from ``services/insights.py``, the prompt from
``agents/advocacy.py``. Every ``client_id`` is resolved against ``org_id`` first.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents.advocacy import generate_advocacy
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.services import product_analytics as pa
from agency.services.brand_context import get_org_client, load_brand_context
from agency.services.creative_assets import asset_out, save_asset
from agency.services.generation_quota import charge_generation, require_generation_quota
from agency.services.insights import advocacy_facts, build_summary

logger = structlog.get_logger()

router = APIRouter(prefix="/insights", tags=["Insights"])


@router.get("/summary")
async def insights_summary(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Pipeline, publish, moderation and quality-signal stats plus recommendations.

    Ratios below the minimum sample come back as ``{"status": "insufficient_data",
    "value": null, "n", "needed"}``; ``thresholds`` lists every recommendation rule
    with its progress, so the UI can say what data is still missing.
    """
    client = await get_org_client(db, client_id, org_id)
    return await build_summary(db, org_id, client)


class AdvocacyRequest(BaseModel):
    client_id: UUID


@router.post("/advocacy")
async def create_advocacy(
    body: AdvocacyRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Review request + case study outline + proof line, citing only real numbers.

    Charges one generation on success and saves a ``creative_asset`` of kind
    ``advocacy``. A model error, a malformed reply, or a reply that cites a number
    the server did not supply is a 502 and nothing is charged or saved.
    """
    client = await get_org_client(db, body.client_id, org_id)
    await require_generation_quota(db, org_id)

    facts = await advocacy_facts(db, org_id, client)
    brand = await load_brand_context(db, client, org_id)
    try:
        result = await generate_advocacy(brand=brand, facts=facts)
    except Exception as exc:
        logger.error("advocacy_generation_failed", org_id=str(org_id), error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Couldn't generate advocacy content; no quota was used. Try again.",
        ) from None

    asset = await save_asset(
        db,
        org_id=org_id,
        client_id=client.id,
        kind="advocacy",
        title=f"Advocacy — {client.brand_name}",
        payload={**result, "facts": facts},
        created_by=user.get("sub"),
    )
    await charge_generation(db, org_id)
    await pa.track(
        db,
        name=pa.ADVOCACY_GENERATED,
        org_id=org_id,
        user_id=user.get("sub"),
        properties={"client_id": str(client.id), "asset_id": str(asset.id)},
    )
    await db.commit()
    await db.refresh(asset)
    return asset_out(asset)
