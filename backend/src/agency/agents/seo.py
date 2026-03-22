"""SEO Agent — The SEO Specialist.

Generates keyword clusters, meta titles/descriptions, hashtag strategies,
and content briefs optimized for discoverability.
"""

import json

from langchain_core.messages import SystemMessage

from agency.agents.state import CampaignState
from agency.services.llm_provider import get_worker_llm

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
    llm = get_worker_llm(temperature=0.4)
    brand_ctx = state.get("brand_context", {})
    plan = state.get("execution_plan", {})

    brand_str = "\n".join(f"- {k}: {v}" for k, v in brand_ctx.items() if v)
    plan_str = json.dumps(plan, indent=2) if isinstance(plan, dict) else str(plan)

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
        keywords = [{"keyword": k, "search_volume": "medium", "difficulty": "medium"} for k in keywords]

    return {
        "seo_keywords": keywords,
        "current_agent": "seo",
    }
