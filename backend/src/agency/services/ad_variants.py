"""Normalisation of the Ad Copy agent's output into per-platform structures.

The agent is prompted for one generic shape (``headlines``, ``descriptions``,
``primary_text``, ``cta``), but each network renders a different set of fields:
Google shows a pool of headlines and descriptions, Meta shows primary text plus a
single headline and description, LinkedIn shows intro text plus a headline and
description. Storing the generic shape and hoping the UI can read it is what
produced ``["AI Gig Approvals in Days", ...]`` in the body of a Google ad and an
empty ``[]`` for every Meta and LinkedIn ad: the body was
``json.dumps(ad["headlines"])``, and for the networks whose copy the model put in
``primary_text`` there were no headlines to dump.

So this module does the mapping in code, once, with the field names each network
actually has. ``normalize`` is deliberately tolerant — it accepts the generic
shape *and* already-per-platform keys, because the prompt asks for the former but
models volunteer the latter — and it reports emptiness rather than inventing a
placeholder, so an unusable variant can be stored as failed instead of offered
for approval (see ``services/content_approval.py``).

Character limits are the networks' own. They are recorded, not enforced: the copy
is a draft for a human to edit, and silently truncating a headline would be the
kind of invented output the product rules forbid. ``services/ad_guardrails.py``
is what flags over-limit copy on the paths that build real ad sets.
"""

from __future__ import annotations

from typing import Any, Final, Literal, TypedDict

__all__ = [
    "AD_PLATFORMS",
    "PLATFORM_LIMITS",
    "NormalizedAd",
    "normalize",
    "render_body",
    "platform_of",
]

AdPlatform = Literal["google", "meta", "linkedin"]

AD_PLATFORMS: Final[tuple[str, ...]] = ("google", "meta", "linkedin")

# Per-field character limits, by platform. Google's are hard caps the network
# rejects; Meta's and LinkedIn's are the thresholds past which the field is
# visually truncated in the feed.
PLATFORM_LIMITS: Final[dict[str, dict[str, int]]] = {
    "google": {"headline": 30, "description": 90},
    "meta": {"primary_text": 125, "headline": 40, "description": 30},
    "linkedin": {"intro_text": 150, "headline": 70, "description": 100},
}

# How many of each repeated field a network takes.
_GOOGLE_MAX_HEADLINES: Final = 3
_GOOGLE_MAX_DESCRIPTIONS: Final = 2


class NormalizedAd(TypedDict):
    """A variant in the shape its platform renders.

    ``fields`` holds only the keys that platform has, so the UI can render it
    without knowing which network it came from. ``missing`` names the fields that
    came back empty, and ``is_empty`` is true when nothing usable survived —
    that variant must not become an approvable draft.
    """

    platform: str
    variant: int
    angle: str
    cta: str
    target_keyword: str
    notes: str
    fields: dict[str, Any]
    limits: dict[str, int]
    missing: list[str]
    is_empty: bool


def platform_of(raw: Any) -> str:
    """The platform a raw variant claims, normalised, defaulting to Google.

    Google is the default because it is the only network whose shape the generic
    prompt maps onto unchanged, so a variant that forgot to say what it is at
    least renders rather than vanishing.
    """
    if not isinstance(raw, dict):
        return "google"
    value = str(raw.get("platform") or "").strip().lower()
    # Models write "facebook"/"instagram" for Meta and "google_ads"/"google ads"
    # for Google often enough that mapping them beats dropping the variant.
    if value in {"facebook", "fb", "instagram", "ig", "meta_ads"}:
        return "meta"
    if value.startswith("google"):
        return "google"
    if value.startswith("linkedin"):
        return "linkedin"
    return value if value in AD_PLATFORMS else "google"


def _clean_str(value: Any) -> str:
    """A trimmed string, or "" for anything that is not usable text.

    Guards against the model returning ``None``, a number, or a nested list where
    a string belongs — all of which would otherwise reach the UI as "None" or
    "[...]", which is the class of bug this module exists to stop.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _clean_list(value: Any) -> list[str]:
    """A list of non-empty strings from a list, or from a single string.

    A bare string is wrapped rather than rejected: asked for ``headlines`` the
    model sometimes returns one headline unwrapped.
    """
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _clean_str(item)
        if text:
            out.append(text)
    return out


def _first(*candidates: Any) -> str:
    """The first candidate that yields usable text.

    Each candidate may be a string or a list — ``headlines`` is checked
    alongside ``headline`` throughout, since which one the model emits varies.
    """
    for candidate in candidates:
        text = _clean_str(candidate)
        if text:
            return text
        items = _clean_list(candidate)
        if items:
            return items[0]
    return ""


def normalize(raw: Any, *, index: int = 1) -> NormalizedAd:
    """One raw variant from the agent, mapped to its platform's fields.

    ``index`` is the fallback variant number, used when the model omits or
    repeats ``variant`` — the number is only a label, but two variants sharing
    one makes the list read as duplicated.
    """
    if not isinstance(raw, dict):
        raw = {}

    platform = platform_of(raw)
    headlines = _clean_list(raw.get("headlines") or raw.get("headline"))
    descriptions = _clean_list(raw.get("descriptions") or raw.get("description"))
    body_text = _first(
        raw.get("primary_text"),
        raw.get("intro_text"),
        raw.get("body"),
        raw.get("text"),
    )

    fields: dict[str, Any] = {}
    required: list[str]

    if platform == "google":
        fields["headlines"] = headlines[:_GOOGLE_MAX_HEADLINES]
        fields["descriptions"] = descriptions[:_GOOGLE_MAX_DESCRIPTIONS]
        # Google has no long-text field, so primary_text is the model putting the
        # description somewhere else. Keep it rather than drop the only copy.
        if not fields["descriptions"] and body_text:
            fields["descriptions"] = [body_text]
        required = ["headlines", "descriptions"]
    elif platform == "meta":
        fields["primary_text"] = body_text
        fields["headline"] = headlines[0] if headlines else ""
        fields["description"] = descriptions[0] if descriptions else ""
        # With no long-text field of its own, a second headline is better shown as
        # the primary text than discarded.
        if not fields["primary_text"] and len(headlines) > 1:
            fields["primary_text"] = headlines[1]
        required = ["primary_text", "headline"]
    else:  # linkedin
        fields["intro_text"] = body_text
        fields["headline"] = headlines[0] if headlines else ""
        fields["description"] = descriptions[0] if descriptions else ""
        if not fields["intro_text"] and len(headlines) > 1:
            fields["intro_text"] = headlines[1]
        required = ["intro_text", "headline"]

    missing = [name for name in required if not fields.get(name)]
    # Emptiness is judged on every field, not just the required ones: a Meta
    # variant with only a description is still something a human can edit, while
    # one with nothing at all is noise that must not reach the approval queue.
    is_empty = not any(fields.get(name) for name in fields)

    try:
        variant = int(raw.get("variant") or index)
    except (TypeError, ValueError):
        variant = index

    return NormalizedAd(
        platform=platform,
        variant=variant,
        angle=_clean_str(raw.get("angle")) or "general",
        cta=_clean_str(raw.get("cta")),
        target_keyword=_clean_str(raw.get("target_keyword")),
        notes=_clean_str(raw.get("notes")),
        fields=fields,
        limits=PLATFORM_LIMITS[platform],
        missing=missing,
        is_empty=is_empty,
    )


# The order fields are read out in, per platform, when flattening to text.
_BODY_ORDER: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "google": (("headlines", "Headlines"), ("descriptions", "Descriptions")),
    "meta": (
        ("primary_text", "Primary text"),
        ("headline", "Headline"),
        ("description", "Description"),
    ),
    "linkedin": (
        ("intro_text", "Intro text"),
        ("headline", "Headline"),
        ("description", "Description"),
    ),
}


def render_body(ad: NormalizedAd) -> str:
    """The variant as labelled plain text, for ``content_piece.body``.

    The structured copy lives in ``metadata.ad`` and is what the UI renders. This
    is the same content flattened, because ``body`` is what every generic path
    already reads — list views, search, CSV export, the moderation check — and a
    column holding ``["…", "…"]`` is what CF-03 was.
    """
    lines: list[str] = []
    for key, label in _BODY_ORDER[ad["platform"]]:
        value = ad["fields"].get(key)
        if isinstance(value, list):
            for item in value:
                lines.append(f"{label[:-1] if label.endswith('s') else label}: {item}")
        elif value:
            lines.append(f"{label}: {value}")
    if ad["cta"]:
        lines.append(f"CTA: {ad['cta']}")
    return "\n".join(lines)
