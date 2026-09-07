"""Cross-learning service — insights across campaigns and clients.

TENANCY EXCEPTION — READ BEFORE "FIXING" THIS FILE.

:func:`get_industry_benchmarks` deliberately aggregates across organisations
and does **not** filter on ``org_id``. That is the whole feature: an industry
benchmark computed from one tenant's own data is just that tenant compared to
itself. It is the single documented exception to the project rule that every
org-scoped query filters on ``org_id``.

The exception is safe only because of :data:`MIN_CONTRIBUTING_ORGS`. Below that
floor the average is close enough to an individual account's numbers to work as
an inference channel — an org in a thin industry could read a competitor's
performance off it — so the benchmark is suppressed instead of returned.

Every other function here is org-scoped normally.
"""

from typing import Final
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import AnalyticsSnapshot, Client, ContentPiece

#: Distinct organisations that must contribute before a benchmark is returned.
#: This is a privacy floor, not a data-quality threshold — it counts *orgs*, not
#: snapshots, because one org with a thousand snapshots is still one account
#: whose numbers would be exposed.
MIN_CONTRIBUTING_ORGS: Final = 5


async def get_industry_benchmarks(
    db: AsyncSession, industry: str
) -> dict:
    """Aggregate engagement metrics across all orgs in the same industry.

    Cross-org by design — see the module docstring. Returns ``status:
    "unavailable"`` rather than an average whenever fewer than
    :data:`MIN_CONTRIBUTING_ORGS` organisations contribute.
    """
    result = await db.execute(
        select(
            func.avg(AnalyticsSnapshot.impressions),
            func.avg(AnalyticsSnapshot.engagement),
            func.avg(AnalyticsSnapshot.clicks),
            func.avg(AnalyticsSnapshot.likes),
            func.count(AnalyticsSnapshot.id),
            func.count(distinct(Client.org_id)),
        )
        .join(ContentPiece, ContentPiece.id == AnalyticsSnapshot.content_id)
        .join(Client, Client.id == ContentPiece.client_id)
        .where(Client.industry == industry)
    )
    row = result.one()
    sample_size = int(row[4] or 0)
    contributing_orgs = int(row[5] or 0)

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
            "contributing_orgs": 0,
        }

    if contributing_orgs < MIN_CONTRIBUTING_ORGS:
        # Report neither the averages nor the true sample size. Returning the
        # real counts while suppressing the averages would leak the same signal
        # the floor exists to protect — how much data one competitor has.
        return {
            "industry": industry,
            "status": "unavailable",
            "reason": (
                f"Benchmarks need at least {MIN_CONTRIBUTING_ORGS} organisations "
                "contributing measured data in this industry. Fewer are "
                "available, so publishing an average could expose an individual "
                "account's performance."
            ),
            "avg_impressions": None,
            "avg_engagement": None,
            "avg_clicks": None,
            "avg_likes": None,
            "sample_size": 0,
            "contributing_orgs": 0,
        }

    return {
        "industry": industry,
        "status": "available",
        "avg_impressions": _avg(row[0]),
        "avg_engagement": _avg(row[1]),
        "avg_clicks": _avg(row[2]),
        "avg_likes": _avg(row[3]),
        "sample_size": sample_size,
        # 200 snapshots from 5 orgs is a different claim from 200 from 50.
        "contributing_orgs": contributing_orgs,
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
            "insight": (
                f"{platform.title()} averages {avg:.1f} performance score "
                f"across {len(scores)} pieces"
            ),
        })

    return insights
