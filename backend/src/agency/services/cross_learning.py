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
    sample_size = int(row[4] or 0)

    def _avg(value: object) -> float | None:
        """Round a SQL AVG, keeping ``NULL`` as ``None``.

        Never coerce a missing average to ``0.0`` — a benchmark of zero reads as
        a measurement ("this industry gets no impressions") rather than "we have
        no data for this industry".
        """
        return None if value is None else round(float(value), 1)  # type: ignore[arg-type]

    if sample_size == 0:
        return {
            "industry": industry,
            "status": "unavailable",
            "reason": (
                "No analytics snapshots exist for this industry yet. Benchmarks "
                "require published content with fetched platform metrics."
            ),
            "avg_impressions": None,
            "avg_engagement": None,
            "avg_clicks": None,
            "avg_likes": None,
            "sample_size": 0,
        }

    return {
        "industry": industry,
        "status": "available",
        "avg_impressions": _avg(row[0]),
        "avg_engagement": _avg(row[1]),
        "avg_clicks": _avg(row[2]),
        "avg_likes": _avg(row[3]),
        "sample_size": sample_size,
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
