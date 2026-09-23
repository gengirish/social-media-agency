"""Activity log — Cadence's per-product event list, rebuilt from real rows.

Cadence appends to a localStorage array as things happen. Here the history
already exists in the tables, so the log is derived from them, each entry
timestamped by the column that records when it happened:

- ``post.published`` ← ``content_piece.published_at``
- ``post.scheduled`` / ``post.failed`` / ``post.rejected`` ← the piece's
  ``updated_at`` while it holds that status (the last change *is* that move:
  editing a scheduled post resets it to draft)
- ``moderation.passed`` / ``moderation.overridden`` ← ``metadata.moderation.at``
- ``moderation.flagged`` ← ``moderation_flagged`` product events
- ``post.created`` ← ``content_piece.created_at``
- ``account.connected`` ← ``platform_account.created_at``
- ``profile.updated`` ← ``brand_profile.updated_at``
- ``asset.created`` ← ``creative_asset.created_at``
- ``pack.generated`` ← ``repurpose_pack.created_at``
- ``campaign.created`` ← ``campaign.created_at``
- anything in ``audit_log`` whose ``details.client_id`` is this client.

Everything is filtered on ``org_id`` *and* the org-resolved ``client_id``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import (
    AuditLog,
    BrandProfile,
    Campaign,
    Client,
    ContentPiece,
    CreativeAsset,
    PlatformAccount,
    ProductEvent,
    RepurposePack,
)
from agency.services import product_analytics as pa
from agency.services.insights import platform_name

#: Cadence keeps the last 50 events.
MAX_EVENTS: Final = 50

ASSET_KIND_LABELS: Final = {
    "blog_post": "blog post",
    "comparison_page": "comparison page",
    "niche_scan": "niche scan",
    "video_script": "video script",
    "email_campaign": "email campaign",
    "launch_kit": "launch kit",
    "community_kit": "community kit",
    "outreach_pitch": "outreach pitch",
    "ad_set": "ad set",
    "advocacy": "advocacy pack",
    "strategy_lens": "strategy lens panel",
}


def _ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _label(piece: Any) -> str:
    title = (piece.title or "").strip()
    return f"“{title[:60]}”" if title else "a post"


async def client_activity(
    db: AsyncSession, org_id: UUID, client: Client, limit: int = MAX_EVENTS
) -> list[dict[str, Any]]:
    events: list[tuple[datetime, str, str, str]] = []  # (at, action, detail, ref)

    def add(at: Any, action: str, detail: str, ref: str) -> None:
        when = _ts(at)
        if when is not None:
            events.append((when, action, detail, ref))

    pieces = (
        await db.execute(
            select(ContentPiece).where(
                ContentPiece.org_id == org_id, ContentPiece.client_id == client.id
            )
        )
    ).scalars()
    for p in pieces:
        name = platform_name(str(p.platform))
        ref = str(p.id)
        add(p.created_at, "post.created", f"Drafted {_label(p)} for {name}", ref)
        if p.status == "published":
            add(p.published_at, "post.published", f"Published {_label(p)} to {name}", ref)
        elif p.status == "scheduled":
            when = p.scheduled_at.strftime("%b %d, %H:%M UTC") if p.scheduled_at else "later"
            add(p.updated_at, "post.scheduled", f"Scheduled {_label(p)} for {name} — {when}", ref)
        elif p.status == "failed":
            add(p.updated_at, "post.failed", f"Publishing {_label(p)} to {name} failed", ref)
        elif p.status == "rejected":
            add(p.updated_at, "post.rejected", f"Rejected {_label(p)} for {name}", ref)
        moderation = (p.metadata_ or {}).get("moderation")
        if isinstance(moderation, dict):
            if moderation.get("status") == "overridden":
                add(
                    moderation.get("at"),
                    "moderation.overridden",
                    f"Approved {_label(p)} despite moderation issues",
                    ref,
                )
            else:
                add(moderation.get("at"), "post.approved", f"Approved {_label(p)} for {name}", ref)

    target = str(client.id)
    flag_rows = (
        await db.execute(
            select(ProductEvent).where(
                ProductEvent.org_id == org_id, ProductEvent.name == pa.MODERATION_FLAGGED
            )
        )
    ).scalars()
    for ev in flag_rows:
        props = ev.properties if isinstance(ev.properties, dict) else {}
        if props.get("client_id") != target:
            continue
        issues = props.get("issue_count")
        detail = f"Moderation flagged a {platform_name(str(props.get('platform') or 'post'))} post"
        if isinstance(issues, int):
            detail += f" ({issues} issue{'s' if issues != 1 else ''})"
        add(ev.occurred_at, "moderation.flagged", detail, str(ev.id))

    accounts = (
        await db.execute(
            select(PlatformAccount).where(
                PlatformAccount.org_id == org_id, PlatformAccount.client_id == client.id
            )
        )
    ).scalars()
    for a in accounts:
        add(
            a.created_at,
            "account.connected",
            f"Connected {platform_name(str(a.platform))} ({a.account_handle})",
            str(a.id),
        )

    bp = (
        await db.execute(
            select(BrandProfile).where(
                BrandProfile.org_id == org_id, BrandProfile.client_id == client.id
            )
        )
    ).scalar_one_or_none()
    if bp is not None:
        add(bp.updated_at or bp.created_at, "profile.updated", "Brand profile saved", str(bp.id))

    assets = (
        await db.execute(
            select(CreativeAsset).where(
                CreativeAsset.org_id == org_id, CreativeAsset.client_id == client.id
            )
        )
    ).scalars()
    for asset in assets:
        kind = ASSET_KIND_LABELS.get(str(asset.kind), str(asset.kind))
        add(asset.created_at, "asset.created", f"Saved a {kind}", str(asset.id))

    packs = (
        await db.execute(
            select(RepurposePack).where(
                RepurposePack.org_id == org_id, RepurposePack.client_id == client.id
            )
        )
    ).scalars()
    for pack in packs:
        add(
            pack.created_at,
            "pack.generated",
            f"Amplify pack generated — {pack.atom_count} drafts",
            str(pack.id),
        )

    campaigns = (
        await db.execute(
            select(Campaign).where(Campaign.org_id == org_id, Campaign.client_id == client.id)
        )
    ).scalars()
    for c in campaigns:
        add(c.created_at, "campaign.created", f"Campaign “{c.name}” created", str(c.id))

    audits = (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.org_id == org_id)
            .order_by(AuditLog.created_at.desc())
            .limit(500)
        )
    ).scalars()
    for entry in audits:
        details = entry.details if isinstance(entry.details, dict) else {}
        if details.get("client_id") != target:
            continue
        detail = str(
            details.get("summary") or f"{entry.action} {entry.resource_type or ''}".strip()
        )
        add(entry.created_at, str(entry.action), detail, str(entry.id))

    events.sort(key=lambda e: e[0], reverse=True)
    return [
        {"id": f"{action}:{ref}", "action": action, "detail": detail, "at": at.isoformat()}
        for at, action, detail, ref in events[:limit]
    ]
