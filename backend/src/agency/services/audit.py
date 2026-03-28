"""Audit log service — track all state-changing operations."""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import AuditLog

logger = structlog.get_logger()


async def log_action(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID | None,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    details: dict | None = None,
    ip_address: str = "",
) -> None:
    """Record an audit log entry."""
    entry = AuditLog(
        org_id=org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
    logger.info(
        "audit_log",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        org_id=str(org_id),
    )
