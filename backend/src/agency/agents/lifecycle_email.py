"""Email/Lifecycle agent — Cadence's ``generateEmailCampaign``.

Honest scope: this writes campaign copy (subject + A/B subject, preview text,
body, segment and send-timing notes). It sends nothing — there is no email
service provider integration for a client's customers. The human copies the
campaign into whatever they already send from.

Not a node in the campaign graph; called by ``routers/create_email.py``.
Worker tier: whether the copy is specific rather than generic is the judgement.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agency.agents.utils import parse_llm_json
from agency.services.brand_context import brand_prompt_block
from agency.services.create_kits import EMAIL_CAMPAIGN_TYPES
from agency.services.llm_provider import get_worker_llm

EMAIL_TEMPERATURE = 0.7

SYSTEM_PROMPT = (
    "You are a lifecycle email marketer writing for the brand described by the user. "
    "Never invent customer names, statistics, prices or results that are not in the brand "
    "context. Return ONLY JSON, no markdown fences."
)


def llm_text(response: Any) -> str:
    """Text of a chat-model reply, including Anthropic-style content blocks."""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def build_email_prompt(campaign_type: str, brand: dict[str, Any]) -> str:
    brief = EMAIL_CAMPAIGN_TYPES[campaign_type]
    return (
        f"## Brand\n{brand_prompt_block(brand)}\n"
        "(Where an active campaign is listed, reflect it specifically where it fits "
        "naturally, rather than writing about the brand in the abstract.)\n\n"
        f"Write {brief}.\n\n"
        "Subject line rules: 40-50 characters (mobile preview cutoff), specific not vague, no "
        'spam-trigger words (FREE, ALL CAPS, excessive punctuation, "act now"), curiosity or '
        "specificity over hype. Also write a genuinely different B variant for A/B testing, not a "
        "trivial rewording. Preview text (40-100 chars) must complement the subject line, never "
        "just repeat it. Body: short scannable paragraphs separated by a blank line, exactly one "
        "clear call-to-action (not three competing ones), no corporate boilerplate. Include a "
        "one-line note on who should receive this (segment) and general best-practice send timing "
        "(day/time window, not a fake personalized stat).\n\n"
        'Return ONLY JSON: {"subjectLine": string, "subjectLineB": string, "previewText": string, '
        '"segmentNote": string, "sendTimeNote": string, "body": string}'
    )


async def generate_email_campaign(campaign_type: str, brand: dict[str, Any]) -> Any:
    """Raw parsed model output; ``services.create_kits.validate_email_campaign`` checks it."""
    llm = get_worker_llm(EMAIL_TEMPERATURE)
    response = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_email_prompt(campaign_type, brand)),
        ]
    )
    return parse_llm_json(llm_text(response))
