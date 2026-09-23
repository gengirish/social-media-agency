"""Insights — Cadence's computed analytics, per client, from real rows only.

Everything here is a count or a ratio over rows that exist: ``content_piece``
statuses and metadata (moderation record, pre-approval edit flag, publish
error), ``platform_account`` connections, ``analytics_snapshot`` metrics the
platforms actually returned, and ``moderation_flagged`` product events. No LLM
call, no estimate, no placeholder.

Every ratio and every recommendation has a minimum sample. Below it the value
is ``None`` / the rule reports ``insufficient_data`` with ``have`` and
``needed`` — never a conclusion drawn from one or two data points. The UI shows
those thresholds verbatim (Cadence's "How this works" explainer).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Final, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import (
    AnalyticsSnapshot,
    Client,
    ContentPiece,
    PlatformAccount,
    ProductEvent,
)
from agency.services import product_analytics as pa

#: Cadence's rule: no conclusion from n < 3, for every ratio on the page.
MIN_SAMPLE: Final = 3
#: Pending-backlog recommendation fires at this many posts waiting for review.
BACKLOG_MIN: Final = 5
#: Below this percentage a success/clean rate is worth flagging.
RATE_FLOOR: Final = 70
#: Platforms needed, each with MIN_SAMPLE measured posts, to compare engagement.
ENGAGEMENT_MIN_PLATFORMS: Final = 2

#: Statuses a post can only reach through the approval gate.
APPROVED_OR_LATER: Final = frozenset({"approved", "scheduled", "published", "failed"})

PLATFORM_NAMES: Final = {
    "twitter": "X",
    "x": "X",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "tiktok": "TikTok",
}


def platform_name(platform: str) -> str:
    return PLATFORM_NAMES.get(platform, platform.capitalize())


def pct(part: int, whole: int) -> int | None:
    return round(part / whole * 100) if whole else None


def gated_rate(part: int, whole: int, minimum: int = MIN_SAMPLE) -> dict[str, Any]:
    """A percentage that only exists once ``whole`` reaches ``minimum``."""
    if whole < minimum:
        return {
            "status": "insufficient_data",
            "value": None,
            "count": part,
            "n": whole,
            "needed": minimum,
        }
    return {
        "status": "available",
        "value": pct(part, whole),
        "count": part,
        "n": whole,
        "needed": minimum,
    }


# ---------------------------------------------------------------------------
# Content quality signal (Cadence §6 H2) — pure, ported from logic.test.js
# ---------------------------------------------------------------------------


def outcome_of(status: str, metadata: dict[str, Any] | None) -> str | None:
    """kept / edited / discarded for a post whose review is over; None while pending.

    - **kept**: approved (or later) with no edit before approval.
    - **edited**: approved (or later) after a body/hashtag edit made while it was
      still pending — later corrections do not count, as in Cadence.
    - **discarded**: rejected. (There is no delete endpoint for posts, so a
      rejection is the only "never approved" outcome that leaves a row.)
    """
    meta = metadata or {}
    if status in APPROVED_OR_LATER:
        return "edited" if meta.get("edited_before_approval") else "kept"
    if status == "rejected":
        return "discarded"
    return None


def tally_content_signal(
    pieces: list[tuple[str, str, dict[str, Any] | None]],
) -> dict[str, dict[str, int]]:
    """``(platform, status, metadata)`` rows → per-platform outcome counts."""
    tallies: dict[str, dict[str, int]] = {}
    for platform, status, metadata in pieces:
        outcome = outcome_of(status, metadata)
        if outcome is None:
            continue
        row = tallies.setdefault(
            platform, {"kept": 0, "edited": 0, "discarded": 0, "regenerated": 0}
        )
        row[outcome] += 1
    return tallies


def summarize_content_signal(
    content_signal: dict[str, dict[str, int]] | None,
) -> list[dict[str, Any]]:
    """Cadence's ``summarizeContentSignal``: rows only for platforms with ≥3 outcomes,
    most active first."""
    rows: list[dict[str, Any]] = []
    for platform, s in (content_signal or {}).items():
        total = s.get("kept", 0) + s.get("edited", 0) + s.get("discarded", 0)
        if total < MIN_SAMPLE:
            continue
        rows.append(
            {
                "platform": platform,
                "total": total,
                "kept": s.get("kept", 0),
                "edited": s.get("edited", 0),
                "discarded": s.get("discarded", 0),
                "kept_pct": round(s.get("kept", 0) / total * 100),
                "edited_pct": round(s.get("edited", 0) / total * 100),
                "discarded_pct": round(s.get("discarded", 0) / total * 100),
                "regenerated": s.get("regenerated", 0),
            }
        )
    rows.sort(key=lambda r: r["total"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Recommendations — pure comparisons over the computed stats
# ---------------------------------------------------------------------------


@dataclass
class InsightStats:
    by_platform: dict[str, int]  # post count per connected platform
    pending: int
    published: int
    failed: int
    moderation_checks: int
    moderation_flags: int
    engagement_by_platform: dict[str, dict[str, Any]]  # platform -> {posts, avg_engagement}


def recommendations_for(stats: InsightStats) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(recommendations that fired, every rule with its threshold and progress).

    Each rule states its minimum sample; below it the rule reports
    ``insufficient_data`` rather than firing or saying things look fine.
    """
    recs: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []

    total_connected = sum(stats.by_platform.values())
    max_count = max(stats.by_platform.values(), default=0)
    rules.append(
        {
            "id": "neglected-platform",
            "rule": f"Needs ≥{MIN_SAMPLE} posts across connected platforms, and one connected "
            "platform with none while another has ≥2.",
            "have": total_connected,
            "needed": MIN_SAMPLE,
            "status": "evaluated" if total_connected >= MIN_SAMPLE else "insufficient_data",
        }
    )
    if total_connected >= MIN_SAMPLE and max_count >= 2:
        neglected = next((p for p, c in sorted(stats.by_platform.items()) if c == 0), None)
        if neglected:
            name = platform_name(neglected)
            recs.append(
                {
                    "id": "neglected-platform",
                    "platform": neglected,
                    "text": f"You haven't created anything for {name} yet, despite it being "
                    f"connected — your other channels have up to {max_count}.",
                    "action_label": f"Create a post for {name}",
                    "href": f"/create/content?platform={neglected}",
                }
            )

    rules.append(
        {
            "id": "pending-backlog",
            "rule": f"Needs ≥{BACKLOG_MIN} posts waiting for approval, and more pending "
            "than published.",
            "have": stats.pending,
            "needed": BACKLOG_MIN,
            "status": "evaluated" if stats.pending >= BACKLOG_MIN else "insufficient_data",
        }
    )
    if stats.pending >= BACKLOG_MIN and stats.pending > stats.published:
        recs.append(
            {
                "id": "pending-backlog",
                "text": f"You have {stats.pending} posts waiting for approval — worth reviewing "
                "that backlog before creating more.",
                "action_label": "Go to Queue",
                "href": "/content",
            }
        )

    attempts = stats.published + stats.failed
    rules.append(
        {
            "id": "publish-failures",
            "rule": f"Needs ≥{MIN_SAMPLE} publish attempts; fires below {RATE_FLOOR}% success.",
            "have": attempts,
            "needed": MIN_SAMPLE,
            "status": "evaluated" if attempts >= MIN_SAMPLE else "insufficient_data",
        }
    )
    success = pct(stats.published, attempts)
    if attempts >= MIN_SAMPLE and success is not None and success < RATE_FLOOR:
        recs.append(
            {
                "id": "publish-failures",
                "text": f"{success}% of publish attempts succeeded ({stats.failed} of {attempts} "
                "failed) — usually an expired or missing account connection, not the content.",
                "action_label": "Go to Accounts",
                "href": "/setup/accounts",
            }
        )

    rules.append(
        {
            "id": "moderation-flags",
            "rule": f"Needs ≥{MIN_SAMPLE} moderation checks; fires below {RATE_FLOOR}% clean.",
            "have": stats.moderation_checks,
            "needed": MIN_SAMPLE,
            "status": "evaluated" if stats.moderation_checks >= MIN_SAMPLE else "insufficient_data",
        }
    )
    clean = pct(stats.moderation_checks - stats.moderation_flags, stats.moderation_checks)
    if stats.moderation_checks >= MIN_SAMPLE and clean is not None and clean < RATE_FLOOR:
        recs.append(
            {
                "id": "moderation-flags",
                "text": f"{100 - clean}% of moderation checks raised issues — worth revisiting "
                "this client's brand profile for overly bold claims.",
                "action_label": "Go to Profile",
                "href": "/setup/profile",
            }
        )

    measured = {p: e for p, e in stats.engagement_by_platform.items() if e["posts"] >= MIN_SAMPLE}
    rules.append(
        {
            "id": "engagement-leader",
            "rule": f"Needs ≥{MIN_SAMPLE} published posts with platform metrics on each of "
            f"≥{ENGAGEMENT_MIN_PLATFORMS} platforms before comparing engagement.",
            "have": len(measured),
            "needed": ENGAGEMENT_MIN_PLATFORMS,
            "status": "evaluated"
            if len(measured) >= ENGAGEMENT_MIN_PLATFORMS
            else "insufficient_data",
        }
    )
    if len(measured) >= ENGAGEMENT_MIN_PLATFORMS:
        ranked = sorted(measured.items(), key=lambda kv: kv[1]["avg_engagement"], reverse=True)
        (top, top_e), (low, low_e) = ranked[0], ranked[-1]
        if top_e["avg_engagement"] > low_e["avg_engagement"]:
            recs.append(
                {
                    "id": "engagement-leader",
                    "platform": top,
                    "text": f"{platform_name(top)} posts average {top_e['avg_engagement']} "
                    f"engagements ({top_e['posts']} measured) vs {low_e['avg_engagement']} on "
                    f"{platform_name(low)} ({low_e['posts']} measured).",
                }
            )
    return recs, rules


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


async def moderation_flag_count(db: AsyncSession, org_id: UUID, client_id: UUID) -> int:
    """``moderation_flagged`` events for this client (approvals moderation refused)."""
    rows = (
        await db.execute(
            select(ProductEvent.properties).where(
                ProductEvent.org_id == org_id, ProductEvent.name == pa.MODERATION_FLAGGED
            )
        )
    ).scalars()
    target = str(client_id)
    return sum(1 for props in rows if isinstance(props, dict) and props.get("client_id") == target)


async def latest_engagement(
    db: AsyncSession, org_id: UUID, client_id: UUID
) -> dict[str, dict[str, Any]]:
    """Per platform: posts with a measured engagement value, and their average.

    Snapshots hold lifetime totals per day, so only each post's latest snapshot
    counts. ``engagement IS NULL`` means not measured and is skipped, never 0.
    """
    latest = (
        select(AnalyticsSnapshot.content_id, func.max(AnalyticsSnapshot.date).label("d"))
        .where(AnalyticsSnapshot.content_id.is_not(None))
        .group_by(AnalyticsSnapshot.content_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(ContentPiece.platform, AnalyticsSnapshot.engagement)
            .join(AnalyticsSnapshot, AnalyticsSnapshot.content_id == ContentPiece.id)
            .join(
                latest,
                (latest.c.content_id == AnalyticsSnapshot.content_id)
                & (latest.c.d == AnalyticsSnapshot.date),
            )
            .where(
                ContentPiece.org_id == org_id,
                ContentPiece.client_id == client_id,
                AnalyticsSnapshot.engagement.is_not(None),
            )
        )
    ).all()
    sums: dict[str, list[int]] = defaultdict(list)
    for platform, engagement in rows:
        sums[platform].append(int(engagement))
    return {
        p: {"posts": len(v), "avg_engagement": round(sum(v) / len(v)), "total_engagement": sum(v)}
        for p, v in sums.items()
    }


async def build_summary(db: AsyncSession, org_id: UUID, client: Client) -> dict[str, Any]:
    """Everything the Insights screen shows, for one org-resolved client."""
    client_id = cast(UUID, client.id)
    pieces = (
        await db.execute(
            select(ContentPiece.platform, ContentPiece.status, ContentPiece.metadata_).where(
                ContentPiece.org_id == org_id, ContentPiece.client_id == client.id
            )
        )
    ).all()
    status_counts = Counter(str(s or "draft") for _, s, _ in pieces)
    platform_counts = Counter(str(p) for p, _, _ in pieces)

    connected = sorted(
        {
            str(p).lower()
            for p in (
                await db.execute(
                    select(PlatformAccount.platform).where(
                        PlatformAccount.org_id == org_id,
                        PlatformAccount.client_id == client.id,
                        PlatformAccount.status == "connected",
                    )
                )
            ).scalars()
        }
    )

    moderation_records = [
        (m or {}).get("moderation")
        for _, _, m in pieces
        if isinstance((m or {}).get("moderation"), dict)
    ]
    overridden = sum(1 for r in moderation_records if r and r.get("status") == "overridden")
    refused = await moderation_flag_count(db, org_id, client_id)
    # Every moderation run: approvals that recorded a result, plus refusals.
    checks = len(moderation_records) + refused
    flags = overridden + refused

    published = status_counts.get("published", 0)
    failed = status_counts.get("failed", 0)
    pending = status_counts.get("draft", 0)

    signal = tally_content_signal([(str(p), str(s or ""), m) for p, s, m in pieces])
    outcomes = {k: sum(row[k] for row in signal.values()) for k in ("kept", "edited", "discarded")}
    reviewed = outcomes["kept"] + outcomes["edited"]

    engagement = await latest_engagement(db, org_id, client_id)
    by_platform = {p: platform_counts.get(p, 0) for p in connected}
    recs, rules = recommendations_for(
        InsightStats(
            by_platform=by_platform,
            pending=pending,
            published=published,
            failed=failed,
            moderation_checks=checks,
            moderation_flags=flags,
            engagement_by_platform=engagement,
        )
    )

    measured_posts = sum(e["posts"] for e in engagement.values())
    return {
        "client_id": str(client.id),
        "min_sample": MIN_SAMPLE,
        "total_posts": len(pieces),
        "funnel": {
            "pending": pending,
            "approved": status_counts.get("approved", 0),
            "scheduled": status_counts.get("scheduled", 0),
            "published": published,
            "failed": failed,
            "rejected": status_counts.get("rejected", 0),
        },
        "connected_platforms": connected,
        "by_platform": [
            {"platform": p, "count": platform_counts.get(p, 0), "connected": p in connected}
            for p in sorted(set(connected) | set(platform_counts))
        ],
        "publish": {
            "attempts": published + failed,
            "published": published,
            "failed": failed,
            "success": gated_rate(published, published + failed),
        },
        "moderation": {
            "checks": checks,
            "flagged": flags,
            "clean": gated_rate(checks - flags, checks),
        },
        "quality_signal": {
            "rows": summarize_content_signal(signal),
            "rates": {
                "approved_without_edit": gated_rate(outcomes["kept"], reviewed),
                "moderation_flag_rate": gated_rate(flags, checks),
                "failed_publish_rate": gated_rate(failed, published + failed),
            },
        },
        "engagement": {
            "status": "available" if measured_posts else "unavailable",
            "posts_measured": measured_posts,
            "by_platform": [{"platform": p, **e} for p, e in sorted(engagement.items())],
        },
        "recommendations": recs,
        "thresholds": rules,
    }


async def advocacy_facts(db: AsyncSession, org_id: UUID, client: Client) -> dict[str, int]:
    """The only numbers the advocacy agent may cite. All are real counts."""
    summary = await build_summary(db, org_id, client)
    facts = {
        "posts_published": summary["funnel"]["published"],
        "posts_created": summary["total_posts"],
        "moderation_checks": summary["moderation"]["checks"],
        "connected_platforms": len(summary["connected_platforms"]),
    }
    if summary["engagement"]["posts_measured"]:
        facts["posts_with_platform_metrics"] = summary["engagement"]["posts_measured"]
        facts["total_engagements_measured"] = sum(
            e["total_engagement"] for e in summary["engagement"]["by_platform"]
        )
    return facts
