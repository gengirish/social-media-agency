"""Ad Copy Agent — Creates ad variants for Google, Meta, and LinkedIn.

Generates 3 variants per platform with A/B headline pairs.
Uses Claude Haiku for cost-effective, high-quality ad copy.
"""

import json

from langchain_core.messages import SystemMessage

from agency.agents.state import CampaignState
from agency.agents.utils import parse_agent_json, text_of
from agency.services.ad_variants import platform_of
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


#: Which campaign channel selects which ad network. A campaign that asked for
#: LinkedIn and X used to come back with Google and Meta search ads: the
#: orchestrator is free to write any ``ad_directives.platforms`` it likes, and
#: the default was a hardcoded ``["google", "meta"]`` that ignored the brief
#: entirely (CF-04). Paid ads are a separate spend decision from organic posting,
#: so they are opt-in per channel, never inferred.
CHANNEL_TO_AD_PLATFORM: dict[str, str] = {
    "google": "google",
    "google_ads": "google",
    "meta": "meta",
    "meta_ads": "meta",
    "facebook_ads": "meta",
    "instagram_ads": "meta",
    "linkedin_ads": "linkedin",
}


def selected_ad_platforms(channels: list[str], directives_platforms: list) -> list[str]:
    """The ad networks this campaign actually asked for.

    The orchestrator's suggestion is treated as a preference and intersected with
    the brief: a network the user did not pick is dropped, and a network they did
    pick is kept even if the orchestrator forgot it. An organic channel
    (``linkedin``, ``twitter``) is not an ad channel — running search ads because
    someone ticked LinkedIn would spend a budget nobody approved.
    """
    asked = []
    for channel in channels or []:
        platform = CHANNEL_TO_AD_PLATFORM.get(str(channel).strip().lower())
        if platform and platform not in asked:
            asked.append(platform)
    if not asked:
        return []

    suggested = {
        str(p).strip().lower() for p in directives_platforms if isinstance(p, (str, int))
    }
    # Honour the orchestrator's narrowing, but never its widening.
    narrowed = [p for p in asked if p in suggested]
    return narrowed or asked


async def ad_copy_node(state: CampaignState) -> dict:
    llm = get_ad_copy_llm()
    brand_ctx = state.get("brand_context", {})
    strategy = state.get("strategy", {})
    seo = state.get("seo_keywords", [])
    plan = state.get("execution_plan", {})

    ad_directives = plan.get("ad_directives", {})
    ad_platforms = selected_ad_platforms(
        state.get("channels", []), ad_directives.get("platforms", []) or []
    )
    if not ad_platforms:
        # No ad network was selected, so there is no ad copy to write. Returning
        # nothing is the point: the alternative is drafts for a channel the
        # campaign never asked for, cluttering the review queue.
        return {"ad_variants": [], "current_agent": "ad_copy"}

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
        # Unparseable JSON: keep the raw text so the run is not silently empty,
        # on a network the campaign actually selected rather than a hardcoded
        # "google" (CF-04).
        raw = text_of(response.content)
        variants = [
            {
                "platform": ad_platforms[0],
                "variant": 1,
                "headlines": [raw[:30]],
                "descriptions": [raw[:90]],
            }
        ]
    else:
        variants = parsed

    if isinstance(variants, dict):
        variants = [variants]

    # The model is asked for specific networks but will occasionally volunteer
    # another. Dropping those here keeps the guarantee the brief implies: no ad
    # copy for a channel nobody selected.
    allowed = set(ad_platforms)
    variants = [
        v
        for v in variants
        if not isinstance(v, dict)
        or platform_of(v) in allowed
    ]

    return {
        "ad_variants": variants,
        "current_agent": "ad_copy",
    }
