"""Notifications router — in-app notification management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import Notification

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user.id, Notification.org_id == org_id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    notifs = result.scalars().all()

    count_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.org_id == org_id,
            Notification.read == False,
        )
    )
    unread = count_result.scalar() or 0

    return {
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
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
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
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.org_id == org_id,
            Notification.read == False,
        )
        .values(read=True)
    )
    await db.commit()
    return {"status": "all_read"}
