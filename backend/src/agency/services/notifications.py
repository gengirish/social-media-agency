"""Notification service — create and manage in-app notifications."""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import Notification

logger = structlog.get_logger()


async def create_notification(
    db: AsyncSession,
    user_id: UUID,
    org_id: UUID,
    type: str,
    title: str,
    body: str = "",
    data: dict | None = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        org_id=org_id,
        type=type,
        title=title,
        body=body,
        data=data or {},
    )
    db.add(notif)
    await db.flush()
    return notif
