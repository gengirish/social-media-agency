"""Export — everything stored for one client, as one JSON document.

Cadence downloads a .txt of every generated item for the active product. Here
the same scope comes from the database: client profile (incl. Setup extras in
``client.settings``), brand profile, connected accounts (no tokens), campaigns,
posts, creative assets and Amplify pack history. Every query filters on
``org_id`` and the org-resolved client id.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import (
    BrandProfile,
    Campaign,
    Client,
    ContentPiece,
    CreativeAsset,
    PlatformAccount,
    RepurposePack,
)
from agency.services.creative_assets import asset_out

EXPORT_VERSION = 1


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return None


async def export_client(db: AsyncSession, org_id: UUID, client: Client) -> dict[str, Any]:
    bp = (
        await db.execute(
            select(BrandProfile).where(
                BrandProfile.org_id == org_id, BrandProfile.client_id == client.id
            )
        )
    ).scalar_one_or_none()
    accounts = (
        await db.execute(
            select(PlatformAccount).where(
                PlatformAccount.org_id == org_id, PlatformAccount.client_id == client.id
            )
        )
    ).scalars()
    campaigns = (
        await db.execute(
            select(Campaign)
            .where(Campaign.org_id == org_id, Campaign.client_id == client.id)
            .order_by(Campaign.created_at)
        )
    ).scalars()
    posts = (
        await db.execute(
            select(ContentPiece)
            .where(ContentPiece.org_id == org_id, ContentPiece.client_id == client.id)
            .order_by(ContentPiece.created_at)
        )
    ).scalars()
    assets = (
        await db.execute(
            select(CreativeAsset)
            .where(CreativeAsset.org_id == org_id, CreativeAsset.client_id == client.id)
            .order_by(CreativeAsset.created_at)
        )
    ).scalars()
    packs = (
        await db.execute(
            select(RepurposePack)
            .where(RepurposePack.org_id == org_id, RepurposePack.client_id == client.id)
            .order_by(RepurposePack.created_at)
        )
    ).scalars()

    post_rows = [
        {
            "id": str(p.id),
            "campaign_id": str(p.campaign_id) if p.campaign_id else None,
            "platform": p.platform,
            "content_type": p.content_type,
            "status": p.status,
            "title": p.title,
            "body": p.body,
            "hashtags": p.hashtags or [],
            "metadata": p.metadata_ or {},
            "scheduled_at": _iso(p.scheduled_at),
            "published_at": _iso(p.published_at),
            "created_at": _iso(p.created_at),
        }
        for p in posts
    ]
    asset_rows = [asset_out(a) for a in assets]
    pack_rows = [
        {
            "id": str(k.id),
            "source_content_id": str(k.source_content_id) if k.source_content_id else None,
            "source_text": k.source_text,
            "platforms": k.platforms or [],
            "atom_count": k.atom_count,
            "committed_count": k.committed_count,
            "created_at": _iso(k.created_at),
        }
        for k in packs
    ]
    campaign_rows = [
        {
            "id": str(c.id),
            "name": c.name,
            "objective": c.objective,
            "channels": c.channels or [],
            "status": c.status,
            "start_date": _iso(c.start_date),
            "end_date": _iso(c.end_date),
            "created_at": _iso(c.created_at),
        }
        for c in campaigns
    ]
    account_rows = [
        {
            "platform": a.platform,
            "account_handle": a.account_handle,
            "display_name": a.display_name,
            "status": a.status,
            "connected_at": _iso(a.created_at),
        }
        for a in accounts
    ]
    brand = None
    if bp is not None:
        brand = {
            "voice_description": bp.voice_description,
            "tone_attributes": bp.tone_attributes or {},
            "vocabulary_include": bp.vocabulary_include or [],
            "vocabulary_exclude": bp.vocabulary_exclude or [],
            "example_posts": bp.example_posts or [],
            "style_rules": bp.style_rules or [],
            "emoji_policy": bp.emoji_policy,
            "competitor_differentiation": bp.competitor_differentiation,
            "target_audience": bp.target_audience,
            "updated_at": _iso(bp.updated_at),
        }
    settings: Any = client.settings
    return {
        "export_version": EXPORT_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "client": {
            "id": str(client.id),
            "brand_name": client.brand_name,
            "industry": client.industry,
            "description": client.description,
            "website_url": client.website_url,
            "contact_email": client.contact_email,
            "is_active": client.is_active,
            "settings": settings if isinstance(settings, dict) else {},
            "created_at": _iso(client.created_at),
        },
        "brand_profile": brand,
        "connected_accounts": account_rows,
        "campaigns": campaign_rows,
        "posts": post_rows,
        "creative_assets": asset_rows,
        "repurpose_packs": pack_rows,
        "counts": {
            "campaigns": len(campaign_rows),
            "posts": len(post_rows),
            "creative_assets": len(asset_rows),
            "repurpose_packs": len(pack_rows),
            "connected_accounts": len(account_rows),
        },
    }
