"""Screens generated media. Runs at GENERATION time, never on the approve path.

STAGE 1 CONTRACT — signatures and semantics are frozen; bodies are Phase 4.
Fill these in place. Do not edit `moderation.py`, `content_approval.py`,
`tables.py` or `config.py` — another agent owns those. Report anything that
looks like it needs a shared-file change.

The latency argument: a vision call on ``POST /content/{id}/approve`` roughly
doubles that request for every post, including the ones with no media at all.
Screening when the image is created instead costs nothing perceptible, because
the user is already waiting on the provider.

The gate still lives before ``approved`` — it is just a row lookup there
(:func:`verdict_missing`), not a model call. So product rule 3 holds at no
approval-latency cost.

Escalation ladder, cheapest first:

1. the provider's own safety signal (fal returns ``has_nsfw_concepts``, free and
   synchronous with the generation);
2. a **brain**-tier vision call, only when that trips or the image carries
   rendered text — which is where the real risk is for this product: a wrong
   price, an unapproved claim, a competitor's mark. Same risk class
   ``ad_guardrails.py`` already handles for ad copy.

Fail open *visibly*, exactly as the text path does: ``status="unavailable"``
plus a ``media_moderation_unavailable`` log. Never silently.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Final

import structlog

from agency.agents.utils import parse_llm_json
from agency.services.tracing import trace_config

logger = structlog.get_logger()

#: Severities accepted from the model, mirroring ``moderation._SEVERITIES``.
_SEVERITIES: Final = ("low", "medium", "high")

#: Upper bound on the vision call. Generation is already slow, but a hung
#: gateway must not hold a Fly worker past the request timeout; past this the
#: check fails open like any other LLM failure.
VISION_TIMEOUT_SECONDS: Final = 45.0

#: Keys the generator may hand us for the provider's own safety signal. fal
#: returns ``has_nsfw_concepts`` as a list, one entry per image in the batch.
_NSFW_FLAG_KEYS: Final = ("has_nsfw_concepts", "nsfw_concepts", "nsfw")

#: Keys that let a caller state outright that the image carries rendered text,
#: for when a provider or a later OCR step knows better than the heuristic.
_TEXT_FLAG_KEYS: Final = ("has_text", "text_detected", "rendered_text")

#: Prompt-side heuristic for "this image was asked to render words". Costs one
#: regex over a string we already have: no pixels fetched, no OCR dependency,
#: no extra model call. Over-triggering only buys an extra vision call; under-
#: triggering is the real risk, so the vocabulary is deliberately generous.
_TEXT_INTENT_PATTERN: Final = re.compile(
    r"""
    (?: \btext\b | \bwords?\b | \bwording\b | \bcaption\b | \bsubtitle\b
      | \bheadline\b | \bheader\b | \bslogan\b | \btagline\b | \blabel\b
      | \btypograph | \blettering\b | \bfont\b | \btitle\b | \bquote\b
      | \blogo\b | \bwordmark\b | \bbadge\b | \bsign\b | \bsignage\b
      | \bbanner\b | \bposter\b | \bbillboard\b | \binfographic\b
      | \bchart\b | \bgraph\b | \btable\b | \bprice\b | \bpricing\b
      | \bdiscount\b | \b\d+\s*%(?:\s*off)? | [$€£]\s*\d
      | \bcall\s*to\s*action\b | \bcta\b | \bthat\s+says\b | \breads\b
      | "[^"]+" | '[^']{3,}' )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_VISION_PROMPT = """You are the pre-approval moderator for a social media agency. A human is \
about to approve the attached generated image for publishing to a real, live client account. \
Flag only concrete problems a careful editor would stop the post for. Do not flag matters of \
taste or art direction.

Check, in this order:
1. Any text rendered IN the image: wrong or unsupported prices and discounts, unverifiable \
claims or guaranteed outcomes, fabricated scarcity, misspellings in brand or product names, and \
text that is garbled or cut off.
2. Third-party trademarks, logos, wordmarks or recognisable brand assets that are not this \
brand's.
3. Identifiable real people, and content implying a personal attribute (health, religion, \
sexuality, race, age) about anyone depicted.
4. Sexual, violent, hateful or otherwise unsafe content that would breach platform policy.
5. Anything that contradicts the brand context below, including its excluded vocabulary \
appearing as rendered text.

## Brand context
{brand}

## Why this image was escalated
{reason}

Return ONLY a JSON object:
{{"issues": [{{"severity": "low|medium|high", "message": "one sentence, specific"}}]}}
Return {{"issues": []}} if nothing should stop this image."""


@dataclass
class MediaModerationResult:
    """``passed`` | ``flagged`` | ``unavailable``, with the issues found."""

    status: str
    issues: list[dict[str, str]] = field(default_factory=list)
    #: True when a vision call actually ran. Unlike the text path's
    #: ``ModerationResult.llm_checked``, a clean rung 1 **is** a screen, so
    #: ``passed`` with ``vision_checked=False`` is a real verdict — media has
    #: two checks where text has one.
    vision_checked: bool = False
    #: Which rung produced this verdict, so a caller can tell "we deliberately
    #: did not look" (``provider_only``) from "the check could not run"
    #: (``timeout``, ``llm_error``, ``unparseable_response``,
    #: ``video_unsupported``, ``missing_image_url``). Lives on the row, not
    #: only in the log, because the UI must not warn on a deliberate skip.
    reason: str = ""

    def as_metadata(self) -> dict[str, Any]:
        """Shape written to ``media_asset.moderation``.

        Must be non-empty for any screened asset: ``{}`` is what
        :func:`verdict_missing` reads as "not yet screened", so an empty dict
        here would make a screened asset unapprovable.
        """
        return {
            "status": self.status,
            "issues": self.issues,
            "vision_checked": self.vision_checked,
            "reason": self.reason,
        }


def verdict_missing(moderation: dict[str, Any] | None) -> bool:
    """True when this asset has not been screened.

    What the approve path calls, per asset attached to the piece. Cheap by
    design — a dict check, no query, no model.
    """
    return not (moderation or {}).get("status")


async def moderate_media(
    *,
    kind: str,
    image_url: str,
    provider_flags: dict[str, Any] | None = None,
    brand_context: dict[str, Any] | None = None,
) -> MediaModerationResult:
    """Screen one generated asset. Never raises.

    ``provider_flags`` carries what the generator already learned for free
    (fal's ``has_nsfw_concepts``); pass it rather than re-deriving it.

    Video (``kind == "video"``) has no cheap provider signal and no frame
    sampling yet: return ``unavailable`` with the log, do not pretend it passed.
    An honest "not screened" is what the approve gate is for.
    """
    if kind == "video":
        # No provider safety signal, no frame sampling. Saying "passed" here
        # would be a capability claim (product rule 1) about a check that never
        # ran; the approve gate exists precisely to carry an honest unknown.
        logger.warning(
            "media_moderation_unavailable", reason="video_unsupported", kind=kind
        )
        return MediaModerationResult(status="unavailable", reason="video_unsupported")

    if not image_url:
        logger.warning("media_moderation_unavailable", reason="missing_image_url", kind=kind)
        return MediaModerationResult(status="unavailable", reason="missing_image_url")

    flags = provider_flags or {}
    nsfw_issue = provider_nsfw_issue(flags)
    carries_text = image_carries_text(flags)

    if nsfw_issue is None and not carries_text:
        # Rung 1 only, and that is a verdict: the provider screened the image
        # and nothing suggests rendered text, so no vision call is made. This
        # is the whole latency argument (§1E), and it is the modal case — the
        # row records *which* rung passed it (``reason``) so nothing has to
        # treat a deliberate skip as an outage.
        return MediaModerationResult(status="passed", reason="provider_only")

    escalation = _escalation_reason(nsfw_issue is not None, carries_text)
    vision_found, vision_reason = await _vision_issues(image_url, brand_context, escalation)
    vision_checked = vision_found is not None

    issues: list[dict[str, str]] = []
    if nsfw_issue is not None:
        issues.append(nsfw_issue)
    issues.extend(vision_found or [])

    if issues:
        # A provider trip is a finding on its own, so this still flags when the
        # escalation could not run — ``reason`` says which.
        return MediaModerationResult(
            status="flagged", issues=issues, vision_checked=vision_checked, reason=vision_reason
        )
    if vision_checked:
        return MediaModerationResult(status="passed", vision_checked=True, reason=vision_reason)
    # Escalated and the model could not answer: genuinely unavailable.
    return MediaModerationResult(status="unavailable", reason=vision_reason)


def provider_nsfw_issue(provider_flags: dict[str, Any] | None) -> dict[str, str] | None:
    """The provider's own safety signal, normalised. ``None`` when clean or absent.

    fal returns ``has_nsfw_concepts`` as a list (one entry per image in the
    batch); a bare bool and a list of dicts/strings are accepted too, so a
    second provider needs no change here.
    """
    for key in _NSFW_FLAG_KEYS:
        if key not in (provider_flags or {}):
            continue
        raw = (provider_flags or {})[key]
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        if any(bool(v) for v in values):
            return {
                "severity": "high",
                "message": (
                    "The image generator flagged this image as possibly unsafe "
                    f"({key}). Review it before approving."
                ),
            }
    return None


def image_carries_text(provider_flags: dict[str, Any] | None) -> bool:
    """Whether this image should be assumed to render words.

    An explicit flag from the caller wins. Otherwise this is a **prompt-side**
    heuristic: the resolved prompt is already in hand (§1F assembles it in
    code), so matching it costs one regex — no bytes fetched, no OCR
    dependency, no extra model call. It cannot see text the model drew
    unbidden; it is the cheap half of the ladder, and the vision rung is what
    actually reads the pixels.
    """
    flags = provider_flags or {}
    for key in _TEXT_FLAG_KEYS:
        if key in flags:
            return bool(flags[key])
    prompt = flags.get("prompt") or ""
    if not isinstance(prompt, str):
        return False
    return _TEXT_INTENT_PATTERN.search(prompt) is not None


def _escalation_reason(nsfw: bool, carries_text: bool) -> str:
    reasons = []
    if nsfw:
        reasons.append("the generator's own safety signal flagged it")
    if carries_text:
        reasons.append("the image is expected to contain rendered text")
    return "; ".join(reasons) or "unspecified"


def _format_brand(brand_context: dict[str, Any] | None) -> str:
    """Mirrors ``moderation._format_brand``, minus the tenant lookup ids."""
    if not brand_context:
        return "No brand profile on file."
    lines = []
    for key, value in brand_context.items():
        if key in ("org_id", "client_id") or value in (None, "", [], {}):
            continue
        rendered = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
        lines.append(f"- {key}: {rendered}")
    return "\n".join(lines) or "No brand profile on file."


def _normalise_issues(raw: Any) -> list[dict[str, str]] | None:
    """Validate the model's ``issues`` list. ``None`` means the response was unusable."""
    if not isinstance(raw, dict) or not isinstance(raw.get("issues"), list):
        return None
    issues: list[dict[str, str]] = []
    for item in raw["issues"]:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or "").strip()
        if not message:
            continue
        severity = str(item.get("severity") or "").lower()
        issues.append(
            {"severity": severity if severity in _SEVERITIES else "medium", "message": message}
        )
    return issues


async def _vision_issues(
    image_url: str, brand_context: dict[str, Any] | None, reason: str
) -> tuple[list[dict[str, str]] | None, str]:
    """Rung 2: one **brain**-tier vision call.

    Returns ``(issues, "vision")`` when the model answered, or
    ``(None, <failure reason>)`` — logged — on any failure. The reason is
    returned rather than only logged so it can land on the row.
    """
    # Imported through the module so tests can swap the tier getter.
    from agency.services import llm_provider

    try:
        llm = llm_provider.get_brain_llm()  # type: ignore[no-untyped-call]
        prompt = _VISION_PROMPT.format(brand=_format_brand(brand_context), reason=reason)
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }
        response = await asyncio.wait_for(
            llm.ainvoke(
                [message],
                config=trace_config(
                    "media-moderation", org_id=(brand_context or {}).get("org_id")
                ),
            ),
            timeout=VISION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("media_moderation_unavailable", reason="timeout")
        return None, "timeout"
    except Exception as exc:
        logger.warning("media_moderation_unavailable", reason="llm_error", error=str(exc))
        return None, "llm_error"

    raw = response.content if hasattr(response, "content") else str(response)
    text = raw if isinstance(raw, str) else json.dumps(raw)
    issues = _normalise_issues(parse_llm_json(text))
    if issues is None:
        logger.warning(
            "media_moderation_unavailable",
            reason="unparseable_response",
            response_head=text[:200],
        )
        return None, "unparseable_response"
    return issues, "vision"
