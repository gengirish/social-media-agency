"""Repairs to an org's mandatory rows, applied on the read paths that notice.

Both places an org is born — ``routers/auth.py::signup`` and
``dependencies.py::_resolve_clerk_user`` — create the one client a personal
account needs, because ``Campaign.client_id`` is NOT NULL. Neither ran again
afterwards, so an org whose client was deleted (or which predates that
provisioning) stayed broken forever: Setup › Clients told the user to sign out
and back in, and signing back in restored nothing, because the resolver finds
their existing user row and never reaches the provisioning branch.

``ensure_personal_brand`` is that restore step, run where the frontend actually
asks who it is talking to (``GET /auth/me``).
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import Client, Organization

logger = structlog.get_logger()


async def ensure_personal_brand(db: AsyncSession, org_id: UUID) -> Client | None:
    """Give a personal org its single brand record back, if it has none.

    Returns the created client, or ``None`` when nothing was needed — a business
    account (whose empty roster is a legitimate state it fills itself) or an org
    that already has at least one client, active or archived.

    The organization row is locked for the check-then-insert so two concurrent
    ``/auth/me`` calls — the frontend fires one per tab — cannot both decide the
    brand is missing and create one each. There is no unique constraint to lean
    on: an org may legitimately hold many clients once it flips to business.
    """
    org = (
        await db.execute(
            select(Organization).where(Organization.id == org_id).with_for_update()
        )
    ).scalar_one_or_none()
    if org is None or org.account_type != "personal":
        return None

    existing = (
        await db.execute(select(Client.id).where(Client.org_id == org_id).limit(1))
    ).first()
    if existing is not None:
        return None

    client = Client(org_id=org_id, brand_name=org.name)
    db.add(client)
    await db.commit()
    await db.refresh(client)
    logger.info("personal_brand_restored", org_id=str(org_id), client_id=str(client.id))
    return client
