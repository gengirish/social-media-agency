"""SEO Agent — The SEO Specialist.

Generates keyword clusters, meta titles/descriptions, hashtag strategies,
and content briefs optimized for discoverability.
"""

import json

from langchain_core.messages import SystemMessage

from agency.agents.state import CampaignState
from agency.services.llm_provider import get_lite_llm

SYSTEM_PROMPT = """You are the SEO Agent of CampaignForge, a digital marketing agency AI.

Generate SEO research and keyword strategy based on the campaign plan and brand context.

## Brand Context
{brand_context}

## Execution Plan
{execution_plan}

## Your Output
Return a JSON document:
{{
    "primary_keywords": [
        {{"keyword": "...", "search_volume": "high|medium|low", "difficulty": "high|medium|low", "intent": "informational|commercial|transactional"}}
        // search_volume and difficulty are YOUR estimates — no search API is called.
        // Omit either field if you have no basis for it. Never state a numeric volume.
    ],
    "long_tail_keywords": ["keyword phrase 1", "keyword phrase 2"],
    "hashtag_strategy": {{
        "platform": {{
            "primary_hashtags": ["..."],
            "secondary_hashtags": ["..."],
            "branded_hashtags": ["..."]
        }}
    }},
    "content_briefs": [
        {{
            "title_suggestion": "...",
            "meta_description": "...",
            "target_keyword": "...",
            "content_angle": "...",
            "word_count_target": 800
        }}
    ],
    "competitor_keywords": ["..."],
    "trending_topics": ["..."]
}}"""


async def seo_node(state: CampaignState) -> dict:
    # Keyword research and structural SEO is extraction, not reasoning — it runs
    # on the cheap tier. Strategy and Content stay on ``worker``.
    llm = get_lite_llm(temperature=0.4)
    brand_ctx = state.get("brand_context", {})
    plan = state.get("execution_plan", {})

    brand_str = "\n".join(f"- {k}: {v}" for k, v in brand_ctx.items() if v)
    plan_str = json.dumps(plan, separators=(",", ":")) if isinstance(plan, dict) else str(plan)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(
            brand_context=brand_str,
            execution_plan=plan_str,
        )),
        ("human", f"Generate SEO strategy for this campaign.\nIndustry: {brand_ctx.get('industry', 'general')}\nChannels: {state.get('channels', [])}"),
    ]

    response = await llm.ainvoke(messages)

    try:
        seo_data = json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            seo_data = json.loads(content[start:end])
        else:
            seo_data = {"raw_output": response.content}

    keywords = seo_data.get("primary_keywords", [])
    if isinstance(keywords, list) and keywords and isinstance(keywords[0], str):
        # Do NOT fill search_volume/difficulty with a constant here. The previous
        # version stamped every bare keyword with "medium"/"medium", which reads as
        # keyword-research data but is a literal.
        keywords = [{"keyword": k} for k in keywords]

    # No search API is called by this agent, so any volume/difficulty band present
    # is the model's own estimate. Label it so no consumer mistakes it for measured
    # search data.
    if isinstance(keywords, list):
        keywords = [
            {**kw, "metrics_source": "llm_estimate"} if isinstance(kw, dict) else kw
            for kw in keywords
        ]

    return {
        "seo_keywords": keywords,
        "current_agent": "seo",
    }
