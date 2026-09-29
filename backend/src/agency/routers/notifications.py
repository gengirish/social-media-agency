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
        # There *is* a producer now: ``services/scheduler.py::_remind_due_manual``
        # writes a ``posts_due`` digest when manual posts come due. This flag was
        # ``False`` while nothing called ``create_notification``, so a permanently
        # empty bell would not read as "you are all caught up"; the frontend also
        # skips re-fetching on it, so leaving it ``False`` would hide the very
        # reminders this exists to deliver. No ``reason`` either — an empty list is
        # now genuinely an empty list.
        "producers_wired": True,
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
