"""Generation quota shared by every Create-screen generator.

1 generation = 1 user-initiated generate click that returned something usable
(an Amplify pack, a blog post, an email campaign, ...). The limit lives on
``subscription.generations_limit`` (falling back to ``PLAN_CONFIG``) and resets
alongside ``posts_used`` on ``invoice.paid``.

Two steps on purpose: ``require_generation_quota`` before calling the model,
``charge_generation`` only after a usable result came back — charging for a
failed generation would bill the user for our failure.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import Subscription
from agency.services.billing import generations_limit_for


def quota_exceeded(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_402_PAYMENT_REQUIRED,
        detail={"code": "generation_quota_exceeded", "message": detail},
    )


async def require_generation_quota(db: AsyncSession, org_id: UUID) -> Subscription:
    """402 unless the org has at least one generation left this period."""
    sub = (
        await db.execute(select(Subscription).where(Subscription.org_id == org_id))
    ).scalar_one_or_none()
    if sub is None:
        raise quota_exceeded("No subscription on file for this workspace.")
    if (sub.generations_used or 0) >= generations_limit_for(sub):
        raise quota_exceeded("Generation limit reached for this billing period.")
    return sub


async def charge_generation(db: AsyncSession, org_id: UUID) -> None:
    """Increment in SQL so two concurrent requests cannot both write N+1.

    The check in ``require_generation_quota`` and this increment are still two
    statements, so concurrent requests at the boundary can overshoot by one.
    Caller commits.
    """
    await db.execute(
        update(Subscription)
        .where(Subscription.org_id == org_id)
        .values(generations_used=Subscription.generations_used + 1)
    )
