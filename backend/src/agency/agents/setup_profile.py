"""Setup › Profile agents — answer coaching, Brand Voice guide, Strategy Lens Panel.

Ports Cadence's ``evaluateAnswerSpecificity``, ``generateBrandVoice`` and
``generateStrategyLensPanel``. Not nodes in the campaign graph; called directly
by ``routers/setup.py``.

All three use the ``worker`` tier: whether an answer is genuinely specific,
what a brand should and should not sound like, and where four frameworks
disagree are all judgement calls — ``lite`` is only for transforming text.

Model output is never trusted: every reply is parsed defensively and validated
into a fixed shape here. A reply that does not validate raises
:class:`MalformedGenerationError`, which the router turns into a 502 without
charging quota and without saving anything.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agency.agents.utils import parse_llm_json
from agency.services.llm_provider import get_worker_llm

COACHING_TEMPERATURE = 0.3
BRAND_VOICE_TEMPERATURE = 0.7
STRATEGY_LENS_TEMPERATURE = 0.6

MAX_VOCAB = 8
MAX_FIELD = 2000

#: Cadence's four frameworks, in order. The panel must cover each exactly once.
STRATEGY_FRAMEWORKS: tuple[tuple[str, str], ...] = (
    ("Jobs-to-be-Done", "Clayton Christensen"),
    ("Category Design", "April Dunford"),
    ("Blue Ocean Strategy (ERRC grid)", "Kim & Mauborgne"),
    ("Distinctive Assets / Mental Availability", "Byron Sharp, How Brands Grow"),
)


class MalformedGenerationError(ValueError):
    """The model replied, but not in a shape we can use."""


def _text_of(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks (Anthropic)
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _str(value: Any, limit: int = MAX_FIELD) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _words(values: Any, limit: int = MAX_VOCAB) -> list[str]:
    """Trimmed, de-duplicated (case-insensitive) short strings, order kept."""
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        s = _str(v, 80)
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out[:limit]


def _product_line(brand: dict[str, Any]) -> str:
    name = brand.get("brand_name") or "the client"
    site = brand.get("website_url") or ""
    return f'"{name}"' + (f" ({site})" if site else "")


async def _ask(system: str, prompt: str, temperature: float) -> dict[str, Any]:
    llm = get_worker_llm(temperature)
    response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    parsed = parse_llm_json(_text_of(response))
    if not isinstance(parsed, dict):
        raise MalformedGenerationError("expected a JSON object")
    return parsed


# ---------------------------------------------------------------------------
# Push-back coaching (Cadence: evaluateAnswerSpecificity)
# ---------------------------------------------------------------------------
COACHING_SYSTEM = """You review answers to a brand positioning questionnaire. \
Be genuinely critical, not automatically encouraging — most first-pass answers \
are thin, and this check exists to catch that before the answer flows into \
every piece of generated content. Advisory only: the human can always keep \
their answer.

Return ONLY JSON, no markdown fences: {"isThin": boolean, "coachingNote": string}"""


async def evaluate_answer(*, question: str, answer: str, brand: dict[str, Any]) -> dict[str, Any]:
    """``{"is_thin": bool, "coaching_note": str}``. Raises on LLM failure."""
    prompt = (
        f"An agency is filling out a positioning profile for {_product_line(brand)}. "
        f'They were asked: "{question}"\n\nThey answered: "{answer}"\n\n'
        "Evaluate whether this answer is specific enough to actually differentiate this "
        "client, or whether it is generic/padded enough that it could describe almost any "
        'business in this general space (e.g. "better UX", "easier to use", "more '
        'affordable", "for everyone" are classic thin answers).\n\n'
        "If it is thin, write one short, direct coaching note (1-2 sentences) naming the "
        "actual gap and what a sharper answer would include — don't just say \"be more "
        'specific." If the answer is already genuinely specific, say so plainly.'
    )
    parsed = await _ask(COACHING_SYSTEM, prompt, COACHING_TEMPERATURE)
    is_thin = parsed.get("isThin", parsed.get("is_thin"))
    note = _str(parsed.get("coachingNote", parsed.get("coaching_note")), 600)
    if not isinstance(is_thin, bool):
        raise MalformedGenerationError("isThin missing")
    if is_thin and not note:
        raise MalformedGenerationError("thin answer without a coaching note")
    return {"is_thin": is_thin, "coaching_note": note}


# ---------------------------------------------------------------------------
# Brand Voice guide (Cadence: generateBrandVoice)
# ---------------------------------------------------------------------------
BRAND_VOICE_SYSTEM = """You are a brand voice strategist. You expand a coarse \
voice register into a fuller brand voice guide that every piece of content — \
social posts, blog posts, emails, launch copy — can consistently follow, so \
different content types sound like the same brand. Never invent facts, \
customers or numbers about the business.

Return ONLY JSON, no markdown fences: {"voiceDescription": string, \
"vocabularyDos": [string], "vocabularyDonts": [string], "exampleSentence": string}"""


def build_brand_voice_prompt(brand: dict[str, Any], answers: dict[str, str]) -> str:
    audience = answers.get("audience") or "its audience"
    differentiator = answers.get("differentiator") or "what sets it apart"
    tone = answers.get("tone") or "Friendly & casual"
    about = f"\nWhat it is: {brand['description']}" if brand.get("description") else ""
    return (
        f"Client: {_product_line(brand)}, for {audience}. Its edge: {differentiator}.{about}\n"
        f"Their chosen voice register: {tone}.\n\n"
        "Produce: 1) a one-paragraph voice description covering sentence rhythm, formality "
        'level, and personality; 2) 5-8 vocabulary "do" words/phrases genuinely specific to '
        'this brand, not generic filler like "great" or "amazing"; 3) 5-8 vocabulary "don\'t" '
        "words/phrases that would clash with this voice (e.g. corporate jargon for a casual "
        "brand, or slang for a formal one); 4) one example sentence, written exactly in this "
        "voice, about this client, that could be dropped into any piece of content as a north star."
    )


def validate_brand_voice(parsed: dict[str, Any]) -> dict[str, Any]:
    guide = {
        "voice_description": _str(parsed.get("voiceDescription")),
        "vocabulary_include": _words(parsed.get("vocabularyDos")),
        "vocabulary_exclude": _words(parsed.get("vocabularyDonts")),
        "example_sentence": _str(parsed.get("exampleSentence"), 500),
    }
    if not guide["voice_description"] or not guide["example_sentence"]:
        raise MalformedGenerationError("brand voice guide is missing its description or example")
    if not guide["vocabulary_include"] or not guide["vocabulary_exclude"]:
        raise MalformedGenerationError("brand voice guide is missing vocabulary")
    return guide


async def generate_brand_voice(brand: dict[str, Any], answers: dict[str, str]) -> dict[str, Any]:
    parsed = await _ask(
        BRAND_VOICE_SYSTEM, build_brand_voice_prompt(brand, answers), BRAND_VOICE_TEMPERATURE
    )
    return validate_brand_voice(parsed)


# ---------------------------------------------------------------------------
# Strategy Lens Panel (Cadence: generateStrategyLensPanel)
# ---------------------------------------------------------------------------
STRATEGY_LENS_SYSTEM = """You run a structured multi-framework critique of a \
brand's positioning — several well-established, named marketing frameworks \
applied independently, so real tension between them can surface. This is \
framework-based analysis, not impersonation of any person: cite each \
framework's real origin by name as attribution, but write the critique itself \
as objective analysis using that framework's logic, never as a simulated \
first-person quote from that person. Never invent facts or numbers about the \
business.

Return ONLY JSON, no markdown fences: {"lenses": [{"framework": string, \
"origin": string, "critique": string, "suggestion": string}], "tension": \
string, "synthesis": string}"""


def build_strategy_lens_prompt(brand: dict[str, Any], answers: dict[str, str]) -> str:
    audience = answers.get("audience") or "its audience"
    differentiator = answers.get("differentiator") or "not stated"
    return (
        f"Client: {_product_line(brand)}, for {audience}. Its claimed edge: {differentiator}.\n\n"
        "Apply these four frameworks independently:\n"
        "1. Jobs-to-be-Done (Clayton Christensen) — what job is the customer actually hiring "
        "this for, and does the stated differentiator address that job or something adjacent?\n"
        '2. Category Design (April Dunford) — is this positioned as "a better X" within an '
        "existing category, or does the differentiator require naming a new category to be "
        'understood? Vague "better X" positioning is a common failure this framework catches.\n'
        "3. Blue Ocean Strategy's Eliminate-Reduce-Raise-Create grid (Kim & Mauborgne) — "
        "relative to the obvious alternative, what should this eliminate or reduce that "
        "competitors compete on, and raise or create that nobody else offers?\n"
        '4. Distinctive Assets / Mental Availability (Byron Sharp, "How Brands Grow") — is the '
        "stated differentiator something a customer could actually remember and recognize "
        "later, or reasoning that sounds fine in the moment but builds no lasting recognition?\n\n"
        "For each framework, write a real critique (be genuinely critical, not encouraging by "
        "default) and one concrete suggestion. Then, in 1-2 sentences, name the sharpest place "
        "these four frameworks genuinely pull in different directions — real tension, not "
        "manufactured for effect. Finally, given that tension, name the single most actionable "
        "next step to take."
    )


def validate_strategy_lens(parsed: dict[str, Any]) -> dict[str, Any]:
    raw = parsed.get("lenses")
    lenses: list[dict[str, str]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        lens = {
            "framework": _str(item.get("framework"), 120),
            "origin": _str(item.get("origin"), 160),
            "critique": _str(item.get("critique")),
            "suggestion": _str(item.get("suggestion")),
        }
        if all(lens.values()):
            lenses.append(lens)
    tension = _str(parsed.get("tension"))
    synthesis = _str(parsed.get("synthesis"))
    if len(lenses) < len(STRATEGY_FRAMEWORKS) or not tension or not synthesis:
        raise MalformedGenerationError("strategy lens panel is incomplete")
    return {
        "lenses": lenses[: len(STRATEGY_FRAMEWORKS)],
        "tension": tension,
        "synthesis": synthesis,
    }


async def generate_strategy_lens(brand: dict[str, Any], answers: dict[str, str]) -> dict[str, Any]:
    parsed = await _ask(
        STRATEGY_LENS_SYSTEM,
        build_strategy_lens_prompt(brand, answers),
        STRATEGY_LENS_TEMPERATURE,
    )
    return validate_strategy_lens(parsed)
