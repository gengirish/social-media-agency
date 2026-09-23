"""Launch/PR, Community-Space and Outreach/Partnership agents (Cadence parity).

Ports ``generatePRFAQStressTest``, ``generateLaunchKit``,
``generateCommunityKit`` and ``generateOutreachPitch``. Each writes a kit the
human uses by hand: nothing here submits to Product Hunt, emails a journalist,
deploys a Discord/Slack bot or contacts a partner.

Campaign focus: the launch kit, community kit and outreach pitch read it (via
``brand_prompt_block``). The PRFAQ stress-test deliberately does NOT — it judges
positioning quality on its own, independent of whatever campaign is running
this month (CREW_CONTEXT_PACK §3, "Campaign wiring").

Tiers: the stress-test is a critique, so it uses ``brain`` (the tier QA/Brand
review uses); the three kits are writing work on ``worker``.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agency.agents.lifecycle_email import llm_text
from agency.agents.utils import parse_llm_json
from agency.services.brand_context import brand_prompt_block
from agency.services.llm_provider import get_brain_llm, get_worker_llm

KIT_TEMPERATURE = 0.7

SYSTEM_PROMPT = (
    "You write launch, community and partnership material for the brand described by the "
    "user. Never invent customers, press coverage, metrics, prices or quotes that are not in "
    "the brand context. Return ONLY JSON, no markdown fences."
)

CAMPAIGN_NOTE = (
    "(Where an active campaign is listed, reflect it specifically where it fits naturally, "
    "rather than writing about the brand in the abstract.)"
)


def _brand(brand: dict[str, Any], *, with_campaign: bool = True) -> str:
    if with_campaign:
        return f"## Brand\n{brand_prompt_block(brand)}\n{CAMPAIGN_NOTE}"
    # Drop the Setup extras (where the campaign focus lives) for the stress-test.
    return f"## Brand\n{brand_prompt_block({**brand, 'setup': {}})}"


def build_prfaq_prompt(brand: dict[str, Any]) -> str:
    return (
        f"{_brand(brand, with_campaign=False)}\n\n"
        'You are running an Amazon-style "Working Backwards" PRFAQ stress-test for this brand.\n\n'
        "Write the press release exactly as if this product already launched and got covered — "
        "imagine a real tech/industry outlet wrote about it. Then write a customer FAQ (3 "
        "questions "
        "a genuinely skeptical customer would ask) and an internal FAQ (3 tough questions a "
        "co-founder or investor would ask about feasibility, market size, or defensibility).\n\n"
        "Then, critically: does this actually read as compelling, or does it lean on generic "
        "claims "
        'that could describe almost any product ("game-changing," "seamless," "all-in-one")? Name '
        "the single weakest or most generic claim in the current positioning and what a sharper "
        "version would need to say instead. Be genuinely critical — if you can't write a "
        "compelling "
        "press release, that's real signal the positioning isn't sharp enough yet, not something "
        "to paper over.\n\n"
        'Return ONLY JSON: {"pressReleaseHeadline": string, "pressReleaseBody": string, '
        '"customerFAQ": [{"question": string, "answer": string}], "internalFAQ": [{"question": '
        'string, "answer": string}], "weakestClaim": string, "sharperVersionNote": string}'
    )


def build_launch_kit_prompt(brand: dict[str, Any], prfaq: dict[str, Any] | None) -> str:
    stress = ""
    if prfaq:
        stress = (
            "\n\nA PRFAQ stress-test was already run on this positioning. Its mock press release "
            f'headline was: "{prfaq.get("press_release_headline", "")}". The identified weak spot '
            f'was: "{prfaq.get("weakest_claim", "")}" — a sharper version would say: '
            f'"{prfaq.get("sharper_version_note", "")}". Make sure the launch kit\'s tagline and '
            "maker comment actually address this gap rather than repeating the same generic "
            "framing."
        )
    return (
        f"{_brand(brand)}\n\n"
        "You are a launch/PR strategist. Write a complete launch kit.\n\n"
        "Product Hunt rules: tagline is 60 characters max, punchy, no fluff words like "
        '"revolutionary" or "game-changing". Description is 200-260 characters covering what it '
        "is, who it's for, and the actual differentiator. The maker's first comment is the single "
        "most important piece — Product Hunt's culture punishes anything that reads like more "
        "marketing copy. It must be an authentic founder story: why you built this, a real "
        "specific "
        "detail about the build, and a genuine invitation for feedback — never a second sales "
        "pitch. "
        "Note the real best-practice launch timing (12:01am PST, Tuesday-Thursday performs best, "
        "avoid Mondays and weekends).\n\n"
        'Press pitch rules: subject line a journalist would actually open (specific, not "Check '
        'out my new app"), body is 3-4 sentences with a concrete "why now" news hook — what makes '
        'this newsworthy today specifically, not just that it exists. No generic "I think your '
        f'readers would love this" filler.{stress}\n\n'
        'Return ONLY JSON: {"tagline": string, "phDescription": string, "makerComment": string, '
        '"launchTimingNote": string, "whyNowHook": string, "pressPitchSubject": string, '
        '"pressPitchBody": string}'
    )


def build_community_kit_prompt(brand: dict[str, Any]) -> str:
    return (
        f"{_brand(brand)}\n\n"
        "You are a community strategist setting up a Discord/Slack space for this brand.\n\n"
        "Design a minimal channel structure — 4-6 channels max, more kills early communities "
        "before "
        "they start. Each needs a one-line purpose. Write a welcome message that gets a new member "
        'to take one specific first action, not just "welcome, introduce yourself." Write 3 '
        "engagement prompts that work as recurring discussion starters (not one-off questions that "
        "die after one reply). Write one event/AMA announcement template. Moderation note: how to "
        "keep the space feeling alive and not over-moderated/corporate.\n\n"
        'Return ONLY JSON: {"channelStructure": string[], "welcomeMessage": string, '
        '"engagementPrompts": string[], "eventAnnouncementTemplate": string, "moderationNote": '
        'string}'
    )


def build_outreach_prompt(brand: dict[str, Any]) -> str:
    return (
        f"{_brand(brand)}\n\n"
        "You are a partnerships/outreach strategist. Write a cold-outreach pitch to a "
        "micro-influencer or complementary product for a partnership/collab. Frame it around "
        "mutual "
        'value, not just "please promote me" — what\'s actually in it for them. End with one '
        'specific, low-friction ask (not a vague "let\'s hop on a call"). Include a brief honest '
        "note on typical exchange economics for a micro-influencer partnership at this stage (e.g. "
        "product access + revenue share vs flat fee ranges) — general guidance, not fabricated "
        "specific numbers.\n\n"
        'Return ONLY JSON: {"targetType": string, "subject": string, "pitchBody": string, '
        '"specificAsk": string, "economicsNote": string}'
    )


async def _call(llm: Any, prompt: str) -> Any:
    response = await llm.ainvoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    return parse_llm_json(llm_text(response))


async def generate_prfaq(brand: dict[str, Any]) -> Any:
    return await _call(get_brain_llm(), build_prfaq_prompt(brand))


async def generate_launch_kit(brand: dict[str, Any], prfaq: dict[str, Any] | None) -> Any:
    return await _call(get_worker_llm(KIT_TEMPERATURE), build_launch_kit_prompt(brand, prfaq))


async def generate_community_kit(brand: dict[str, Any]) -> Any:
    return await _call(get_worker_llm(KIT_TEMPERATURE), build_community_kit_prompt(brand))


async def generate_outreach_pitch(brand: dict[str, Any]) -> Any:
    return await _call(get_worker_llm(KIT_TEMPERATURE), build_outreach_prompt(brand))
