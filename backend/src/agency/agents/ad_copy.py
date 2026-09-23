"""Ad Copy Agent — Creates ad variants for Google, Meta, and LinkedIn.

Generates 3 variants per platform with A/B headline pairs.
Uses Claude Haiku for cost-effective, high-quality ad copy.
"""

import json

from langchain_core.messages import SystemMessage

from agency.agents.state import CampaignState
from agency.agents.utils import parse_agent_json, text_of
from agency.services.llm_provider import get_ad_copy_llm

SYSTEM_PROMPT = """You are the Ad Copy Agent of CampaignForge, a digital marketing agency AI.

Create ad copy variants for paid advertising campaigns.

## Brand Context
{brand_context}

## Campaign Strategy
{strategy}

## SEO Keywords
{seo_keywords}

## Ad Platforms Requested
{ad_platforms}

## Ad Format Specs
- **Google Ads**: Headlines (max 30 chars each, 3 per ad), Descriptions (max 90 chars each, 2 per ad)
- **Meta Ads**: Primary text (125 chars optimal), Headline (40 chars), Description (30 chars), CTA button
- **LinkedIn Ads**: Intro text (150 chars optimal), Headline (70 chars), Description (100 chars)

## Rules
1. Each variant must have a different angle (benefit, social proof, urgency, curiosity, etc.)
2. Include A/B pairs for headlines — test emotional vs rational appeals
3. Match brand voice while being compelling and action-oriented
4. Include specific numbers, results, or offers when possible
5. Every ad needs a clear CTA

## Response Format
Return a JSON array:
[
    {{
        "platform": "google|meta|linkedin",
        "variant": 1,
        "angle": "benefit|social_proof|urgency|curiosity|comparison",
        "headlines": ["Headline A", "Headline B", "Headline C"],
        "descriptions": ["Description 1", "Description 2"],
        "primary_text": "For Meta/LinkedIn — longer intro text",
        "cta": "Learn More|Sign Up|Get Started|Shop Now|Book Now",
        "target_keyword": "...",
        "notes": "Why this angle works"
    }}
]"""


async def ad_copy_node(state: CampaignState) -> dict:
    llm = get_ad_copy_llm()
    brand_ctx = state.get("brand_context", {})
    strategy = state.get("strategy", {})
    seo = state.get("seo_keywords", [])
    plan = state.get("execution_plan", {})

    ad_directives = plan.get("ad_directives", {})
    ad_platforms = ad_directives.get("platforms", ["google", "meta"])

    brand_str = "\n".join(f"- {k}: {v}" for k, v in brand_ctx.items() if v)
    strategy_str = json.dumps(strategy, separators=(",", ":")) if isinstance(strategy, dict) else str(strategy)
    seo_str = json.dumps(seo[:5]) if seo else "No keywords"

    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(
            brand_context=brand_str,
            strategy=strategy_str,
            seo_keywords=seo_str,
            ad_platforms=", ".join(ad_platforms),
        )),
        ("human", f"Create 3 ad variants each for: {', '.join(ad_platforms)}"),
    ]

    response = await llm.ainvoke(messages)

    parsed = await parse_agent_json(response.content, agent="ad_copy", expect=list)
    if parsed is None:
        raw = text_of(response.content)
        variants = [{"platform": "google", "variant": 1, "headlines": [raw[:30]], "descriptions": [raw[:90]]}]
    else:
        variants = parsed

    if isinstance(variants, dict):
        variants = [variants]

    return {
        "ad_variants": variants,
        "current_agent": "ad_copy",
    }
