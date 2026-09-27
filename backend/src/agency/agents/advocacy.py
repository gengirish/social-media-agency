"""Customer advocacy agent — Cadence's review request / case study / proof line.

Not a node in the campaign graph; called by ``routers/insights.py``.

The only numbers it may use are the ``facts`` the server computed from real rows
(``services.insights.advocacy_facts``). The prompt says so, and
:func:`validate_advocacy` enforces it: any digit sequence in the output that is
not one of those facts rejects the whole generation (502, no quota used). An
invented "grew 300%" never reaches the client.

``worker`` tier: whether the ask is timed around a real win and stays honest is
judgement, not text transformation.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agency.agents.utils import parse_llm_json
from agency.services.brand_context import brand_prompt_block
from agency.services.llm_provider import get_worker_llm

ADVOCACY_TEMPERATURE = 0.7
MAX_OUTLINE = 8
MAX_FIELD_CHARS = 2000

FACT_LABELS: dict[str, str] = {
    "posts_published": "posts published to live accounts",
    "posts_created": "posts drafted in total",
    "moderation_checks": "moderation checks run before approval",
    "connected_platforms": "social platforms connected",
    "posts_with_platform_metrics": "published posts with metrics returned by the platform",
    "total_engagements_measured": "engagements measured across those posts",
}

SYSTEM_PROMPT = """You are a customer advocacy strategist writing for a brand. \
You write three things, each grounded in genuine specifics — never vague hype \
like "growing fast" or "loved by users":
1. A review-request message to send to an engaged customer, timed around a real \
win (not random), with one specific ask (which platform to leave the review on), \
low-pressure tone.
2. A case study outline following problem -> solution -> result, using the real \
numbers given where relevant.
3. A short, shareable social-proof line built from the real numbers — honest \
enough to actually post.

Hard rule on numbers: the ONLY numbers you may write as digits are the exact \
values in "Real numbers". Never invent a percentage, growth rate, customer \
count, revenue, rating or any other figure. Any other quantity must be written \
in words without a figure, or left out. Do not number the outline items.

Return ONLY JSON, no markdown fences:
{"reviewRequestMessage": string, "caseStudyOutline": [string], "socialProofSnippet": string}"""


class AdvocacyError(ValueError):
    """The model's output was unusable; the router answers 502 without charging."""


def build_prompt(brand: dict[str, Any], facts: dict[str, int]) -> str:
    fact_lines = "\n".join(
        f"- {value} {FACT_LABELS.get(key, key.replace('_', ' '))}" for key, value in facts.items()
    )
    return f"""## Brand
{brand_prompt_block(brand)}

## Real numbers (from this workspace; the only figures you may cite)
{fact_lines}"""


_NUMBER = re.compile(r"\d[\d,.]*")


def _tokens(text: str) -> list[str]:
    return [m.rstrip(".,").replace(",", "") for m in _NUMBER.findall(text)]


def invented_numbers(text: str, facts: dict[str, int], brand_text: str = "") -> list[str]:
    """Digit sequences in ``text`` that are neither a real fact nor already in the
    brand's own text (a year in the campaign focus, a product name like "Web3")."""
    allowed = {str(v) for v in facts.values()} | set(_tokens(brand_text))
    bad: list[str] = []
    for match in _NUMBER.findall(text):
        token = match.rstrip(".,").replace(",", "")
        if token and token not in allowed:
            bad.append(match.rstrip(".,"))
    return bad


def validate_advocacy(parsed: Any, facts: dict[str, int], brand_text: str = "") -> dict[str, Any]:
    """Shape-check and number-check the model output, or raise :class:`AdvocacyError`."""
    if not isinstance(parsed, dict):
        raise AdvocacyError("not a JSON object")
    review = str(parsed.get("reviewRequestMessage") or "").strip()
    proof = str(parsed.get("socialProofSnippet") or "").strip()
    outline_raw = parsed.get("caseStudyOutline")
    outline = (
        [str(h).strip() for h in outline_raw if str(h).strip()][:MAX_OUTLINE]
        if isinstance(outline_raw, list)
        else []
    )
    if not review or not proof or not outline:
        raise AdvocacyError("missing a required field")
    result = {
        "reviewRequestMessage": review[:MAX_FIELD_CHARS],
        "caseStudyOutline": [h[:MAX_FIELD_CHARS] for h in outline],
        "socialProofSnippet": proof[:MAX_FIELD_CHARS],
    }
    bad = invented_numbers(" ".join([review, proof, *outline]), facts, brand_text)
    if bad:
        raise AdvocacyError(f"cited numbers that are not real: {', '.join(bad[:5])}")
    return result


def _text_of(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


async def generate_advocacy(*, brand: dict[str, Any], facts: dict[str, int]) -> dict[str, Any]:
    """Generate and validate. Raises the LLM's error or :class:`AdvocacyError`."""
    llm = get_worker_llm(ADVOCACY_TEMPERATURE)
    response = await llm.ainvoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=build_prompt(brand, facts))]
    )
    return validate_advocacy(parse_llm_json(_text_of(response)), facts, brand_prompt_block(brand))
