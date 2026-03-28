"""Analytics fetcher — retrieve engagement metrics from platform APIs."""

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import AnalyticsSnapshot, ContentPiece, PlatformAccount

logger = structlog.get_logger()


async def fetch_content_metrics(
    db: AsyncSession, content_id: UUID
) -> dict:
    """Fetch engagement metrics for a published content piece."""
    result = await db.execute(
        select(ContentPiece).where(ContentPiece.id == content_id)
    )
    piece = result.scalar_one_or_none()
    if not piece or piece.status != "published":
        return {"error": "Content not published"}

    result = await db.execute(
        select(PlatformAccount).where(
            PlatformAccount.client_id == piece.client_id,
            PlatformAccount.platform == piece.platform,
            PlatformAccount.status == "connected",
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        return {"error": f"No connected {piece.platform} account"}

    # In production, call platform APIs here. Return mock data for now.
    metrics = {
        "impressions": 0,
        "reach": 0,
        "engagement": 0,
        "clicks": 0,
        "shares": 0,
        "likes": 0,
    }

    snapshot = AnalyticsSnapshot(
        platform_account_id=account.id,
        content_id=content_id,
        date=datetime.now(timezone.utc).date(),
        impressions=metrics["impressions"],
        reach=metrics["reach"],
        engagement=metrics["engagement"],
        clicks=metrics["clicks"],
        shares=metrics["shares"],
        likes=metrics["likes"],
    )
    db.add(snapshot)
    await db.flush()
    return metrics


async def get_content_analytics(
    db: AsyncSession, content_id: UUID
) -> list[dict]:
    """Get historical analytics snapshots for a content piece."""
    result = await db.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.content_id == content_id)
        .order_by(AnalyticsSnapshot.date.desc())
    )
    snapshots = result.scalars().all()
    return [
        {
            "date": s.date.isoformat(),
            "impressions": s.impressions,
            "reach": s.reach,
            "engagement": s.engagement,
            "clicks": s.clicks,
            "shares": s.shares,
            "likes": s.likes,
        }
        for s in snapshots
    ]


async def get_client_analytics_summary(
    db: AsyncSession, client_id: UUID, org_id: UUID
) -> dict:
    """Aggregated analytics for all content by a client."""
    result = await db.execute(
        select(
            func.sum(AnalyticsSnapshot.impressions),
            func.sum(AnalyticsSnapshot.engagement),
            func.sum(AnalyticsSnapshot.clicks),
            func.sum(AnalyticsSnapshot.likes),
            func.sum(AnalyticsSnapshot.shares),
            func.count(AnalyticsSnapshot.id),
        )
        .join(ContentPiece, ContentPiece.id == AnalyticsSnapshot.content_id)
        .where(ContentPiece.client_id == client_id, ContentPiece.org_id == org_id)
    )
    row = result.one()
    return {
        "total_impressions": row[0] or 0,
        "total_engagement": row[1] or 0,
        "total_clicks": row[2] or 0,
        "total_likes": row[3] or 0,
        "total_shares": row[4] or 0,
        "snapshot_count": row[5] or 0,
    }
