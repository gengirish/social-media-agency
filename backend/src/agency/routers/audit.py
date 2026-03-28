"""Audit log router — view audit trail (enterprise feature)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import AuditLog

router = APIRouter(prefix="/audit", tags=["Enterprise - Audit"])


@router.get("")
async def list_audit_logs(
    resource_type: str | None = None,
    action: str | None = None,
    limit: int = Query(default=50, le=200),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """List audit log entries for the organization."""
    q = select(AuditLog).where(AuditLog.org_id == org_id)
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)
    if action:
        q = q.where(AuditLog.action == action)
    q = q.order_by(AuditLog.created_at.desc()).limit(limit)

    result = await db.execute(q)
    logs = result.scalars().all()

    return {
        "items": [
            {
                "id": str(l.id),
                "action": l.action,
                "resource_type": l.resource_type,
                "resource_id": l.resource_id,
                "details": l.details,
                "user_id": str(l.user_id) if l.user_id else None,
                "ip_address": l.ip_address,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ]
    }
