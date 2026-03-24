"""Persist learned analytics preferences into brand profile tone_attributes."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import BrandProfile


async def update_brand_learnings(
    db: AsyncSession,
    client_id: UUID,
    analytics_data: dict,
) -> dict:
    """Merge analytics-derived learnings into ``tone_attributes['learned']``."""
    result = await db.execute(
        select(BrandProfile).where(BrandProfile.client_id == client_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return {"error": "Brand profile not found"}

    tone = dict(profile.tone_attributes or {})
    learned = dict(tone.get("learned") or {})

    if "best_performing_topics" in analytics_data:
        learned["best_performing_topics"] = analytics_data["best_performing_topics"]
    if "optimal_posting_times" in analytics_data:
        learned["optimal_posting_times"] = analytics_data["optimal_posting_times"]
    if "engagement_multipliers" in analytics_data:
        learned["engagement_multipliers"] = analytics_data["engagement_multipliers"]

    # Optional passthrough for richer agent output (incl. campaign completion summary)
    for key in (
        "topic_engagement_index",
        "platform_benchmarks",
        "last_updated_at",
        "topics_covered",
        "platforms_used",
        "ad_platforms",
    ):
        if key in analytics_data:
            learned[key] = analytics_data[key]

    tone["learned"] = learned
    profile.tone_attributes = tone
    await db.commit()
    await db.refresh(profile)

    return {"status": "updated", "client_id": str(client_id), "learned": learned}
