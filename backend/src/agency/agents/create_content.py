"""Create › Content agents — blog post, comparison page, niche scan, video script, AI-SEO.

Ports of Cadence's generateSEOContent / generateComparisonPage /
generateNicheScan / generateShortFormScript / generateAISeoPack. Not nodes in
the campaign graph; called directly by ``routers/create_content.py``.

All five use the ``worker`` tier: each output's value *is* the judgement in it
(which keyword, which gap, what is fair to say about a named rival), which is
what ``lite`` is explicitly not for.

Web research: Cadence's comparison page and niche scan ran the model with a
web-search tool. Here retrieval goes through the shared Exa client first
(``competitive_intel.gather_sources``) and the retrieved documents are handed
to the model as its only evidence. When Exa is not configured or returns
nothing, the model is told it has no web access, and the router stamps the
saved asset with ``webResearch.status = "unavailable"`` — the output never
claims to have browsed.

Every function returns the model's parsed JSON; shape validation lives in
``services/create_content.py`` so it is enforced in code, not trusted.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agency.agents.utils import parse_llm_json
from agency.services.brand_context import brand_prompt_block
from agency.services.llm_provider import get_worker_llm

BLOG_TEMPERATURE = 0.7
COMPARISON_TEMPERATURE = 0.5
SCAN_TEMPERATURE = 0.4
VIDEO_TEMPERATURE = 0.8
AI_SEO_TEMPERATURE = 0.3

SYSTEM = (
    "You are one specialist on a small marketing crew writing for a real client. "
    "Never invent numbers, customers, quotes, results, prices or features. "
    "Return ONLY JSON, no markdown fences."
)


def _text_of(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # Anthropic content blocks
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


async def _call(prompt: str, temperature: float) -> Any:
    llm = get_worker_llm(temperature)
    response = await llm.ainvoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
    return parse_llm_json(_text_of(response))


def _audience(brand: dict[str, Any]) -> str:
    return str(brand.get("target_audience") or "its target audience")


def render_sources(sources: list[dict[str, Any]]) -> str:
    blocks = []
    for s in sources:
        blocks.append(
            f"[{s.get('id')}] competitor: {s.get('competitor')}\n"
            f"title: {s.get('title')}\nurl: {s.get('url')}\n"
            f"published: {s.get('published_date') or 'not provided'}\n"
            f"text: {s.get('excerpt') or '(no page text retrieved)'}"
        )
    return "\n\n".join(blocks)


def research_block(sources: list[dict[str, Any]]) -> str:
    """The evidence section: retrieved documents, or an explicit no-web-access notice."""
    if sources:
        return (
            "## Retrieved web documents (live search, just now)\n"
            "These are the ONLY evidence you may use about any named competitor. Do not add "
            "anything you remember about them that these documents do not show.\n\n"
            + render_sources(sources)
        )
    return (
        "## No live web data\n"
        "You have NO web access for this request and no documents were retrieved. Do not "
        "state specific current facts about any named competitor (pricing, features, "
        "campaigns, numbers). Where a point depends on current facts, say it needs checking "
        "rather than guessing. Say plainly in your notes that this was written without live "
        "web research."
    )


# ---------------------------------------------------------------------------
# Blog post (SEO content)
# ---------------------------------------------------------------------------
def build_blog_prompt(
    brand: dict[str, Any], used_keywords: list[str], gap: str | None = None
) -> str:
    memory = (
        "\n\nKeywords already targeted for this client (real history, not invented performance "
        f"data): {', '.join(used_keywords)}. Do not repeat any of these. Where it makes sense, "
        "pick a keyword that builds topical depth alongside them, part of the same cluster a "
        "search engine would recognise as related expertise, but a fresh, unrelated keyword is "
        "fine too if none of them sets up a natural next topic."
        if used_keywords
        else ""
    )
    campaign = (
        "\n\nIf the brand's active campaign (above) fits naturally with a real, rankable keyword "
        "opportunity, lean toward it, but never force it into a keyword that would not genuinely "
        "have search intent."
    )
    gap_line = (
        "\n\nThis post must address a specific gap found in a competitor niche scan: "
        f'"{gap}". Pick the keyword and angle to serve that gap.'
        if gap
        else ""
    )
    return (
        "You are an SEO content strategist.\n\n"
        f"{brand_prompt_block(brand)}\n\n"
        f"Pick ONE realistic keyword this brand could actually rank for with {_audience(brand)}: "
        "not just the brand name, something with genuine search intent a real person would type "
        '(e.g. "how to X" or "best tool for Y"), matched to where this brand is strong. Then '
        f"write a real, publishable blog post draft targeting it.{memory}{campaign}{gap_line}\n\n"
        "SEO rules: title tag 50-60 characters; meta description 150-160 characters and "
        "includes the keyword naturally; outline uses H2-level headers covering related search "
        "intent (not keyword-stuffed repeats); body is 500-700 words, genuinely useful, keyword "
        "appears naturally 3-5 times including once in the first 100 words.\n\n"
        'Return ONLY JSON: {"keyword": string, "searchIntent": string, "title": string, '
        '"metaDescription": string, "outline": string[], "body": string}'
    )


async def generate_blog_post(
    brand: dict[str, Any], used_keywords: list[str], gap: str | None = None
) -> Any:
    return await _call(build_blog_prompt(brand, used_keywords, gap), BLOG_TEMPERATURE)


# ---------------------------------------------------------------------------
# Comparison page (Competitors)
# ---------------------------------------------------------------------------
def build_comparison_prompt(
    brand: dict[str, Any], competitor: str, sources: list[dict[str, Any]]
) -> str:
    name = brand.get("brand_name") or "the brand"
    return (
        f'You are writing a comparison / alternative landing page: "{name} vs {competitor}".\n\n'
        f"{brand_prompt_block(brand)}\n\n"
        f"{research_block(sources)}\n\n"
        f"You must not invent features, pricing or claims about {competitor}. If the evidence "
        'does not support a specific point, use honest generic framing (e.g. "may vary by plan") '
        "instead of a fabricated one.\n\n"
        "Write a fair comparison, not a hit piece: it will be read by people evaluating both "
        "tools honestly, and disparaging a real competitor with unfounded claims is dishonest and "
        "against most platforms' policies. Every comparison point must be something a reader "
        f"could verify. Include one honest paragraph on what {competitor} is genuinely better "
        "at.\n\n"
        "Structure: SEO title under 60 characters, meta description 150-160 characters, one "
        "intro paragraph framing who the page is for, 4-6 comparison points each covering one "
        "dimension (pricing model, target user, standout feature, integration depth, ...) stated "
        'fairly for both sides, the honest "where they win" paragraph, and a closing CTA.\n\n'
        'Return ONLY JSON: {"title": string, "metaDescription": string, "introParagraph": string, '
        '"comparisonPoints": [{"dimension": string, "us": string, "them": string}], '
        '"honestWhereTheyWin": string, "cta": string}'
    )


async def generate_comparison_page(
    brand: dict[str, Any], competitor: str, sources: list[dict[str, Any]]
) -> Any:
    return await _call(build_comparison_prompt(brand, competitor, sources), COMPARISON_TEMPERATURE)


# ---------------------------------------------------------------------------
# Niche scan
# ---------------------------------------------------------------------------
def build_niche_scan_prompt(
    brand: dict[str, Any], competitors: list[str], sources: list[dict[str, Any]]
) -> str:
    return (
        "You are scanning a competitive niche for this brand.\n\n"
        f"{brand_prompt_block(brand)}\n\n"
        f"Named competitors (the human chose these): {', '.join(competitors)}.\n\n"
        f"{research_block(sources)}\n\n"
        "Do not invent features, campaigns or content angles for any of them: every angle must be "
        "based on the evidence above. If you have nothing reliable for one of them, say so plainly "
        "in sourcesNote rather than fabricating a placeholder.\n\n"
        "Identify 4-6 distinct content or positioning angles used across these competitors (e.g. "
        '"founder-story video", "free tier as the hook", "integration marketplace as '
        'differentiator"). For each, list which of the NAMED competitors use it (usedBy, exact '
        "names from the list) and how saturated it looks in this set (high/medium/low). Then "
        "suggest exactly ONE differentiated angle this brand could take that is not already "
        "crowded here, grounded in what makes this brand different, not a copy of what already "
        "works for someone else.\n\n"
        'Return ONLY JSON: {"angles": [{"angle": string, "usedBy": [string], '
        '"saturation": "high"|"medium"|"low", "note": string}], "gapRecommendation": string, '
        '"sourcesNote": string}'
    )


async def generate_niche_scan(
    brand: dict[str, Any], competitors: list[str], sources: list[dict[str, Any]]
) -> Any:
    return await _call(build_niche_scan_prompt(brand, competitors, sources), SCAN_TEMPERATURE)


# ---------------------------------------------------------------------------
# Short-form video script
# ---------------------------------------------------------------------------
def build_video_script_prompt(brand: dict[str, Any]) -> str:
    return (
        "You are a short-form video strategist (TikTok / Reels / Shorts).\n\n"
        f"{brand_prompt_block(brand)}\n\n"
        "Write a shootable SCRIPT, 15-40 seconds. You are not making a video; a person will film "
        'it. The hook must land in the first 2 seconds: no slow build-up, no "hey guys" intro. '
        "Native, unpolished beats produced on these platforms, so write for someone talking to "
        "camera or doing a quick screen recording, not a commercial. Break it into sequential "
        "beats with rough timing. On-screen text should reinforce the spoken hook for sound-off "
        "viewers.\n\n"
        'For audio, describe the STYLE that tends to work (e.g. "upbeat instrumental" or '
        '"voiceover only, no music") rather than naming a specific trending sound: you cannot '
        "verify what is trending right now, and an outdated or invented song is worse than none."
        "\n\n"
        'Return ONLY JSON: {"hook": string, "scriptBeats": string[], "onScreenText": string[], '
        '"audioStyleNote": string, "caption": string, "hashtags": string[]}'
    )


async def generate_video_script(brand: dict[str, Any]) -> Any:
    return await _call(build_video_script_prompt(brand), VIDEO_TEMPERATURE)


# ---------------------------------------------------------------------------
# AI-SEO pack (attached to an existing blog post)
# ---------------------------------------------------------------------------
def build_ai_seo_prompt(brand: dict[str, Any], blog: dict[str, Any]) -> str:
    name = brand.get("brand_name") or "the brand"
    return (
        "You are optimizing an existing blog draft to be cited by AI search engines (ChatGPT, "
        "Perplexity, Google AI Overviews). That is a different discipline from ranking in "
        "traditional search: these engines extract and cite short, self-contained, directly "
        "answering passages rather than crawling a full page.\n\n"
        f'Blog draft for "{name}":\nTitle: {blog.get("title")}\n'
        f'Target keyword: {blog.get("keyword")}\nBody:\n"""{blog.get("body")}"""\n\n'
        "Produce four things, all grounded in what is actually in this draft. Do not introduce "
        "any claim that is not already here:\n"
        "1. citableSummary: one self-contained paragraph (40-60 words) that directly answers the "
        "core question of the post, quotable verbatim without surrounding context.\n"
        "2. faq: 3-4 question/answer pairs drawn from the draft, each answer 1-3 sentences, "
        'answer-first, no throat-clearing like "Great question!".\n'
        f'3. entityClarityNotes: is "{name}" named clearly and consistently enough for an AI '
        "engine to attribute the answer to this brand rather than give a generic answer? Flag "
        "anything ambiguous.\n"
        "4. llmsTxtEntry: a suggested llms.txt line in the form "
        '"- [{title}](/blog/your-slug-here): {one-line description}". Keep the literal '
        "placeholder URL; the real page location is not known.\n\n"
        'Return ONLY JSON: {"citableSummary": string, "faq": [{"question": string, '
        '"answer": string}], "entityClarityNotes": string, "llmsTxtEntry": string}'
    )


async def generate_ai_seo_pack(brand: dict[str, Any], blog: dict[str, Any]) -> Any:
    return await _call(build_ai_seo_prompt(brand, blog), AI_SEO_TEMPERATURE)
