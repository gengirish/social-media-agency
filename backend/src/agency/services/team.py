"""Team collaboration — invites, roles, comments on content."""

from uuid import UUID, uuid4

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import User

ROLE_PERMISSIONS = {
    "admin": ["read", "write", "delete", "approve", "publish", "invite", "billing"],
    "manager": ["read", "write", "approve", "publish", "invite"],
    "content_creator": ["read", "write"],
    "viewer": ["read"],
}

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def invite_team_member(
    db: AsyncSession, org_id: UUID, email: str, role: str, invited_by: str
) -> dict:
    """Create a new user invitation."""
    if role not in ROLE_PERMISSIONS:
        return {"error": f"Invalid role. Must be one of: {list(ROLE_PERMISSIONS.keys())}"}

    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        return {"error": "User with this email already exists"}

    temp_password = str(uuid4())[:12]
    user = User(
        org_id=org_id,
        email=email,
        password_hash=_pwd_context.hash(temp_password),
        full_name=email.split("@")[0].replace(".", " ").title(),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {
        "status": "invited",
        "email": email,
        "role": role,
        "temp_password": temp_password,
        "user_id": str(user.id),
    }


async def list_team_members(db: AsyncSession, org_id: UUID) -> list:
    result = await db.execute(
        select(User).where(User.org_id == org_id).order_by(User.created_at)
    )
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "is_active": u.is_active,
            "permissions": ROLE_PERMISSIONS.get(u.role, []),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


async def update_member_role(db: AsyncSession, org_id: UUID, user_id: UUID, new_role: str) -> dict:
    if new_role not in ROLE_PERMISSIONS:
        return {"error": "Invalid role"}

    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == org_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return {"error": "User not found"}

    user.role = new_role
    await db.commit()
    return {"status": "updated", "role": new_role}


def check_permission(user_role: str, action: str) -> bool:
    return action in ROLE_PERMISSIONS.get(user_role, [])
