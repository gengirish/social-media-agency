"""Notifications router — in-app notification management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update

from agency.dependencies import get_current_user_id, get_db, get_org_id
from agency.models.tables import Notification

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    user_id: UUID = Depends(get_current_user_id),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.org_id == org_id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    notifs = result.scalars().all()

    count_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.org_id == org_id,
            Notification.read.is_(False),
        )
    )
    unread = count_result.scalar() or 0

    return {
        # `services/notifications.py::create_notification` is never called by any
        # route or agent, so nothing produces notifications today. Flag it rather
        # than let a permanently empty bell read as "you are all caught up".
        "producers_wired": False,
        # User-facing. The previous wording named the function that is missing a
        # caller, which told a marketer nothing and leaked the internals into the
        # bell (CF-16). The fact worth stating is only that the list will stay
        # empty, so nobody waits on it; ``producers_wired`` carries the detail for
        # anyone reading the API.
        "reason": "Notifications aren't switched on yet — this list stays empty for now.",
        "items": [
            {
                "id": str(n.id),
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "data": n.data,
                "read": n.read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifs
        ],
        "unread_count": unread,
    }


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
            Notification.org_id == org_id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    notif.read = True
    await db.commit()
    return {"status": "read"}


@router.patch("/read-all")
async def mark_all_read(
    user_id: UUID = Depends(get_current_user_id),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.org_id == org_id,
            Notification.read.is_(False),
        )
        .values(read=True)
    )
    await db.commit()
    return {"status": "all_read"}
