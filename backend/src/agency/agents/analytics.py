"""Analytics Agent — turns engagement metrics into actionable recommendations."""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from agency.agents.state import CampaignState
from agency.services.llm_provider import get_worker_llm

SYSTEM_PROMPT = """You are the Analytics Agent for CampaignForge, a digital marketing agency AI.

You analyze social and content performance data and produce clear, specific recommendations
that a marketer can act on this week.

## Rules
- Compare platforms, topics, and formats using the numbers provided (rates, counts, multipliers).
- Call out patterns (e.g. "LinkedIn posts about X get ~3x engagement vs baseline").
- Prefer 3–7 bullet-style recommendations in JSON; each must be concrete ("create more…", "post at…", "test…").
- If data is thin, say what to measure next instead of inventing metrics.

## Engagement data (JSON)
{engagement_json}

## Your output
Return ONLY valid JSON:
{{
  "summary": "One short paragraph on overall performance.",
  "recommendations": [
    "Your LinkedIn posts about [topic] get 3x engagement — create more carousel posts on that theme.",
    "..."
  ],
  "by_platform": {{
    "linkedin": {{ "insight": "...", "suggested_actions": ["..."] }}
  }},
  "risks_or_gaps": ["..."]
}}"""


async def analytics_node(state: CampaignState) -> dict:
    engagement = state.get("engagement_data") or {}

    # ``engagement_data`` is only populated once a campaign's content has been
    # published AND platform metrics have been fetched. On a fresh campaign it is
    # empty, and an LLM handed `{}` will happily invent "LinkedIn gets 3x
    # engagement". Return an explicit unavailable result instead of calling the
    # model — never fabricate performance analysis.
    if not engagement:
        return {
            "analytics_insights": {
                "status": "unavailable",
                "reason": (
                    "No measured engagement data for this campaign yet. Publish "
                    "content to a connected platform account and wait for the "
                    "daily metrics refresh; recommendations require real numbers."
                ),
                "summary": None,
                "recommendations": [],
                "by_platform": {},
                "risks_or_gaps": [],
            },
            "current_agent": "analytics",
        }

    llm = get_worker_llm(temperature=0.4)
    engagement_json = json.dumps(engagement, separators=(",", ":"), default=str)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(engagement_json=engagement_json)),
        HumanMessage(
            content="Analyze this engagement data and return insights and recommendations as JSON."
        ),
    ]

    response = await llm.ainvoke(messages)
    raw = response.content if isinstance(response.content, str) else str(response.content)

    insights: dict
    try:
        insights = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            insights = json.loads(raw[start:end])
        else:
            insights = {
                "summary": raw[:2000],
                "recommendations": [],
                "by_platform": {},
                "risks_or_gaps": ["Could not parse structured analytics output."],
            }

    if isinstance(insights, dict):
        insights.setdefault("status", "available")

    return {
        "analytics_insights": insights,
        "current_agent": "analytics",
    }
