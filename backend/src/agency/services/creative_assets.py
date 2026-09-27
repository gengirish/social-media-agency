"""Store for the Create screens' long-form output.

Each generator router (content, email, launch, ads, ...) calls ``save_asset``
after a successful generation; the generic ``/assets`` router lists, reads,
renames and deletes them. ``kind`` is a closed set so a typo cannot create an
orphan category the UI never shows.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import CreativeAsset

#: kind → the Create screen that produces it (documentation; the UI filters on kind).
ASSET_KINDS: dict[str, str] = {
    "blog_post": "Create › Content",
    "comparison_page": "Create › Content",
    "niche_scan": "Create › Content",
    "video_script": "Create › Content",
    "email_campaign": "Create › Email",
    "launch_kit": "Create › Launch",
    "community_kit": "Create › Launch",
    "outreach_pitch": "Create › Launch",
    "ad_set": "Create › Ads",
    "advocacy": "Insights › Customer advocacy",
    "strategy_lens": "Setup › Profile",
}

MAX_TITLE = 500


def validate_kind(kind: str) -> str:
    if kind not in ASSET_KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unknown asset kind {kind!r}; expected one of {sorted(ASSET_KINDS)}",
        )
    return kind


def _as_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None


async def save_asset(
    db: AsyncSession,
    *,
    org_id: UUID,
    client_id: UUID,
    kind: str,
    title: str,
    payload: dict[str, Any],
    created_by: Any = None,
    source_asset_id: UUID | None = None,
) -> CreativeAsset:
    """Add an asset row. ``client_id`` must already be org-resolved. Caller commits."""
    asset = CreativeAsset(
        org_id=org_id,
        client_id=client_id,
        kind=validate_kind(kind),
        title=(title or "")[:MAX_TITLE],
        payload=payload,
        source_asset_id=source_asset_id,
        created_by=_as_uuid(created_by),
    )
    db.add(asset)
    await db.flush()
    return asset


async def get_org_asset(db: AsyncSession, asset_id: UUID, org_id: UUID) -> CreativeAsset:
    """The asset, or 404 — including when it belongs to another org."""
    asset = (
        await db.execute(
            select(CreativeAsset).where(
                CreativeAsset.id == asset_id, CreativeAsset.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return asset


def asset_out(asset: CreativeAsset) -> dict[str, Any]:
    return {
        "id": str(asset.id),
        "client_id": str(asset.client_id),
        "kind": asset.kind,
        "title": asset.title,
        "payload": asset.payload or {},
        "source_asset_id": str(asset.source_asset_id) if asset.source_asset_id else None,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
    }
