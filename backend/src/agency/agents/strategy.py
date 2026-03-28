"""Strategy Agent — The Strategist.

Creates campaign strategy with target audience analysis, channel mix,
content calendar framework, and KPIs. Uses a Worker-tier model (Gemini Flash).
"""

import json

from langchain_core.messages import SystemMessage

from agency.agents.state import CampaignState
from agency.services.knowledge_base import retrieve_knowledge
from agency.services.llm_provider import get_worker_llm

SYSTEM_PROMPT = """You are the Strategy Agent of CampaignForge, a digital marketing agency AI.

Create a comprehensive campaign strategy based on the orchestrator's execution plan and brand context.

## Brand Context
{brand_context}

## Execution Plan
{execution_plan}

## Your Output
Return a JSON strategy document:
{{
    "campaign_theme": "...",
    "target_audience": {{
        "primary": "...",
        "secondary": "...",
        "pain_points": ["..."],
        "motivations": ["..."]
    }},
    "channel_strategy": {{
        "platform": {{
            "role": "awareness|engagement|conversion",
            "posting_frequency": "X times per week",
            "content_mix": ["type1", "type2"],
            "best_times": ["..."]
        }}
    }},
    "content_pillars": ["pillar1", "pillar2", "pillar3"],
    "campaign_timeline": [
        {{"week": 1, "theme": "...", "focus": "..."}},
        {{"week": 2, "theme": "...", "focus": "..."}}
    ],
    "kpis": [
        {{"metric": "...", "target": "...", "measurement": "..."}}
    ],
    "competitive_angle": "..."
}}"""


async def strategy_node(state: CampaignState) -> dict:
    llm = get_worker_llm(temperature=0.6)
    brand_ctx = state.get("brand_context", {})
    plan = state.get("execution_plan", {})

    brand_str = "\n".join(f"- {k}: {v}" for k, v in brand_ctx.items() if v)
    plan_str = json.dumps(plan, indent=2) if isinstance(plan, dict) else str(plan)

    brief_for_kb = state.get("client_brief", "") or ""
    knowledge = await retrieve_knowledge(brief_for_kb, k=2)
    knowledge_context = ""
    if knowledge:
        knowledge_context = "\n\nRelevant marketing knowledge:\n" + "\n".join(
            f"- {k['title']}: {k['content'][:200]}" for k in knowledge
        )

    system_content = SYSTEM_PROMPT.format(
        brand_context=brand_str,
        execution_plan=plan_str,
    ) + knowledge_context

    messages = [
        SystemMessage(content=system_content),
        ("human", f"Create the campaign strategy.\nBrief: {state.get('client_brief', '')}"),
    ]

    response = await llm.ainvoke(messages)

    try:
        strategy = json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            strategy = json.loads(content[start:end])
        else:
            strategy = {"raw_output": response.content}

    return {
        "strategy": strategy,
        "current_agent": "strategy",
    }
