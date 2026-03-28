"""Content Agent — The Copywriter.

Generates platform-specific content pieces: social posts, blog outlines,
email sequences. Respects brand voice, character limits, and platform conventions.
"""

import json

from langchain_core.messages import SystemMessage

from agency.agents.state import CampaignState
from agency.services.llm_provider import get_worker_llm

PLATFORM_GUIDELINES = {
    "instagram": {
        "max_length": 2200,
        "optimal_length": "150-300 characters for feed",
        "style": "Visual-first. Use line breaks. CTA in first 125 chars. Emojis welcomed.",
    },
    "facebook": {
        "max_length": 63206,
        "optimal_length": "40-80 characters for highest engagement",
        "style": "Short and punchy. Questions drive comments. Native content over links.",
    },
    "twitter": {
        "max_length": 280,
        "optimal_length": "71-100 characters",
        "style": "Concise and witty. Threads for longer content. Media increases engagement 150%.",
    },
    "linkedin": {
        "max_length": 3000,
        "optimal_length": "150-300 characters, up to 1300 for thought leadership",
        "style": "Professional tone. Personal stories perform well. Use line breaks heavily.",
    },
    "tiktok": {
        "max_length": 2200,
        "optimal_length": "50-150 characters",
        "style": "Casual, authentic tone. Hook in first 3 seconds. Trending formats.",
    },
}

SYSTEM_PROMPT = """You are the Content Agent of CampaignForge, a digital marketing agency AI.

Generate platform-specific content pieces based on the campaign strategy and SEO keywords.

## Brand Context
{brand_context}

## Campaign Strategy
{strategy}

## SEO Keywords to Incorporate
{seo_keywords}

## Platform Guidelines
{platform_guidelines}

## Rules
1. Match the brand voice and tone exactly
2. Each post must feel native to its platform — NEVER identical content cross-platform
3. Include a clear call-to-action when appropriate
4. Incorporate SEO keywords naturally (don't force them)
5. Respect character limits per platform
6. Do NOT include hashtags in the body — return them separately

## Response Format
Return a JSON array of content pieces:
[
    {{
        "platform": "linkedin|twitter|instagram|facebook|tiktok",
        "content_type": "post|thread|carousel|story|reel_caption",
        "title": "Internal title for content library",
        "body": "The actual post content",
        "hashtags": ["tag1", "tag2"],
        "cta": "The call-to-action",
        "notes": "Why this content works for this platform"
    }}
]

Generate {post_count} total pieces across the requested platforms.

{language_instructions}"""


async def content_writer_node(state: CampaignState) -> dict:
    llm = get_worker_llm(temperature=0.8)
    brand_ctx = state.get("brand_context", {})
    strategy = state.get("strategy", {})
    seo = state.get("seo_keywords", [])
    channels = state.get("channels", ["linkedin", "twitter"])
    plan = state.get("execution_plan", {})

    content_directives = plan.get("content_directives", {})
    platforms = content_directives.get("platforms", {})
    if not platforms:
        platforms = {ch: 2 for ch in channels}
    post_count = sum(platforms.values()) if isinstance(platforms, dict) else len(channels) * 2

    brand_str = "\n".join(f"- {k}: {v}" for k, v in brand_ctx.items() if v)
    strategy_str = json.dumps(strategy, indent=2) if isinstance(strategy, dict) else str(strategy)
    seo_str = json.dumps(seo[:10]) if seo else "No SEO keywords provided"

    relevant_guidelines = {
        k: v for k, v in PLATFORM_GUIDELINES.items() if k in channels
    }
    guidelines_str = json.dumps(relevant_guidelines, indent=2)

    target_languages = state.get("target_languages") or []
    if target_languages:
        language_instructions = (
            "## Multi-language requirement\n"
            f"Target languages: {', '.join(target_languages)}.\n"
            "For each logical post, produce one JSON object per language (same platform/title intent), "
            "or include a \"language\" field on each piece with the full body and hashtags in that language. "
            "Cover every requested platform for each target language."
        )
    else:
        language_instructions = (
            "## Language\n"
            "Generate all content in the primary language of the brand brief unless the brief specifies otherwise."
        )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(
            brand_context=brand_str,
            strategy=strategy_str,
            seo_keywords=seo_str,
            platform_guidelines=guidelines_str,
            post_count=post_count,
            language_instructions=language_instructions,
        )),
        ("human", f"Create {post_count} content pieces for platforms: {', '.join(channels)}"),
    ]

    response = await llm.ainvoke(messages)

    try:
        pieces = json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("[")
        end = content.rfind("]") + 1
        if start != -1 and end > start:
            pieces = json.loads(content[start:end])
        else:
            pieces = [{"platform": channels[0], "content_type": "post", "title": "Generated Post", "body": response.content, "hashtags": []}]

    if isinstance(pieces, dict):
        pieces = [pieces]

    return {
        "content_pieces": pieces,
        "current_agent": "content",
    }
