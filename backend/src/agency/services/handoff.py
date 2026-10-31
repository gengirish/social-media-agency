"""The one shape approved content leaves CampaignForge in.

Agencies keep the scheduler they already use; CampaignForge hands it approved
posts. Two exits carry the same object so a recipe built on one works on the other:

* ``GET /api/v1/public/content`` (X-API-Key) — polled, e.g. by a Zapier/Make
  "new item" trigger, which dedupes on ``id``.
* the ``content.approved`` webhook (HMAC-signed) — pushed the moment a post is
  approved, from the dashboard or a client review link.

Only approved-or-later content is ever serialised for hand-off: a draft has not
passed moderation or a human, and handing it to a scheduler would post unreviewed
copy to a client's account (product rule 3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import Client

#: Statuses the public API will hand off. Never ``draft``/``rejected``/``failed``.
HANDOFF_STATUSES: Final = frozenset({"approved", "scheduled", "published"})


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def handoff_item(piece: Any, *, client_name: str | None) -> dict[str, Any]:
    """Serialise an approved piece for a scheduler. Raises on a non-handoff status.

    ``approved_at`` comes from ``metadata.approval`` (written since 261031), falling
    back to the moderation record's timestamp for pieces approved before that. It is
    ``None`` rather than a guess when neither exists.
    """
    if piece.status not in HANDOFF_STATUSES:
        raise ValueError(f"content in status {piece.status!r} is not handed off")
    meta = piece.metadata_ or {}
    approval = _dict(meta.get("approval"))
    moderation = _dict(meta.get("moderation"))
    ad = _dict(meta.get("ad"))
    return {
        "id": str(piece.id),
        "client_id": str(piece.client_id),
        "client_name": client_name,
        "campaign_id": str(piece.campaign_id) if piece.campaign_id else None,
        "platform": piece.platform,
        "content_type": piece.content_type,
        "title": piece.title or "",
        "body": piece.body or "",
        "hashtags": list(piece.hashtags or []),
        "media_urls": list(piece.media_urls or []),
        "status": piece.status,
        "scheduled_at": _iso(piece.scheduled_at),
        "published_at": _iso(piece.published_at),
        "approved_at": approval.get("at") or moderation.get("at"),
        "approved_via": approval.get("via"),
        "ad_fields": ad.get("fields") if ad else None,
        "updated_at": _iso(piece.updated_at),
    }


async def client_names(db: AsyncSession, org_id: UUID, client_ids: set[Any]) -> dict[str, str]:
    """``{client_id: brand_name}`` for the given ids, org-scoped."""
    if not client_ids:
        return {}
    rows = (
        await db.execute(
            select(Client.id, Client.brand_name).where(
                Client.org_id == org_id, Client.id.in_(list(client_ids))
            )
        )
    ).all()
    return {str(cid): name for cid, name in rows}


async def approved_event_payload(db: AsyncSession, piece: Any) -> dict[str, Any]:
    """The ``content.approved`` webhook body.

    The four top-level ids are what the event carried before 261031 and stay for
    existing receivers; ``content`` is the full hand-off object, so a receiver can
    create the post in a scheduler without calling back.
    """
    names = await client_names(db, piece.org_id, {piece.client_id})
    return {
        "content_id": str(piece.id),
        "campaign_id": str(piece.campaign_id) if piece.campaign_id else None,
        "client_id": str(piece.client_id),
        "platform": piece.platform,
        "content": handoff_item(piece, client_name=names.get(str(piece.client_id))),
    }
