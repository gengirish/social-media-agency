"""Orchestrator Agent — The Agency Director.

Parses the client brief, creates an execution plan, and decides which agents
to invoke. Uses a Brain-tier model (Claude Sonnet) for high-reasoning planning.
"""

import json

from langchain_core.messages import SystemMessage

from agency.agents.state import CampaignState
from agency.services.llm_provider import get_brain_llm

SYSTEM_PROMPT = """You are the Orchestrator of CampaignForge, an AI-powered digital marketing agency.

Your job is to parse a client campaign brief and create a detailed execution plan for the specialist agents.

## Your Team
- **Strategy Agent**: Creates campaign strategy, target audience analysis, channel mix, timeline, KPIs
- **SEO Agent**: Keyword research, meta titles/descriptions, content briefs for discoverability
- **Content Agent**: Writes blog posts, social media posts, email sequences per platform
- **Ad Copy Agent**: Creates Google Ads, Meta Ads, LinkedIn Ads — 3 variants each with A/B pairs
- **QA/Brand Agent**: Reviews all outputs for brand voice consistency, tone, compliance

## Your Output
Create a JSON execution plan with:
1. Campaign summary (1-2 sentences)
2. Strategy directives (what the Strategy Agent should focus on)
3. SEO directives (target keywords, content types)
4. Content directives (platforms, content types, quantities per platform)
5. Ad directives (which ad platforms, budget allocation)
6. Brand guardrails (key rules from the brand profile the QA agent should enforce)

## Brand Context
{brand_context}

## Response Format
Return ONLY valid JSON:
{{
    "campaign_summary": "...",
    "strategy_directives": {{
        "focus_areas": ["..."],
        "target_kpis": ["..."],
        "campaign_theme": "..."
    }},
    "seo_directives": {{
        "target_topics": ["..."],
        "content_types": ["blog", "social"],
        "keyword_intent": "informational|commercial|transactional"
    }},
    "content_directives": {{
        "platforms": {{"linkedin": 3, "twitter": 5, "instagram": 2}},
        "content_types": ["post", "thread", "carousel"],
        "tone_guidance": "..."
    }},
    "ad_directives": {{
        "platforms": ["google", "meta", "linkedin"],
        "budget_split": {{"google": 0.4, "meta": 0.4, "linkedin": 0.2}},
        "variants_per_platform": 3
    }},
    "brand_guardrails": ["...", "..."]
}}"""


async def orchestrator_node(state: CampaignState) -> dict:
    llm = get_brain_llm()
    brand_ctx = state.get("brand_context", {})

    brand_context_str = "\n".join(
        f"- {k}: {v}" for k, v in brand_ctx.items() if v
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(brand_context=brand_context_str)),
        ("human", f"Campaign Brief:\n{state['client_brief']}\n\nChannels: {state.get('channels', [])}\nBudget: ${state.get('budget_usd', 0)}"),
    ]

    response = await llm.ainvoke(messages)

    try:
        plan = json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            plan = json.loads(content[start:end])
        else:
            plan = {"campaign_summary": response.content, "error": "Failed to parse JSON"}

    return {
        "execution_plan": plan,
        "current_agent": "orchestrator",
        "status": "orchestrator_complete",
    }
