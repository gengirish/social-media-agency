"""Amplify — pure helpers for the repurposing engine.

One source (an existing content piece or pasted text) becomes up to
:data:`MAX_ATOMS` platform-native drafts ("atoms"), each committed to a
different angle from a closed taxonomy. The taxonomy is closed on purpose: the
#1 reason repurposing tools get abandoned is that every output is the same
sentence reworded, and a fixed enum is what lets the prompt say "you already
used X" and lets code check it.

Everything here is pure (no DB, no LLM) so the guards that matter are unit
tested in isolation. The agent is ``agents/amplify.py``; the endpoints are
``routers/amplify.py``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, cast

from agency.agents.content_writer import PLATFORM_GUIDELINES

#: Closed angle taxonomy. Max one atom per angle in a pack.
REPURPOSE_ANGLES: tuple[str, ...] = (
    "hook",
    "how-to",
    "contrarian",
    "story",
    "data-point",
    "question",
    "behind-the-scenes",
    "listicle",
)

#: 1 pack = 1 generation, and never more than this many atoms in it.
MAX_ATOMS = len(REPURPOSE_ANGLES)

#: Hard per-platform character caps. Derived from the content agent's
#: ``PLATFORM_GUIDELINES`` rather than restated, so the two cannot drift.
PLATFORM_CHAR_LIMITS: dict[str, int] = {
    platform: cast(int, spec["max_length"]) for platform, spec in PLATFORM_GUIDELINES.items()
}

#: Spelled out for the prompt rather than trusting the model's read of a name.
ANGLE_DEFINITIONS: dict[str, str] = {
    "hook": "one arresting opening line or claim, then just enough to earn it",
    "how-to": "a concrete step or method pulled from the source, written so someone can do it",
    "contrarian": "a respectful pushback on an assumption the source touches",
    "story": "one specific small moment from the source, told narratively",
    "data-point": "one real number or fact that is IN the source, made to stand alone",
    "question": "a genuine open question the source raises, inviting replies",
    "behind-the-scenes": "the process or decision behind what the source describes",
    "listicle": "a short numbered breakdown of a few points from the source",
}

#: Per-platform format guidance for the prompt.
PLATFORM_FORMATS: dict[str, str] = {
    "twitter": "under 280 characters including hashtags, punchy, at most 2 hashtags",
    "linkedin": (
        "120-250 words, first-person voice, a standalone hook as the very first line "
        "(LinkedIn truncates after it), short paragraphs separated by blank lines"
    ),
    "instagram": "a 2-4 sentence caption with line breaks; hashtags go in the hashtags field",
    "facebook": "2-4 conversational sentences, community tone, no hashtag stuffing",
    "tiktok": "a short on-screen caption (under 150 characters) with a hook in the first words",
}

DEFAULT_DUPLICATE_THRESHOLD = 0.6

_TOKEN = re.compile(r"[a-z0-9']+")
# Very common words carry no angle information and inflate overlap between
# any two English posts; drop them before comparing.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "has",
        "have", "i", "in", "is", "it", "its", "of", "on", "or", "our", "so", "that",
        "the", "their", "this", "to", "was", "we", "were", "what", "when", "with",
        "you", "your",
    }
)  # fmt: skip


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS}


def jaccard(a: str, b: str) -> float:
    """Token-set overlap in [0, 1]. Two empty texts are 0, not 1."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def is_angle_duplicate(
    candidate: str,
    recent_bodies: Iterable[str],
    threshold: float = DEFAULT_DUPLICATE_THRESHOLD,
) -> bool:
    """True when ``candidate`` overlaps any recent body at or above ``threshold``.

    Warn-don't-block: callers surface this as ``duplicate_warning`` and let the
    human decide. It is a cheap reworded-duplicate catch, not semantic similarity.
    """
    return any(jaccard(candidate, body) >= threshold for body in recent_bodies if body)


def drip_schedule(n: int, start: datetime, per_week: int = 5) -> list[datetime]:
    """``n`` publish slots after ``start``, one per day at most, 09:00 local to ``start``.

    ``per_week`` becomes a day spacing of ``round(7 / per_week)``, floored at 1,
    so no two atoms share a day and a zero/negative cadence cannot collapse
    them onto one. The first slot is the day AFTER ``start``, never the same
    day. Only a suggestion — drafts are never scheduled at generation time.
    """
    if n <= 0:
        return []
    spacing = max(1, round(7 / max(1, per_week)))
    base = start.replace(hour=9, minute=0, second=0, microsecond=0)
    return [base + timedelta(days=spacing * (i + 1)) for i in range(n)]


def plan_atoms(
    platforms: Sequence[str],
    max_atoms: int,
    used_angles: Iterable[str] = (),
) -> list[dict[str, str]]:
    """Decide the ``(platform, angle)`` pairs a pack will ask for.

    Angles are assigned here, not by the model, so the one-atom-per-angle rule
    holds by construction. Angles already used for this source by earlier packs
    go last, so a second pack from the same source explores new ground first.
    Platforms rotate so every requested platform gets atoms.
    """
    targets = [p for p in dict.fromkeys(platforms) if p in PLATFORM_CHAR_LIMITS]
    if not targets:
        return []
    used = set(used_angles)
    ordered = [a for a in REPURPOSE_ANGLES if a not in used] + [
        a for a in REPURPOSE_ANGLES if a in used
    ]
    count = max(0, min(max_atoms, MAX_ATOMS))
    return [
        {"platform": targets[i % len(targets)], "angle": angle}
        for i, angle in enumerate(ordered[:count])
    ]


def rendered_length(body: str, hashtags: Sequence[str]) -> int:
    """Length of the text a publisher actually sends.

    ``services/publishing.py`` appends a blank line and ``#tag #tag`` to the
    body, so a body that fits on its own can still blow the platform cap once tagged.
    """
    if not hashtags:
        return len(body)
    return len(body) + 2 + len(" ".join(f"#{t}" for t in hashtags))


@dataclass
class AtomValidation:
    kept: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


def _clean_hashtags(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for tag in raw:
        if not isinstance(tag, str):
            continue
        cleaned = tag.strip().lstrip("#").strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out[:10]


def validate_atoms(
    raw: Any,
    platforms: Sequence[str],
    max_atoms: int = MAX_ATOMS,
) -> AtomValidation:
    """Keep only well-formed atoms; say why each other one was dropped.

    Drops: non-objects, a platform not requested, an angle outside the enum or
    already used earlier in the list, an empty body, a body whose published
    length (hashtags included) is over the platform's character limit. Stops at
    ``max_atoms`` (never more than :data:`MAX_ATOMS`).
    """
    result = AtomValidation()
    allowed = set(platforms)
    cap = max(0, min(max_atoms, MAX_ATOMS))
    seen_angles: set[str] = set()

    for i, atom in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(atom, dict):
            result.dropped.append(f"#{i}: not an object")
            continue
        platform = str(atom.get("platform") or "").strip().lower()
        angle = str(atom.get("angle") or "").strip().lower()
        body = str(atom.get("body") or "").strip()

        if platform not in allowed or platform not in PLATFORM_CHAR_LIMITS:
            result.dropped.append(f"#{i}: platform {platform!r} not requested")
            continue
        if angle not in REPURPOSE_ANGLES:
            result.dropped.append(f"#{i}: unknown angle {angle!r}")
            continue
        if angle in seen_angles:
            result.dropped.append(f"#{i}: duplicate angle {angle!r}")
            continue
        if not body:
            result.dropped.append(f"#{i}: empty body")
            continue
        hashtags = _clean_hashtags(atom.get("hashtags"))
        limit = PLATFORM_CHAR_LIMITS[platform]
        length = rendered_length(body, hashtags)
        if length > limit:
            result.dropped.append(f"#{i}: {length} chars over {platform} limit {limit}")
            continue
        if len(result.kept) >= cap:
            result.dropped.append(f"#{i}: over the {cap}-atom cap")
            continue

        seen_angles.add(angle)
        result.kept.append(
            {
                "platform": platform,
                "angle": angle,
                "title": str(atom.get("title") or "").strip()[:500],
                "body": body,
                "hashtags": hashtags,
            }
        )
    return result
