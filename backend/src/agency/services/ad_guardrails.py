"""Ad copy guardrails for Create › Ads — pure, no I/O, fully unit-tested.

Ported from the Cadence prototype (``AD_LIMITS``, ``validateAdAssets``,
``findTrademarkRisks``, ``findPersonalAttributeRisks``, ``adCopyText``,
``META_CTA_OPTIONS``). Every check here is enforced in code rather than trusted
to the prompt, because the failures are expensive and invisible: an over-limit
Google asset is rejected on paste, and an over-threshold Meta asset saves fine
in Ads Manager but is silently truncated for real viewers.

Google's numbers are hard limits. Meta's are VISIBLE thresholds, far below its
hard caps (primary text ~125 visible vs 2,200 cap; headline ~27 visible on Feed
vs 255 cap) — writing to the cap is the most common Meta copy mistake.

Problems are reported, never "fixed": truncating a headline to fit would change
copy someone is about to spend money on.

Asset dicts use snake_case keys (``primary_texts``, ``keyword_themes``, ...).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, TypedDict

NETWORKS = ("google", "meta")


class _Rule(TypedDict, total=False):
    max: int
    preferred: int
    min_count: int
    max_count: int
    label: str


AD_LIMITS: dict[str, dict[str, _Rule]] = {
    "google": {
        "headlines": {"max": 30, "min_count": 3, "max_count": 15, "label": "Headline"},
        "descriptions": {"max": 90, "min_count": 2, "max_count": 4, "label": "Description"},
        "paths": {"max": 15, "max_count": 2, "label": "Display path"},
        "sitelinks": {"max": 25, "max_count": 20, "label": "Sitelink text"},
        "callouts": {"max": 25, "max_count": 10, "label": "Callout"},
    },
    "meta": {
        "primary_texts": {"max": 125, "min_count": 1, "max_count": 5, "label": "Primary text"},
        "headlines": {
            "max": 40,
            "preferred": 27,
            "min_count": 1,
            "max_count": 5,
            "label": "Headline",
        },
        "descriptions": {"max": 30, "max_count": 2, "label": "Link description"},
    },
}

#: Sitelink description lines (Google): 35 chars each.
SITELINK_DESC_MAX = 35

#: The only 7 real Meta CTA buttons. Button text is a preset, not free-form, so
#: anything else from the model is a concrete, checkable error.
META_CTA_OPTIONS: tuple[str, ...] = (
    "Learn More",
    "Sign Up",
    "Get Started",
    "Try It Free",
    "Download",
    "Subscribe",
    "Contact Us",
)

#: Meta's protected-attribute vocabulary, from its personal attributes policy.
#: Used only by find_personal_attribute_risks — never for targeting.
PROTECTED_ATTRIBUTE_TERMS: tuple[str, ...] = (
    "race", "ethnicity", "ethnic", "religion", "religious", "muslim", "christian", "jewish",
    "hindu",
    "age", "aged", "elderly", "senior", "middle-aged", "millennial", "boomer", "gen z",
    "gay", "lesbian", "queer", "lgbt", "sexual orientation", "transgender", "gender identity",
    "disability", "disabled", "adhd", "autistic", "autism", "depression", "depressed", "anxiety",
    "anxious", "mental health", "illness", "diagnosed", "diabetic", "obese", "overweight",
    "broke", "bankrupt", "in debt", "debt", "unemployed", "jobless", "low income", "poor",
    "struggling financially",
    "divorced", "single mom", "single dad", "immigrant", "criminal record", "felon",
)  # fmt: skip

_TERM_PATTERNS = [
    (t, re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)) for t in PROTECTED_ATTRIBUTE_TERMS
]
_SECOND_PERSON = re.compile(r"\b(you|your|you're|youre|u r)\b", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _strings(values: Any) -> list[str]:
    return [v for v in values if isinstance(v, str) and v] if isinstance(values, list) else []


def ad_copy_text(network: str, assets: dict[str, Any] | None) -> str:
    """The fields that count as real ad copy, joined.

    Shared by the trademark check, the personal-attributes check and moderation
    so they can never drift apart. Deliberately EXCLUDES ``keyword_themes``:
    that field is supposed to contain competitor names (bidding on a rival's
    keyword is allowed), so scanning it as copy would be a false positive.
    """
    if not isinstance(assets, dict):
        return ""
    if network == "google":
        parts = [
            *_strings(assets.get("headlines")),
            *_strings(assets.get("descriptions")),
            *_strings(assets.get("callouts")),
        ]
        for link in assets.get("sitelinks") or []:
            if isinstance(link, dict):
                parts.extend(str(link[k]) for k in ("text", "desc1", "desc2") if link.get(k))
        return " \n ".join(parts)
    return "\n".join(
        [
            *_strings(assets.get("primary_texts")),
            *_strings(assets.get("headlines")),
            *_strings(assets.get("descriptions")),
        ]
    )


def _text_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("text") or "")
    return ""


def validate_ad_assets(network: str, assets: dict[str, Any] | None) -> list[str]:
    """Concrete, human-readable problems against the real platform limits. Empty = clean."""
    spec = AD_LIMITS.get(network)
    if not spec or not isinstance(assets, dict):
        return []
    google = network == "google"
    problems: list[str] = []

    for field, rule in spec.items():
        values = assets.get(field)
        if not isinstance(values, list):
            continue
        label = rule["label"]
        n = len(values)
        min_count = rule.get("min_count")
        max_count = rule.get("max_count")
        if min_count and n < min_count:
            who = "Google requires" if google else "Meta needs"
            plural = "" if n == 1 else "s"
            problems.append(f"Only {n} {label.lower()}{plural} — {who} at least {min_count}.")
        if max_count and n > max_count:
            problems.append(f"{n} {label.lower()}s — the maximum is {max_count}.")
        limit = rule["max"]
        preferred = rule.get("preferred")
        for i, value in enumerate(values):
            length = len(_text_of(value))
            if length > limit:
                why = (
                    f"over Google's {limit} limit, it will be rejected"
                    if google
                    else f"past Meta's ~{limit} visible threshold, it will be truncated"
                )
                problems.append(f"{label} {i + 1} is {length} chars — {why}.")
            elif preferred and length > preferred:
                # Meta-only soft warning: valid, but cut off on the tightest placement.
                problems.append(
                    f"{label} {i + 1} is {length} chars — fine on Instagram, "
                    f"but Facebook Feed shows only ~{preferred}."
                )

    if google:
        for i, link in enumerate(assets.get("sitelinks") or []):
            if not isinstance(link, dict):
                continue
            for key, line in (("desc1", 1), ("desc2", 2)):
                length = len(str(link.get(key) or ""))
                if length > SITELINK_DESC_MAX:
                    problems.append(
                        f"Sitelink {i + 1} description line {line} is {length} chars — "
                        f"over Google's {SITELINK_DESC_MAX} limit, it will be rejected."
                    )

    # CTA is a preset button on Meta, not free text.
    cta = assets.get("cta")
    if network == "meta" and cta and cta not in META_CTA_OPTIONS:
        problems.append(
            f"CTA \"{cta}\" isn't one of Meta's real preset buttons "
            f"({', '.join(META_CTA_OPTIONS)}) — button text can't be freeform."
        )
    return problems


def find_trademark_risks(
    text: str | None, known_competitor_names: Iterable[Any] | None
) -> list[str]:
    """Competitor names (lower-cased, once each) that appear in ad text.

    Google allows bidding on a rival's trademark as a KEYWORD but not using it
    in AD TEXT. Word-boundary matched so a rival called "Later" does not fire
    on "laterally".
    """
    if not text:
        return []
    seen: list[str] = []
    for raw in known_competitor_names or []:
        name = (raw if isinstance(raw, str) else "").strip().lower()
        if len(name) < 2 or name in seen:
            continue
        if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
            seen.append(name)
    return seen


def find_personal_attribute_risks(text: str | None) -> list[dict[str, str]]:
    """Sentences that pair second-person address with a protected trait.

    HEURISTIC, NOT A COMPLIANCE CHECK. Meta's reviewers judge how copy reads to
    a reasonable viewer; no pattern match approximates that. This will miss
    things and sometimes over-flag. Surface it as "worth a second look", never
    as "this ad is compliant". "You" alone is fine ("your team ships faster");
    the violation is "you" PLUS an assumed trait, so both must be in one sentence.
    """
    if not text:
        return []
    flagged: list[dict[str, str]] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        if not sentence or not _SECOND_PERSON.search(sentence):
            continue
        for term, pattern in _TERM_PATTERNS:
            if pattern.search(sentence):
                flagged.append({"sentence": sentence.strip(), "term": term})
                break
    return flagged


def collect_competitor_names(payloads: Iterable[Any]) -> list[str]:
    """Every competitor named in the client's comparison pages and niche scans.

    Tolerates both snake_case and the prototype's camelCase keys, since those
    payloads are written by another screen. Order-preserving, de-duplicated
    case-insensitively.
    """
    names: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip() and value.strip().lower() not in seen:
            seen.add(value.strip().lower())
            names.append(value.strip())

    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in ("competitor_name", "competitorName"):
            add(payload.get(key))
        for key in ("competitor_names", "competitorNames", "competitors"):
            values = payload.get(key)
            if isinstance(values, list):
                for v in values:
                    add(v.get("name") if isinstance(v, dict) else v)
    return names
