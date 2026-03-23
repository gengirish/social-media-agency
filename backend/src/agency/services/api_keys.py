"""REST API key management for external integrations."""

import hashlib
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import ApiKey


def _generate_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (full_key, prefix, hash)."""
    raw = f"cf_{secrets.token_urlsafe(32)}"
    prefix = raw[:10]
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, prefix, key_hash


async def create_api_key(
    db: AsyncSession, org_id: UUID, name: str, permissions: list[str] | None = None
) -> dict:
    raw_key, prefix, key_hash = _generate_key()

    key = ApiKey(
        org_id=org_id,
        name=name,
        key_hash=key_hash,
        key_prefix=prefix,
        permissions=permissions or ["read"],
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)

    return {
        "id": str(key.id),
        "name": name,
        "key": raw_key,  # Only shown once
        "prefix": prefix,
        "permissions": key.permissions,
    }


async def list_api_keys(db: AsyncSession, org_id: UUID) -> list:
    result = await db.execute(
        select(ApiKey).where(ApiKey.org_id == org_id, ApiKey.is_active == True)
        .order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [
        {
            "id": str(k.id),
            "name": k.name,
            "prefix": k.key_prefix,
            "permissions": k.permissions,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in keys
    ]


async def revoke_api_key(db: AsyncSession, org_id: UUID, key_id: UUID) -> dict:
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.org_id == org_id)
    )
    key = result.scalar_one_or_none()
    if not key:
        return {"error": "API key not found"}
    key.is_active = False
    await db.commit()
    return {"status": "revoked"}


async def validate_api_key(db: AsyncSession, raw_key: str) -> dict | None:
    """Validate an API key and return org_id + permissions."""
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    prefix = raw_key[:10]

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_prefix == prefix,
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        return None

    from datetime import datetime, timezone
    key.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "org_id": str(key.org_id),
        "permissions": key.permissions,
        "key_id": str(key.id),
    }
