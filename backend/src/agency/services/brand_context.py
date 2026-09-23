"""Tenant-scoped client lookup and the brand context every generator reads.

Every Create-screen agent (Amplify, Content, Email, Launch, Ads, ...) needs the
same two things: the client, resolved against the caller's org (there is no
row-level security — this filter *is* the isolation boundary), and the client's
brand voice. Keeping one loader means a new brand field reaches every agent.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import BrandProfile, Client


async def get_org_client(db: AsyncSession, client_id: UUID, org_id: UUID) -> Client:
    """The client, or 404 — including when it belongs to another org."""
    client = (
        await db.execute(select(Client).where(Client.id == client_id, Client.org_id == org_id))
    ).scalar_one_or_none()
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return client


async def load_brand_context(db: AsyncSession, client: Client, org_id: UUID) -> dict[str, Any]:
    """Client basics plus the brand profile, when one exists.

    ``client.settings`` carries the Setup-screen extras (active campaign focus,
    strategy lens synthesis); they are passed through under ``setup`` so agents
    can reference them without every agent re-reading the column.
    """
    settings: Any = client.settings
    brand: dict[str, Any] = {
        "brand_name": client.brand_name,
        "industry": client.industry or "",
        "description": client.description or "",
        "website_url": client.website_url or "",
        "setup": settings if isinstance(settings, dict) else {},
    }
    bp = (
        await db.execute(
            select(BrandProfile).where(
                BrandProfile.client_id == client.id, BrandProfile.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if bp is not None:
        brand.update(
            {
                "voice_description": bp.voice_description or "",
                "tone_attributes": bp.tone_attributes or {},
                "vocabulary_include": bp.vocabulary_include or [],
                "vocabulary_exclude": bp.vocabulary_exclude or [],
                "example_posts": bp.example_posts or [],
                "style_rules": bp.style_rules or [],
                "emoji_policy": bp.emoji_policy or "",
                "target_audience": bp.target_audience or "",
                "competitor_differentiation": bp.competitor_differentiation or "",
            }
        )
    return brand


def brand_prompt_block(brand: dict[str, Any]) -> str:
    """Brand context as a prompt section. Omits empty fields rather than printing blanks."""
    lines = [f"Brand: {brand.get('brand_name', '')}"]
    for key, label in (
        ("industry", "Industry"),
        ("description", "What it is"),
        ("website_url", "Website"),
        ("target_audience", "Audience"),
        ("competitor_differentiation", "Differentiator"),
        ("voice_description", "Voice"),
        ("emoji_policy", "Emoji policy"),
    ):
        value = brand.get(key)
        if value:
            lines.append(f"{label}: {value}")
    # Setup › Profile's human-picked register (Cadence's fallback when no voice guide exists).
    tone = brand.get("tone_attributes")
    register = tone.get("register") if isinstance(tone, dict) else None
    if isinstance(register, str) and register:
        lines.append(f"Tone register: {register}")
    if brand.get("vocabulary_include"):
        lines.append("Use words like: " + ", ".join(map(str, brand["vocabulary_include"])))
    if brand.get("vocabulary_exclude"):
        lines.append("Never use: " + ", ".join(map(str, brand["vocabulary_exclude"])))
    if brand.get("style_rules"):
        lines.append("Style rules: " + "; ".join(map(str, brand["style_rules"])))
    campaign = (brand.get("setup") or {}).get("campaign_focus")
    if isinstance(campaign, dict) and campaign.get("description"):
        lines.append(f"Active campaign right now: {campaign['description']}")
    return "\n".join(lines)
