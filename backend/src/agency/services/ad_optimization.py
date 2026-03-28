"""Ad optimization service — bid and budget recommendations."""

import json

import structlog

from agency.services.llm_provider import get_worker_llm

logger = structlog.get_logger()


async def analyze_ad_performance(
    platform: str,
    campaign_data: dict,
) -> dict:
    """Analyze ad performance and suggest bid adjustments."""
    llm = get_worker_llm()

    prompt = f"""You are a paid advertising optimization expert.

Platform: {platform}
Campaign data: {campaign_data}

Analyze and provide:
1. Performance assessment
2. Bid adjustment recommendations
3. Budget reallocation suggestions
4. Audience targeting improvements
5. Creative refresh suggestions

Return JSON:
{{
    "assessment": "...",
    "bid_adjustments": [{{"target": "...", "current_bid": 0, "recommended_bid": 0, "reason": "..."}}],
    "budget_suggestions": {{"total": 0, "breakdown": {{}}}},
    "targeting_improvements": ["..."],
    "creative_suggestions": ["..."]
}}"""

    response = await llm.ainvoke(prompt)
    text = response.content if hasattr(response, "content") else str(response)
    text = text.strip()

    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception:
        return {"assessment": text[:500], "bid_adjustments": [], "raw": True}
