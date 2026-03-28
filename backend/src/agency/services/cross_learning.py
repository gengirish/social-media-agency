"""Cross-learning service — insights across campaigns and clients."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import AnalyticsSnapshot, Client, ContentPiece


async def get_industry_benchmarks(
    db: AsyncSession, industry: str
) -> dict:
    """Aggregate engagement metrics across all orgs in same industry."""
    result = await db.execute(
        select(
            func.avg(AnalyticsSnapshot.impressions),
            func.avg(AnalyticsSnapshot.engagement),
            func.avg(AnalyticsSnapshot.clicks),
            func.avg(AnalyticsSnapshot.likes),
            func.count(AnalyticsSnapshot.id),
        )
        .join(ContentPiece, ContentPiece.id == AnalyticsSnapshot.content_id)
        .join(Client, Client.id == ContentPiece.client_id)
        .where(Client.industry == industry)
    )
    row = result.one()
    return {
        "industry": industry,
        "avg_impressions": round(float(row[0] or 0), 1),
        "avg_engagement": round(float(row[1] or 0), 1),
        "avg_clicks": round(float(row[2] or 0), 1),
        "avg_likes": round(float(row[3] or 0), 1),
        "sample_size": row[4] or 0,
    }


async def get_cross_campaign_insights(
    db: AsyncSession, org_id: UUID
) -> list[dict]:
    """Identify content patterns that work across campaigns."""
    result = await db.execute(
        select(ContentPiece)
        .where(
            ContentPiece.org_id == org_id,
            ContentPiece.performance_score.isnot(None),
        )
        .order_by(ContentPiece.performance_score.desc())
        .limit(20)
    )
    pieces = result.scalars().all()

    platform_perf: dict[str, list] = {}
    for p in pieces:
        platform_perf.setdefault(p.platform, []).append(p.performance_score)

    insights = []
    for platform, scores in platform_perf.items():
        avg = sum(scores) / len(scores) if scores else 0
        insights.append({
            "platform": platform,
            "avg_performance": round(avg, 2),
            "content_count": len(scores),
            "insight": f"{platform.title()} averages {avg:.1f} performance score across {len(scores)} pieces",
        })

    return insights
