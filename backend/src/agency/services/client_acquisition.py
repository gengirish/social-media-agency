"""Client acquisition engine — identify and outreach to prospects."""

import json

import structlog

from agency.services.llm_provider import get_worker_llm

logger = structlog.get_logger()


async def generate_outreach(
    prospect_name: str,
    prospect_industry: str,
    prospect_pain_points: list[str],
    our_brand: str = "CampaignForge",
) -> dict:
    """Generate personalized outreach for a prospect."""
    llm = get_worker_llm()

    prompt = f"""You are a sales outreach specialist for {our_brand}, an AI marketing agency platform.

Prospect: {prospect_name}
Industry: {prospect_industry}
Pain points: {', '.join(prospect_pain_points)}

Generate a 3-email outreach sequence:
1. Cold intro (personalized, value-first)
2. Follow-up (case study / social proof)
3. Final (urgency / limited offer)

Return JSON:
{{
    "emails": [
        {{"subject": "...", "body": "...", "send_day": 1}},
        {{"subject": "...", "body": "...", "send_day": 4}},
        {{"subject": "...", "body": "...", "send_day": 7}}
    ]
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
        return {"emails": [], "raw_response": text[:500]}
