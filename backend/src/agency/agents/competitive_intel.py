"""Competitive intelligence agent — monitor competitors, suggest counter-campaigns."""

import json

from agency.services.llm_provider import get_worker_llm


async def run_competitive_scan(
    competitor_info: str,
    brand_context: dict,
) -> dict:
    """Analyze competitors and generate counter-campaign suggestions."""
    llm = get_worker_llm()

    prompt = f"""You are a competitive intelligence analyst for a marketing agency.

Brand: {brand_context.get('brand_name', 'Unknown')}
Industry: {brand_context.get('industry', 'Unknown')}

Competitor information:
{competitor_info}

Analyze the competitive landscape and provide:
1. Key competitor messaging themes (3-5)
2. Content gaps we can exploit (3-5)
3. Counter-campaign suggestions (2-3 specific campaign ideas)
4. Recommended response strategy

Return JSON:
{{
    "themes": ["..."],
    "content_gaps": ["..."],
    "counter_campaigns": [
        {{"name": "...", "objective": "...", "channels": ["..."], "key_message": "..."}}
    ],
    "strategy": "..."
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
            "themes": [],
            "content_gaps": [],
            "counter_campaigns": [],
            "strategy": text[:500],
            "raw_response": True,
        }
