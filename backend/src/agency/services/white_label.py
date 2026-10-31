"""Agency white-label mode — custom branding for agency users."""

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import WhiteLabel
from agency.services.url_safety import UnsafeURLError, assert_safe_link

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


async def get_white_label(db: AsyncSession, org_id: UUID) -> dict | None:
    result = await db.execute(select(WhiteLabel).where(WhiteLabel.org_id == org_id))
    wl = result.scalar_one_or_none()
    if not wl:
        return None
    return {
        "id": str(wl.id),
        "custom_domain": wl.custom_domain,
        "logo_url": wl.logo_url,
        "primary_color": wl.primary_color,
        "company_name": wl.company_name,
        "support_email": wl.support_email,
        "portal_enabled": wl.portal_enabled,
        "email_from_name": wl.email_from_name,
        "is_active": wl.is_active,
    }


async def upsert_white_label(db: AsyncSession, org_id: UUID, data: dict) -> dict:
    result = await db.execute(select(WhiteLabel).where(WhiteLabel.org_id == org_id))
    wl = result.scalar_one_or_none()

    if wl:
        for key in (
            "custom_domain",
            "logo_url",
            "primary_color",
            "company_name",
            "support_email",
            "portal_enabled",
            "email_from_name",
            "is_active",
        ):
            if key in data:
                setattr(wl, key, data[key])
    else:
        wl = WhiteLabel(
            org_id=org_id,
            **{
                k: v
                for k, v in data.items()
                if k
                in (
                    "custom_domain",
                    "logo_url",
                    "primary_color",
                    "company_name",
                    "support_email",
                    "portal_enabled",
                    "email_from_name",
                    "is_active",
                )
            },
        )
        db.add(wl)

    await db.commit()
    return {"status": "saved"}


async def agency_branding(db: AsyncSession, org: Any) -> dict[str, Any]:
    """Name, logo and colour an agency's client sees: active white-label, else the org name.

    Used by the client review page and the campaign pack. The logo URL and colour
    end up in a public page or a shared document, so both are re-checked here —
    ``PUT /integrations/white-label`` stores whatever it is sent.
    """
    wl = (
        await db.execute(
            select(WhiteLabel).where(WhiteLabel.org_id == org.id, WhiteLabel.is_active.is_(True))
        )
    ).scalar_one_or_none()
    name = org.name
    logo_url: str | None = None
    color: str | None = None
    support_email: str | None = None
    if wl is not None:
        name = (wl.company_name or "").strip() or org.name
        if wl.logo_url:
            try:
                logo_url = assert_safe_link(wl.logo_url)
            except UnsafeURLError:
                logo_url = None
        if wl.primary_color and _HEX_COLOR.match(wl.primary_color):
            color = wl.primary_color
        support_email = wl.support_email or None
    return {
        "name": name,
        "logo_url": logo_url,
        "primary_color": color,
        "support_email": support_email,
    }
