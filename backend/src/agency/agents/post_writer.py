"""Post writer — one platform-native draft, and the Creative Director's brief.

Cadence's ``generatePlatformPost`` and ``generateCreativeBrief``, moved server
side. Not a node in the campaign graph; called by ``services/post_studio.py``
for the Queue's "Generate a post", "Regenerate" and "Get a creative brief".

Both use the ``worker`` tier: whether a post is any good, and whether a brief
is something a designer could actually execute, *is* the judgement — that is
not ``lite`` work (CLAUDE.md, LLM routing).

Model output is never trusted to have obeyed: shapes are validated in code and
anything unusable raises :class:`PostWriterError`, which the router turns into a
502 without charging quota.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from agency.agents.utils import parse_llm_json
from agency.services.brand_context import brand_prompt_block
from agency.services.llm_provider import get_worker_llm
from agency.services.repurpose import PLATFORM_CHAR_LIMITS, PLATFORM_FORMATS, rendered_length

logger = structlog.get_logger()

POST_TEMPERATURE = 0.8
BRIEF_TEMPERATURE = 0.7

#: Cadence caps the "what's this post about?" note at 280 characters.
MAX_CONTEXT_NOTE = 280

#: The seven fields of Cadence's creative brief, in display order.
BRIEF_FIELDS: tuple[str, ...] = (
    "visualConcept",
    "composition",
    "style",
    "colorDirection",
    "textOverlay",
    "aspectRatio",
    "altText",
)


class PostWriterError(Exception):
    """The model returned nothing usable. Nothing may be saved or charged."""


POST_SYSTEM_PROMPT = """You write ONE social post for a brand, native to the \
platform it is for.

Hard rules:
1. Write in the brand's voice below. Respect its vocabulary lists and emoji policy.
2. Never invent a claim, number, customer, quote, award or result. If the brand \
context does not give you a fact, do not state one.
3. Never promise outcomes or predict performance.
4. Respect the platform's format and hard character limit. Hashtags go in the \
"hashtags" array WITHOUT the # symbol, never in the body; they count toward the \
limit when published.
5. No generic openers ("Excited to announce", "In today's fast-paced world").

Return ONLY JSON, no markdown fences:
{"title": string, "body": string, "hashtags": [string]}
"title" is a short internal label for the queue (under 80 characters), not part \
of the post."""


BRIEF_SYSTEM_PROMPT = """You are a creative director briefing a designer for one \
social post. The designer will make the visual; you write the brief.

Write a brief a designer could execute without asking follow-up questions. \
Decide whether a photo, illustration, screenshot or text-on-colour-field graphic \
actually fits THIS post best — do not default to generic stock-photo thinking. \
Any text overlay must complement the caption, never repeat it. Alt text must \
describe the intended image for a screen-reader user, not the post.

Return ONLY JSON, no markdown fences:
{"visualConcept": string, "composition": string, "style": string, \
"colorDirection": string, "textOverlay": string, "aspectRatio": string, \
"altText": string}"""


def _text_of(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks (Anthropic)
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _clean_hashtags(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for tag in raw:
        t = str(tag).strip().lstrip("#").strip()
        if t and " " not in t and t not in out:
            out.append(t)
    return out[:10]


def build_post_prompt(
    *,
    platform: str,
    brand: dict[str, Any],
    context_note: str = "",
    previous_body: str | None = None,
) -> str:
    note = context_note.strip()[:MAX_CONTEXT_NOTE]
    # Cadence: a per-post note wins; with none, the standing campaign focus
    # (already inside brand_prompt_block) is the default subject.
    about = (
        "\n## What this specific post is about, in the user's own words\n"
        f'"{note}"\nWrite specifically about this — do not fall back to a generic post '
        "about the brand overall.\n"
        if note
        else ""
    )
    previous = (
        "\n## The draft being replaced\nThe user asked for a different take. Do not reuse "
        f'its opening line or structure:\n"""{previous_body[:1500]}"""\n'
        if previous_body
        else ""
    )
    return f"""## Brand
{brand_prompt_block(brand)}
{about}{previous}
## Platform
{platform}: {PLATFORM_FORMATS.get(platform, "a few plain sentences")}.
Hard limit: {PLATFORM_CHAR_LIMITS[platform]} characters including hashtags."""


def validate_post(parsed: Any, platform: str) -> dict[str, Any]:
    """Shape-check a post. Raises :class:`PostWriterError` on anything unusable."""
    if not isinstance(parsed, dict):
        raise PostWriterError("Model did not return a JSON object")
    body = str(parsed.get("body") or "").strip()
    if not body:
        raise PostWriterError("Model returned an empty post")
    hashtags = _clean_hashtags(parsed.get("hashtags"))
    limit = PLATFORM_CHAR_LIMITS[platform]
    if rendered_length(body, hashtags) > limit:
        raise PostWriterError(f"Draft came back over the {limit}-character limit")
    title = str(parsed.get("title") or "").strip()[:200] or body.split("\n", 1)[0][:80]
    return {"title": title, "body": body, "hashtags": hashtags}


async def generate_platform_post(
    *,
    platform: str,
    brand: dict[str, Any],
    context_note: str = "",
    previous_body: str | None = None,
) -> dict[str, Any]:
    """One validated ``{title, body, hashtags}`` draft for ``platform``."""
    if platform not in PLATFORM_CHAR_LIMITS:
        raise ValueError(f"Unsupported platform {platform!r}")
    prompt = build_post_prompt(
        platform=platform, brand=brand, context_note=context_note, previous_body=previous_body
    )
    llm = get_worker_llm(POST_TEMPERATURE)
    response = await llm.ainvoke(
        [SystemMessage(content=POST_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    return validate_post(parse_llm_json(_text_of(response)), platform)


def validate_brief(parsed: Any) -> dict[str, str]:
    """All seven fields present and non-empty, or :class:`PostWriterError`."""
    if not isinstance(parsed, dict):
        raise PostWriterError("Model did not return a JSON object")
    brief: dict[str, str] = {}
    missing: list[str] = []
    for key in BRIEF_FIELDS:
        value = str(parsed.get(key) or "").strip()
        if not value:
            missing.append(key)
        brief[key] = value[:1000]
    # "No text overlay" is a legitimate creative decision, so textOverlay may
    # say so — but it must say something.
    if missing:
        raise PostWriterError(f"Brief is missing {', '.join(missing)}")
    return brief


async def generate_creative_brief(
    *, platform: str, body: str, hashtags: list[str], brand: dict[str, Any]
) -> dict[str, str]:
    """A designer-ready brief for the visual that goes with this post."""
    tags = " ".join(f"#{t}" for t in hashtags)
    prompt = f"""## Brand
{brand_prompt_block(brand)}

## The {platform} post the visual goes with
\"\"\"{body[:3000]}{(chr(10) * 2 + tags) if tags else ""}\"\"\""""
    llm = get_worker_llm(BRIEF_TEMPERATURE)
    response = await llm.ainvoke(
        [SystemMessage(content=BRIEF_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    return validate_brief(parse_llm_json(_text_of(response)))
