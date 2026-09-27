"""Create › Ads agents — Google Ads (RSA asset set) and Meta Ads copy.

Not a node in the campaign graph (the pipeline's ``ad_copy.py`` is separate and
untouched); called directly by ``routers/create_ads.py``.

Copy and structure only. There is no Google Ads API or Meta Marketing API here:
nothing creates campaigns, sets budgets or spends money, and no prompt asks for
— and no code ever produces — a CTR, CPC, ROAS or conversion prediction.

Tiers: generation uses ``get_ad_copy_llm()`` (the ad-copy tier); the advisory
moderation pass uses ``get_brain_llm()``, like post moderation does. Moderation
FAILS OPEN — a moderation hiccup must never discard a successful generation.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from agency.agents.utils import parse_llm_json
from agency.services import llm_provider
from agency.services.ad_guardrails import AD_LIMITS, META_CTA_OPTIONS, SITELINK_DESC_MAX
from agency.services.brand_context import brand_prompt_block

logger = structlog.get_logger()

MODERATION_TIMEOUT_SECONDS = 30.0

#: Appended in code so the "we can't make the visual" disclosure can't quietly
#: vanish the next time the prompt is edited.
CREATIVE_BRIEF_DISCLOSURE = (
    "This is a brief — CampaignForge can't generate the image or video, and on Meta "
    "the visual matters more than the copy."
)

_G = AD_LIMITS["google"]
_M = AD_LIMITS["meta"]

GOOGLE_INSTRUCTIONS = (
    "Write a complete Google Ads Responsive Search Ad asset set for the brand below.\n\n"
    "HARD CHARACTER LIMITS — an asset over its limit is rejected by Google outright, "
    "so count characters including spaces:\n"
    f"- Headlines: exactly {_G['headlines']['max_count']}, "
    f"max {_G['headlines']['max']} chars each\n"
    f"- Descriptions: exactly {_G['descriptions']['max_count']}, "
    f"max {_G['descriptions']['max']} chars each\n"
    f"- Display paths: 2, max {_G['paths']['max']} chars each\n"
    f"- Sitelinks: 4, text max {_G['sitelinks']['max']} chars, each with 2 description "
    f"lines max {SITELINK_DESC_MAX} chars\n"
    f"- Callouts: 8, max {_G['callouts']['max']} chars each\n\n"
    "Rules that matter more than polish:\n"
    "1. EVERY headline must make complete sense alone — Google mixes them unpredictably, "
    "so never write fragments meant to be read in sequence.\n"
    f"2. All {_G['headlines']['max_count']} headlines must cover genuinely DIFFERENT "
    "territory (core value, primary keyword, a specific differentiator, an objection "
    "answered, a concrete proof point, a use case, a CTA). Paraphrases of one idea give "
    "Google nothing to optimize and are a failure.\n"
    "3. NEVER name a competitor or any other company's trademark in any asset — using a "
    "rival's trademark in ad text gets ads disapproved and can escalate to account "
    "suspension. Use generic category descriptors instead.\n"
    "4. No guaranteed outcomes, no invented statistics, no fabricated scarcity, no "
    'unsupportable superlatives ("#1", "best"). Concrete specifics convert better and '
    "can't be disapproved.\n"
    "5. Never state or imply any performance prediction (CTR, conversion rate, CPC).\n\n"
    "Also produce keyword themes grouped by intent and negative keywords to stop wasted "
    "spend. Do NOT invent search volumes or bid estimates — you have no access to real "
    "data.\n\n"
    'Return ONLY JSON, no markdown fences: {"headlines": [string], "descriptions": '
    '[string], "paths": [string], "sitelinks": [{"text": string, "desc1": string, '
    '"desc2": string}], "callouts": [string], "keyword_themes": [{"intent": string, '
    '"keywords": [string], "note": string}], "negative_keywords": [string], '
    '"structure_note": string}'
)

META_INSTRUCTIONS = (
    "Write Meta (Facebook/Instagram) ad copy for the brand below.\n\n"
    "This is NOT Google Search. Nobody is looking for this product — the copy has to "
    "stop a scroll and create the need, conversationally and natively. Literal "
    "keyword-matching copy fails here.\n\n"
    "LENGTHS — Meta accepts far more text than it SHOWS, and over-threshold copy is "
    "silently truncated for real viewers while looking fine in Ads Manager. Write to "
    "what's visible:\n"
    f"- Primary texts: 4, max {_M['primary_texts']['max']} chars each. The FIRST LINE is "
    'the entire ad — everything past this is behind "See more" and mostly unread. Never '
    "build to a punchline.\n"
    f"- Headlines: 4, target {_M['headlines']['preferred']} chars, absolute max "
    f"{_M['headlines']['max']}\n"
    f"- Link descriptions: 2, max {_M['descriptions']['max']} chars (often hidden on "
    "mobile entirely)\n\n"
    "CRITICAL POLICY — Meta's personal attributes rule is its most-violated policy and "
    "enforcement is AI-driven, proactive, and covers INDIRECT implication. Ad copy must "
    "never assert or imply that you know the reader's race, ethnicity, religion, age, "
    "sexual orientation, gender identity, disability, physical or mental health "
    "condition, financial status, criminal record, or name.\n"
    "The trap: second-person problem-agitation, the default move in SaaS copywriting, is "
    "exactly this violation.\n"
    '  VIOLATION: "Are you a broke founder drowning in support tickets?"\n'
    '  COMPLIANT: "Support tickets pile up fast at small companies."\n'
    'Describe the PRODUCT and the SITUATION, never the reader\'s traits. "You" is fine '
    'on its own ("your team ships faster") — it\'s "you" plus an assumed personal trait '
    "that violates.\n\n"
    "Also: no guaranteed outcomes, no invented statistics, no fabricated scarcity, no "
    "performance predictions.\n\n"
    "The CTA must be one of Meta's real preset buttons "
    f"({', '.join(META_CTA_OPTIONS)}) — button text is not free-form.\n\n"
    'Return ONLY JSON, no markdown fences: {"primary_texts": [string], "headlines": '
    '[string], "descriptions": [string], "cta": string, "cta_reason": string, '
    '"creative_direction": string, "audience_angle": string, '
    '"special_ad_category_note": string}\n'
    '"creative_direction" describes what the image or video should show. '
    '"special_ad_category_note" flags whether this product plausibly falls into Meta\'s '
    "Credit, Employment, Housing or Social Issues categories (which carry mandatory "
    "declaration and heavy targeting limits), or says plainly that it does not appear to."
)

SYSTEM_PROMPT = (
    "You write paid-ad copy and structure for a marketing agency's client. You never "
    "predict performance, never invent numbers, and never claim to launch or run anything."
)


class MalformedAdSetError(ValueError):
    """The model's output did not have the minimum usable shape."""


def _text_of(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks (Anthropic)
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _pick(raw: dict[str, Any], *keys: str) -> Any:
    """First present key — tolerates the prototype's camelCase if the model uses it."""
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize_google(raw: Any) -> dict[str, Any]:
    """Coerce a model reply into the Google asset shape. Never truncates copy."""
    if not isinstance(raw, dict):
        raise MalformedAdSetError("Google reply was not a JSON object")
    sitelinks = []
    for link in _pick(raw, "sitelinks") or []:
        if isinstance(link, dict) and _str(link.get("text")):
            sitelinks.append({k: _str(link.get(k)) for k in ("text", "desc1", "desc2")})
    themes = []
    for theme in _pick(raw, "keyword_themes", "keywordThemes") or []:
        if isinstance(theme, dict) and _str_list(theme.get("keywords")):
            themes.append(
                {
                    "intent": _str(theme.get("intent")) or "General",
                    "keywords": _str_list(theme.get("keywords")),
                    "note": _str(theme.get("note")),
                }
            )
    assets = {
        "headlines": _str_list(raw.get("headlines")),
        "descriptions": _str_list(raw.get("descriptions")),
        "paths": _str_list(raw.get("paths")),
        "sitelinks": sitelinks,
        "callouts": _str_list(raw.get("callouts")),
        "keyword_themes": themes,
        "negative_keywords": _str_list(_pick(raw, "negative_keywords", "negativeKeywords")),
        "structure_note": _str(_pick(raw, "structure_note", "structureNote")),
    }
    if not assets["headlines"] or not assets["descriptions"]:
        raise MalformedAdSetError("Google reply had no headlines or no descriptions")
    return assets


def normalize_meta(raw: Any) -> dict[str, Any]:
    """Coerce a model reply into the Meta asset shape. The CTA is kept verbatim
    so ``validate_ad_assets`` can flag one that is not a real preset."""
    if not isinstance(raw, dict):
        raise MalformedAdSetError("Meta reply was not a JSON object")
    direction = _str(_pick(raw, "creative_direction", "creativeDirection"))
    assets = {
        "primary_texts": _str_list(_pick(raw, "primary_texts", "primaryTexts")),
        "headlines": _str_list(raw.get("headlines")),
        "descriptions": _str_list(raw.get("descriptions")),
        "cta": _str(raw.get("cta")),
        "cta_reason": _str(_pick(raw, "cta_reason", "ctaReason")),
        "creative_direction": f"{direction}\n\n{CREATIVE_BRIEF_DISCLOSURE}" if direction else "",
        "audience_angle": _str(_pick(raw, "audience_angle", "audienceAngle")),
        "special_ad_category_note": _str(
            _pick(raw, "special_ad_category_note", "specialAdCategoryNote")
        ),
    }
    if not assets["primary_texts"] or not assets["headlines"]:
        raise MalformedAdSetError("Meta reply had no primary text or no headlines")
    return assets


def build_prompt(network: str, brand: dict[str, Any]) -> str:
    instructions = GOOGLE_INSTRUCTIONS if network == "google" else META_INSTRUCTIONS
    return f"{instructions}\n\n## Brand\n{brand_prompt_block(brand)}"


async def generate_ad_set(network: str, brand: dict[str, Any]) -> dict[str, Any]:
    """Generate and normalize one ad set. Raises ``MalformedAdSetError`` on an unusable
    reply and whatever the LLM client raises on a provider error — the router turns
    both into a 502 without charging quota."""
    if network not in ("google", "meta"):
        raise ValueError(f"Unknown network {network!r}")
    llm = llm_provider.get_ad_copy_llm()  # type: ignore[no-untyped-call]
    response = await llm.ainvoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=build_prompt(network, brand))]
    )
    parsed = parse_llm_json(_text_of(response))
    return normalize_google(parsed) if network == "google" else normalize_meta(parsed)


MODERATION_PROMPT = (
    "Review this draft {platform} copy before it's used. Flag only real problems: "
    "specific unverifiable/exaggerated claims (numbers, guarantees), fabricated scarcity, "
    'unsupportable superlatives ("#1", "best") with no real basis, negative mentions of a '
    "named competitor, profanity, or anything likely to violate {platform}'s advertising "
    "policies. Don't flag normal marketing tone or confident but ordinary claims.\n\n"
    'Ad copy:\n"""{text}"""\n\n'
    'Return ONLY JSON, no markdown fences: {{"flagged": boolean, "issues": [string]}}. '
    "Empty issues array if flagged is false."
)


def _unavailable(reason: str, network: str, **extra: Any) -> dict[str, Any]:
    logger.warning("ad_moderation_unavailable", reason=reason, network=network, **extra)
    return {"status": "unavailable", "flagged": False, "issues": []}


async def moderate_ad_copy(text: str, network: str) -> dict[str, Any]:
    """Advisory LLM check for what the code-level guardrails can't see.

    Returns ``{"status": "ok"|"unavailable", "flagged": bool, "issues": [str]}``.
    Never raises for a provider/parse failure — it FAILS OPEN with
    ``status="unavailable"`` and a ``ad_moderation_unavailable`` log line, so the
    UI can say moderation did not run instead of implying the copy passed.
    Cancellation (``CancelledError``) still propagates.
    """
    if not text.strip():
        return {"status": "ok", "flagged": False, "issues": []}
    platform = "Google Ads" if network == "google" else "Meta (Facebook/Instagram) ads"
    try:
        llm = llm_provider.get_brain_llm()  # type: ignore[no-untyped-call]
        response = await asyncio.wait_for(
            llm.ainvoke(MODERATION_PROMPT.format(platform=platform, text=text)),
            timeout=MODERATION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return _unavailable("timeout", network)
    except Exception as exc:
        return _unavailable("llm_error", network, error=str(exc))

    raw_text = _text_of(response)
    parsed = parse_llm_json(raw_text)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("flagged"), bool):
        return _unavailable("unparseable_response", network, response_head=raw_text[:200])
    issues = _str_list(parsed.get("issues"))
    flagged = bool(parsed["flagged"]) and bool(issues)
    return {"status": "ok", "flagged": flagged, "issues": issues if flagged else []}


def ad_set_title(network: str, assets: dict[str, Any]) -> str:
    if network == "google":
        return f"Google RSA · {assets['headlines'][0]}"
    return f"Meta ads · {assets['headlines'][0]}"
