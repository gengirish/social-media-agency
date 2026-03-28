"""Brand analytics router — per-client intelligence dashboard."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import BrandProfile, Campaign, Client, ContentPiece

router = APIRouter(prefix="/brand-analytics", tags=["Brand Analytics"])


@router.get("/clients/{client_id}/intelligence")
async def get_client_intelligence(
    client_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Aggregated intelligence for a client."""
    # Verify client
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.org_id == org_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    # Campaign count
    result = await db.execute(
        select(func.count(Campaign.id)).where(
            Campaign.client_id == client_id, Campaign.org_id == org_id
        )
    )
    campaign_count = result.scalar() or 0

    # Content by platform
    result = await db.execute(
        select(ContentPiece.platform, func.count(ContentPiece.id))
        .where(ContentPiece.client_id == client_id, ContentPiece.org_id == org_id)
        .group_by(ContentPiece.platform)
    )
    platform_breakdown = {row[0]: row[1] for row in result.all()}

    # Content by status
    result = await db.execute(
        select(ContentPiece.status, func.count(ContentPiece.id))
        .where(ContentPiece.client_id == client_id, ContentPiece.org_id == org_id)
        .group_by(ContentPiece.status)
    )
    status_breakdown = {row[0]: row[1] for row in result.all()}

    # Top performing content
    result = await db.execute(
        select(ContentPiece)
        .where(
            ContentPiece.client_id == client_id,
            ContentPiece.org_id == org_id,
            ContentPiece.performance_score.isnot(None),
        )
        .order_by(ContentPiece.performance_score.desc())
        .limit(5)
    )
    top_content = result.scalars().all()

    # Brand profile
    result = await db.execute(
        select(BrandProfile).where(BrandProfile.client_id == client_id)
    )
    profile = result.scalar_one_or_none()

    return {
        "client_name": client.brand_name,
        "industry": client.industry,
        "campaign_count": campaign_count,
        "platform_breakdown": platform_breakdown,
        "status_breakdown": status_breakdown,
        "top_content": [
            {
                "id": str(p.id),
                "platform": p.platform,
                "title": p.title,
                "performance_score": p.performance_score,
            }
            for p in top_content
        ],
        "brand_voice": {
            "voice_description": profile.voice_description if profile else "",
            "tone_attributes": profile.tone_attributes if profile else {},
            "target_audience": profile.target_audience if profile else "",
        },
    }


@router.get("/cross-learning")
async def get_cross_learning(
    industry: str | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Cross-campaign insights and industry benchmarks."""
    from agency.services.cross_learning import (
        get_cross_campaign_insights,
        get_industry_benchmarks,
    )

    insights = await get_cross_campaign_insights(db, org_id)
    benchmarks = None
    if industry:
        benchmarks = await get_industry_benchmarks(db, industry)

    return {
        "insights": insights,
        "benchmarks": benchmarks,
    }
