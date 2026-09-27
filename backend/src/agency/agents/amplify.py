"""Amplify agent — one source, up to 8 angle-distinct platform-native drafts.

Not a node in the campaign graph; called directly by ``routers/amplify.py``.

Uses the ``worker`` tier at 0.8, not ``lite``: ``lite`` is for transforming
text without judgement, and here the judgement *is* the product — whether eight
atoms are genuinely different angles or one sentence reworded eight times.

Angles are assigned before the call (``services.repurpose.plan_atoms``), so the
model is told exactly which angle each atom must take; ``validate_atoms`` then
drops anything off-plan, over its platform limit, or repeating an angle. The
model output is never trusted to have obeyed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from agency.agents.utils import parse_llm_json
from agency.services.llm_provider import get_worker_llm
from agency.services.repurpose import (
    ANGLE_DEFINITIONS,
    PLATFORM_CHAR_LIMITS,
    PLATFORM_FORMATS,
    AtomValidation,
    validate_atoms,
)

logger = structlog.get_logger()

AMPLIFY_TEMPERATURE = 0.8

#: The model needs substance to extract angles from, not an entire long post.
SOURCE_EXCERPT_CHARS = 6000

SYSTEM_PROMPT = """You repurpose ONE existing piece of content into several \
platform-native social posts for a brand. Each post ("atom") commits to a \
different, assigned angle.

Hard rules:
1. Ground every atom in the source. The source is real and already approved; \
never invent a claim, number, customer, quote or result that is not in it.
2. Each atom must genuinely take its assigned angle. Two atoms that restate \
each other in different words is a failure, not a variation.
3. Write in the brand's voice below. Respect its vocabulary and emoji policy.
4. Respect each platform's format and character limit. Hashtags go in the \
"hashtags" array WITHOUT the # symbol, never in the body; they count toward \
the limit when published.
5. Never promise outcomes or state performance predictions.

Return ONLY JSON, no markdown fences:
{"atoms": [{"platform": string, "angle": string, "title": string, \
"body": string, "hashtags": [string]}]}
One entry per numbered request, same order, same platform and angle."""


@dataclass
class AmplifyResult:
    atoms: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


def _lines(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v).strip() for v in values if str(v).strip()]


def _example_post_text(post: Any) -> str:
    if isinstance(post, str):
        return post
    if isinstance(post, dict):
        for key in ("body", "text", "content", "post"):
            if isinstance(post.get(key), str):
                return str(post[key])
    return ""


def format_brand_context(brand: dict[str, Any]) -> str:
    """Render the client's brand profile for the prompt. Empty fields are omitted."""
    out: list[str] = []
    if brand.get("brand_name"):
        out.append(f"Brand: {brand['brand_name']}")
    if brand.get("industry"):
        out.append(f"Industry: {brand['industry']}")
    if brand.get("description"):
        out.append(f"About: {brand['description']}")
    if brand.get("target_audience"):
        out.append(f"Audience: {brand['target_audience']}")
    if brand.get("voice_description"):
        out.append(f"Voice: {brand['voice_description']}")
    tone = brand.get("tone_attributes")
    if isinstance(tone, dict) and tone:
        out.append("Tone (0-1 weights): " + ", ".join(f"{k}={v}" for k, v in tone.items()))
    include = _lines(brand.get("vocabulary_include"))
    if include:
        out.append("Words to use: " + ", ".join(include))
    exclude = _lines(brand.get("vocabulary_exclude"))
    if exclude:
        out.append("NEVER use these words: " + ", ".join(exclude))
    rules = _lines(brand.get("style_rules"))
    if rules:
        out.append("Style rules:\n" + "\n".join(f"- {r}" for r in rules))
    if brand.get("emoji_policy"):
        out.append(f"Emoji policy: {brand['emoji_policy']}")
    examples = [
        _example_post_text(p)[:600]
        for p in (brand.get("example_posts") or [])
        if _example_post_text(p).strip()
    ][:3]
    if examples:
        out.append(
            "Example posts in this brand's voice (match the voice, do not copy):\n"
            + "\n---\n".join(examples)
        )
    return "\n".join(out) if out else "No brand profile on file; write in a clear, plain voice."


def build_prompt(
    *,
    source_text: str,
    requests: list[dict[str, str]],
    brand: dict[str, Any],
    campaign_brief: str | None,
) -> str:
    request_lines = "\n".join(
        f"{i + 1}. platform={r['platform']} angle={r['angle']} — "
        f"format: {PLATFORM_FORMATS.get(r['platform'], 'a few plain sentences')}; "
        f"hard limit {PLATFORM_CHAR_LIMITS[r['platform']]} characters"
        for i, r in enumerate(requests)
    )
    used = {r["angle"] for r in requests}
    glossary = "\n".join(f"- {a}: {d}" for a, d in ANGLE_DEFINITIONS.items() if a in used)
    campaign = (
        f"\n## Campaign this source belongs to\n{campaign_brief}\n" if campaign_brief else ""
    )
    excerpt = source_text[:SOURCE_EXCERPT_CHARS]
    return f"""## Brand
{format_brand_context(brand)}
{campaign}
## Source
\"\"\"{excerpt}\"\"\"

## Angle definitions
{glossary}

## Requests — write exactly {len(requests)} atoms
{request_lines}"""


def _text_of(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks (Anthropic)
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content)


async def generate_amplify_atoms(
    *,
    source_text: str,
    requests: list[dict[str, str]],
    brand: dict[str, Any],
    campaign_brief: str | None = None,
) -> AmplifyResult:
    """Generate and validate atoms for the planned ``requests``.

    Returns only atoms that passed :func:`validate_atoms`; ``dropped`` says why
    the rest were discarded. Raises whatever the LLM client raises — the router
    turns that into a 502 without charging quota.
    """
    if not requests:
        return AmplifyResult()

    prompt = build_prompt(
        source_text=source_text, requests=requests, brand=brand, campaign_brief=campaign_brief
    )
    llm = get_worker_llm(AMPLIFY_TEMPERATURE)
    response = await llm.ainvoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    parsed = parse_llm_json(_text_of(response))
    raw = parsed.get("atoms") if isinstance(parsed, dict) else parsed

    # Only the planned (platform, angle) pairs are acceptable: an atom whose
    # angle the model swapped onto another platform is off-plan.
    planned = {(r["platform"], r["angle"]) for r in requests}
    on_plan: list[Any] = []
    off_plan: list[str] = []
    for i, atom in enumerate(raw if isinstance(raw, list) else []):
        if isinstance(atom, dict):
            key = (
                str(atom.get("platform") or "").strip().lower(),
                str(atom.get("angle") or "").strip().lower(),
            )
            if key not in planned:
                off_plan.append(f"#{i}: {key[0]}/{key[1]} was not requested")
                continue
        on_plan.append(atom)

    checked: AtomValidation = validate_atoms(
        on_plan, sorted({r["platform"] for r in requests}), max_atoms=len(requests)
    )
    dropped = off_plan + checked.dropped
    if dropped:
        logger.warning(
            "amplify_atoms_dropped",
            requested=len(requests),
            kept=len(checked.kept),
            dropped=dropped,
        )
    return AmplifyResult(atoms=checked.kept, dropped=dropped)
