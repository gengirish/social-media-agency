"""Agency white-label mode — custom branding for agency users."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import WhiteLabel


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
        "is_active": wl.is_active,
    }


async def upsert_white_label(db: AsyncSession, org_id: UUID, data: dict) -> dict:
    result = await db.execute(select(WhiteLabel).where(WhiteLabel.org_id == org_id))
    wl = result.scalar_one_or_none()

    if wl:
        for key in ("custom_domain", "logo_url", "primary_color", "company_name", "support_email", "is_active"):
            if key in data:
                setattr(wl, key, data[key])
    else:
        wl = WhiteLabel(org_id=org_id, **{k: v for k, v in data.items() if k in (
            "custom_domain", "logo_url", "primary_color", "company_name", "support_email", "is_active"
        )})
        db.add(wl)

    await db.commit()
    return {"status": "saved"}
