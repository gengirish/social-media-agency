"""Create › Content: shape validation, scan memory and repurpose-source text.

Pure functions (no I/O) so the rules the model is never trusted to obey are
enforced — and unit-tested — in code:

* every generation is checked field by field before anything is saved; a
  malformed reply raises :class:`MalformedGenerationError`, which the router turns
  into a 502 with no quota charged and no partial asset written;
* a blog post may not re-target a keyword this client already has a post for
  (Cadence's ``usedKeywords`` memory, enforced here rather than only asked for);
* a niche scan's ``usedBy`` may only name competitors the human typed — the
  model cannot introduce a third party nobody asked about.

Payloads keep Cadence's camelCase field names so the card components map 1:1.
"""

from __future__ import annotations

from typing import Any

#: Kinds this screen produces.
CONTENT_KINDS = ("blog_post", "comparison_page", "niche_scan", "video_script")

#: Kinds Amplify accepts as a source (Cadence's collectRepurposeSources).
REPURPOSABLE_ASSET_KINDS = (
    "blog_post",
    "comparison_page",
    "niche_scan",
    "video_script",
    "launch_kit",
)

MIN_SCAN_COMPETITORS = 2
MAX_SCAN_COMPETITORS = 5
MAX_NAME_CHARS = 80
SATURATIONS = ("high", "medium", "low")
MIN_BLOG_BODY_CHARS = 200


class MalformedGenerationError(ValueError):
    """The model's reply did not have the promised shape."""


# ---------------------------------------------------------------------------
# field helpers
# ---------------------------------------------------------------------------
def _text(obj: dict[str, Any], key: str, *, required: bool = True) -> str:
    value = obj.get(key)
    out = value.strip() if isinstance(value, str) else ""
    if required and not out:
        raise MalformedGenerationError(f"missing or empty {key!r}")
    return out


def _strings(
    obj: dict[str, Any], key: str, *, min_count: int = 0, max_count: int = 50
) -> list[str]:
    raw = obj.get(key)
    items = (
        [str(v).strip() for v in raw if isinstance(v, (str, int, float)) and str(v).strip()]
        if isinstance(raw, list)
        else []
    )
    if len(items) < min_count:
        raise MalformedGenerationError(
            f"{key!r} needs at least {min_count} entries, got {len(items)}"
        )
    return items[:max_count]


def _obj(parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise MalformedGenerationError("reply is not a JSON object")
    return parsed


def normalize_keyword(value: str) -> str:
    return " ".join(value.lower().split())


# ---------------------------------------------------------------------------
# validators — one per generator
# ---------------------------------------------------------------------------
def validate_blog(parsed: Any, used_keywords: list[str] | None = None) -> dict[str, Any]:
    obj = _obj(parsed)
    blog: dict[str, Any] = {
        "keyword": _text(obj, "keyword"),
        "searchIntent": _text(obj, "searchIntent"),
        "title": _text(obj, "title"),
        "metaDescription": _text(obj, "metaDescription"),
        "outline": _strings(obj, "outline", min_count=2, max_count=12),
        "body": _text(obj, "body"),
    }
    if len(blog["body"]) < MIN_BLOG_BODY_CHARS:
        raise MalformedGenerationError("body is too short to be a blog post")
    used = {normalize_keyword(k) for k in used_keywords or [] if k}
    if normalize_keyword(blog["keyword"]) in used:
        raise MalformedGenerationError(f"re-used an already-targeted keyword: {blog['keyword']!r}")
    return blog


def validate_comparison(parsed: Any) -> dict[str, Any]:
    obj = _obj(parsed)
    raw_points = obj.get("comparisonPoints")
    points: list[dict[str, str]] = []
    for p in raw_points if isinstance(raw_points, list) else []:
        if not isinstance(p, dict):
            continue
        try:
            points.append(
                {"dimension": _text(p, "dimension"), "us": _text(p, "us"), "them": _text(p, "them")}
            )
        except MalformedGenerationError:
            continue
    if len(points) < 3:
        raise MalformedGenerationError("comparisonPoints needs at least 3 complete points")
    return {
        "title": _text(obj, "title"),
        "metaDescription": _text(obj, "metaDescription"),
        "introParagraph": _text(obj, "introParagraph"),
        "comparisonPoints": points[:8],
        # The honest paragraph is the whole point of a fair page — required.
        "honestWhereTheyWin": _text(obj, "honestWhereTheyWin"),
        "cta": _text(obj, "cta"),
    }


def validate_niche_scan(parsed: Any, competitor_names: list[str]) -> dict[str, Any]:
    obj = _obj(parsed)
    by_key = {n.strip().lower(): n for n in competitor_names}
    angles: list[dict[str, Any]] = []
    raw_angles = obj.get("angles")
    for a in raw_angles if isinstance(raw_angles, list) else []:
        if not isinstance(a, dict):
            continue
        name = a.get("angle")
        saturation = str(a.get("saturation") or "").strip().lower()
        if not isinstance(name, str) or not name.strip() or saturation not in SATURATIONS:
            continue
        used_by: list[str] = []
        raw_used = a.get("usedBy")
        for u in raw_used if isinstance(raw_used, list) else []:
            match = by_key.get(str(u).strip().lower())
            if match and match not in used_by:
                used_by.append(match)
        note = a.get("note")
        angles.append(
            {
                "angle": name.strip(),
                "usedBy": used_by,
                "saturation": saturation,
                "note": note.strip() if isinstance(note, str) else "",
            }
        )
    if len(angles) < 2:
        raise MalformedGenerationError("a scan needs at least 2 well-formed angles")
    return {
        "angles": angles[:6],
        "gapRecommendation": _text(obj, "gapRecommendation"),
        "sourcesNote": _text(obj, "sourcesNote", required=False),
    }


def validate_video_script(parsed: Any) -> dict[str, Any]:
    obj = _obj(parsed)
    return {
        "hook": _text(obj, "hook"),
        "scriptBeats": _strings(obj, "scriptBeats", min_count=2, max_count=12),
        "onScreenText": _strings(obj, "onScreenText", min_count=1, max_count=12),
        "audioStyleNote": _text(obj, "audioStyleNote"),
        "caption": _text(obj, "caption"),
        "hashtags": [
            h.lstrip("#") for h in _strings(obj, "hashtags", max_count=15) if h.lstrip("#")
        ],
    }


def validate_ai_seo_pack(parsed: Any) -> dict[str, Any]:
    obj = _obj(parsed)
    faq: list[dict[str, str]] = []
    raw_faq = obj.get("faq")
    for qa in raw_faq if isinstance(raw_faq, list) else []:
        if not isinstance(qa, dict):
            continue
        try:
            faq.append({"question": _text(qa, "question"), "answer": _text(qa, "answer")})
        except MalformedGenerationError:
            continue
    if len(faq) < 2:
        raise MalformedGenerationError("faq needs at least 2 complete question/answer pairs")
    return {
        "citableSummary": _text(obj, "citableSummary"),
        "faq": faq[:6],
        "entityClarityNotes": _text(obj, "entityClarityNotes"),
        "llmsTxtEntry": _text(obj, "llmsTxtEntry"),
    }


# ---------------------------------------------------------------------------
# inputs + memory
# ---------------------------------------------------------------------------
def clean_competitor_names(names: list[str]) -> list[str]:
    """Trim, drop blanks and case-insensitive duplicates, keep the human's order."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = " ".join(str(raw).split())[:MAX_NAME_CHARS]
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def used_keywords(blog_payloads: list[dict[str, Any]]) -> list[str]:
    """Keywords this client's earlier blog posts targeted — real history, not scores."""
    out: list[str] = []
    for payload in blog_payloads:
        kw = payload.get("keyword") if isinstance(payload, dict) else None
        if isinstance(kw, str) and kw.strip() and kw.strip() not in out:
            out.append(kw.strip())
    return out


def find_similar_scan(names: list[str], scans: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Port of Cadence's ``findSimilarScan``: warn (never block) before re-scanning a set.

    ``scans`` are niche-scan payloads with ``competitorNames``. Returns
    ``{"scan", "shared", "isExact"}`` for an exact match or >= 60% overlap.
    """
    normalized = list(dict.fromkeys(n.strip().lower() for n in names if n.strip()))
    if len(normalized) < 2:
        return None
    best: dict[str, Any] | None = None
    for scan in scans:
        scan_set = {str(n).strip().lower() for n in scan.get("competitorNames") or []}
        if not scan_set:
            continue
        shared = [n for n in normalized if n in scan_set]
        if not shared:
            continue
        is_exact = len(shared) == len(normalized) == len(scan_set)
        overlap = len(shared) / max(len(normalized), len(scan_set))
        if (is_exact or overlap >= 0.6) and (
            best is None or is_exact or len(shared) > len(best["shared"])
        ):
            best = {"scan": scan, "shared": shared, "isExact": is_exact}
    return best


# ---------------------------------------------------------------------------
# Amplify sources
# ---------------------------------------------------------------------------
def _join(*parts: Any) -> str:
    return "\n\n".join(str(p).strip() for p in parts if isinstance(p, str) and p.strip())


def asset_source_text(kind: str, title: str, payload: dict[str, Any]) -> str:
    """The repurposable text of a saved asset, or "" when it has none.

    Cadence reads ``body`` for comparison pages and ``summary`` for niche scans,
    fields those items never carry, so both silently dropped out of its source
    list; here each kind is flattened from the fields it really has.
    """
    p = payload if isinstance(payload, dict) else {}
    if kind == "blog_post":
        return _join(p.get("title") or title, p.get("body"))
    if kind == "comparison_page":
        points = "\n".join(
            f"{c.get('dimension')}: us: {c.get('us')} | them: {c.get('them')}"
            for c in p.get("comparisonPoints") or []
            if isinstance(c, dict)
        )
        where = p.get("honestWhereTheyWin")
        return _join(
            p.get("title") or title,
            p.get("introParagraph"),
            points,
            f"Where they win: {where}" if isinstance(where, str) and where.strip() else "",
            p.get("cta"),
        )
    if kind == "niche_scan":
        angles = "\n".join(
            f"{a.get('angle')} ({a.get('saturation')} saturation): {a.get('note') or ''}".strip()
            for a in p.get("angles") or []
            if isinstance(a, dict)
        )
        gap = p.get("gapRecommendation")
        return _join(
            f"Gap none of them cover: {gap}" if isinstance(gap, str) and gap.strip() else "",
            angles,
        )
    if kind == "video_script":
        beats = "\n".join(str(b) for b in p.get("scriptBeats") or [])
        return _join(p.get("hook"), beats, p.get("caption"))
    if kind == "launch_kit":
        for key in ("announcementPost", "announcement_post", "summary"):
            value = p.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""
    return ""
