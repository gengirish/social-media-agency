"""Trend intelligence service — trending topics by platform."""

import structlog

logger = structlog.get_logger()

PLATFORM_TRENDS = {
    "twitter": [
        {"topic": "AI Agents", "volume": "trending", "category": "tech"},
        {"topic": "Summer Marketing", "volume": "rising", "category": "marketing"},
        {"topic": "Gen Z Engagement", "volume": "steady", "category": "audience"},
        {"topic": "Short-form Video", "volume": "trending", "category": "content"},
        {"topic": "Sustainability", "volume": "rising", "category": "brand"},
    ],
    "linkedin": [
        {"topic": "B2B AI Adoption", "volume": "trending", "category": "tech"},
        {"topic": "Remote Work Culture", "volume": "steady", "category": "workplace"},
        {"topic": "Thought Leadership", "volume": "rising", "category": "content"},
        {"topic": "Data-Driven Marketing", "volume": "trending", "category": "marketing"},
        {"topic": "Employee Advocacy", "volume": "rising", "category": "brand"},
    ],
    "instagram": [
        {"topic": "Reels Strategy", "volume": "trending", "category": "content"},
        {"topic": "UGC Marketing", "volume": "rising", "category": "marketing"},
        {"topic": "Behind the Scenes", "volume": "steady", "category": "content"},
        {"topic": "Carousel Posts", "volume": "trending", "category": "format"},
        {"topic": "Influencer Collab", "volume": "rising", "category": "partnership"},
    ],
    "facebook": [
        {"topic": "Community Groups", "volume": "trending", "category": "engagement"},
        {"topic": "Video First", "volume": "rising", "category": "content"},
        {"topic": "Local Business", "volume": "steady", "category": "market"},
        {"topic": "Event Marketing", "volume": "rising", "category": "marketing"},
        {"topic": "Messenger Bots", "volume": "trending", "category": "tech"},
    ],
}


async def get_trending_topics(platform: str | None = None) -> list:
    """Get trending topics. In production, uses Exa search API."""
    if platform and platform in PLATFORM_TRENDS:
        return PLATFORM_TRENDS[platform]
    all_trends = []
    for p, trends in PLATFORM_TRENDS.items():
        for t in trends:
            all_trends.append({**t, "platform": p})
    return all_trends
