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

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MediaModerationResult:
    """``passed`` | ``flagged`` | ``unavailable``, with the issues found."""

    status: str
    issues: list[dict[str, str]] = field(default_factory=list)
    #: True when a vision call actually ran. ``passed`` without it is
    #: ``unavailable`` — the same distinction ``ModerationResult.llm_checked``
    #: draws for text.
    vision_checked: bool = False

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
    raise NotImplementedError("Phase 4")
