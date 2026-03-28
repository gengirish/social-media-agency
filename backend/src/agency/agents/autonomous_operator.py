"""Autonomous campaign operator — self-running weekly campaign cycles."""

import json

import structlog

from agency.services.llm_provider import get_worker_llm

logger = structlog.get_logger()


async def plan_autonomous_cycle(
    goal: str,
    brand_context: dict,
    previous_performance: dict | None = None,
) -> dict:
    """Plan the next autonomous campaign cycle based on goals and past performance."""
    llm = get_worker_llm()

    perf_context = ""
    if previous_performance:
        perf_context = f"""
Previous cycle performance:
- Impressions: {previous_performance.get('impressions', 0)}
- Engagement: {previous_performance.get('engagement', 0)}
- Clicks: {previous_performance.get('clicks', 0)}
- Top performing: {previous_performance.get('top_content', 'N/A')}
"""

    prompt = f"""You are an autonomous marketing campaign operator.

Brand: {brand_context.get('brand_name', 'Unknown')}
Industry: {brand_context.get('industry', 'Unknown')}
Goal: {goal}
{perf_context}

Plan the next weekly campaign cycle:
1. Strategy adjustments based on performance
2. Content themes for the week (3-5)
3. Posting schedule (platform, day, time)
4. A/B test suggestions
5. Budget allocation recommendations

Return JSON:
{{
    "strategy": "...",
    "themes": ["..."],
    "schedule": [{{"platform": "...", "day": "...", "time": "...", "content_type": "..."}}],
    "ab_tests": ["..."],
    "budget_allocation": {{"platform": percentage}},
    "key_metrics_to_track": ["..."]
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
        return {
            "strategy": text[:500],
            "themes": [],
            "schedule": [],
            "ab_tests": [],
            "raw": True,
        }
