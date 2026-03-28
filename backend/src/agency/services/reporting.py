"""Report generation service — client-facing PDF/JSON reports."""

from datetime import datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import Campaign, Client, ContentPiece

logger = structlog.get_logger()


async def generate_report_data(
    db: AsyncSession, client_id: UUID, org_id: UUID, period: str = "monthly"
) -> dict:
    """Generate report data for a client over a given period."""
    now = datetime.utcnow()
    if period == "weekly":
        start = now - timedelta(days=7)
    elif period == "monthly":
        start = now - timedelta(days=30)
    elif period == "quarterly":
        start = now - timedelta(days=90)
    else:
        start = now - timedelta(days=30)

    # Get client info
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.org_id == org_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        return {"error": "Client not found"}

    # Campaign stats
    result = await db.execute(
        select(func.count(Campaign.id)).where(
            Campaign.client_id == client_id,
            Campaign.org_id == org_id,
            Campaign.created_at >= start,
        )
    )
    total_campaigns = result.scalar() or 0

    # Content stats
    result = await db.execute(
        select(func.count(ContentPiece.id)).where(
            ContentPiece.client_id == client_id,
            ContentPiece.org_id == org_id,
            ContentPiece.created_at >= start,
        )
    )
    total_content = result.scalar() or 0

    # Content by platform
    result = await db.execute(
        select(ContentPiece.platform, func.count(ContentPiece.id))
        .where(
            ContentPiece.client_id == client_id,
            ContentPiece.org_id == org_id,
            ContentPiece.created_at >= start,
        )
        .group_by(ContentPiece.platform)
    )
    platform_breakdown = {row[0]: row[1] for row in result.all()}

    # Content by status
    result = await db.execute(
        select(ContentPiece.status, func.count(ContentPiece.id))
        .where(
            ContentPiece.client_id == client_id,
            ContentPiece.org_id == org_id,
            ContentPiece.created_at >= start,
        )
        .group_by(ContentPiece.status)
    )
    status_breakdown = {row[0]: row[1] for row in result.all()}

    # Published content
    published = status_breakdown.get("published", 0)

    return {
        "client_name": client.brand_name,
        "industry": client.industry,
        "period": period,
        "start_date": start.isoformat(),
        "end_date": now.isoformat(),
        "metrics": {
            "total_campaigns": total_campaigns,
            "total_content_pieces": total_content,
            "published": published,
            "drafts": status_breakdown.get("draft", 0),
            "approved": status_breakdown.get("approved", 0),
        },
        "platform_breakdown": platform_breakdown,
        "status_breakdown": status_breakdown,
    }
