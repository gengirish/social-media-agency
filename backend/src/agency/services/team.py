"""Team collaboration — invites, roles, comments on content.

There is exactly **one** role vocabulary in this codebase and it lives in
``agency.permissions``. This module used to carry a second one
(``admin``/``manager``/``content_creator``/``viewer`` with an ad-hoc action
list) that existed only to decorate the team-list response. Two vocabularies
meant the string the UI showed and the string a gate would read could disagree
silently, so it is gone: capabilities reported here are the same
:func:`capabilities_for` a router gate resolves.

No capability *check* happens in this module. Gates belong in routers — the
scheduler and the agent pipeline call services with no user in scope.
"""

from uuid import UUID, uuid4

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import Organization, User
from agency.permissions import ROLES, capabilities_for

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

#: What an invite may assign. ``owner`` is deliberately absent: an org has one
#: owner, established at provisioning, and an invite must not be able to mint a
#: second one. Transferring ownership is a different operation.
INVITABLE_ROLES: tuple[str, ...] = tuple(r for r in ROLES if r != "owner")


async def _account_type(db: AsyncSession, org_id: UUID) -> str:
    """The org's account shape, or the narrower ``personal`` if it has none."""
    result = await db.execute(
        select(Organization.account_type).where(Organization.id == org_id)
    )
    return result.scalar_one_or_none() or "personal"


async def invite_team_member(
    db: AsyncSession, org_id: UUID, email: str, role: str, invited_by: str
) -> dict:
    """Create a new user invitation, and upgrade the org to ``business``.

    **The invite is the B2C → B2B upgrade.** A new org is provisioned
    ``account_type='personal'``; a solo account that gains a second seat is by
    definition no longer solo, so the first successful invite flips the column
    to ``'business'``. One way — nothing here ever writes ``'personal'`` back.

    The flip shares the invite's transaction (one ``commit``, below), so a
    rejected role or a duplicate email — both of which return before anything is
    added to the session — leaves the org exactly as it was. Not a capability
    check: gates live in routers, and ``account_type`` subtracts no capability
    anyway (see ``permissions.PERSONAL_DENIED``).
    """
    if role not in INVITABLE_ROLES:
        return {"error": f"Invalid role. Must be one of: {list(INVITABLE_ROLES)}"}

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

    # Read first so a second invite against an already-business org is a genuine
    # no-op rather than a redundant UPDATE.
    org = (
        await db.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if org is not None and org.account_type != "business":
        org.account_type = "business"

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
    account_type = await _account_type(db, org_id)
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
            # Sorted so the response is stable; ``frozenset`` is not JSON-serialisable.
            "permissions": sorted(str(c) for c in capabilities_for(u.role, account_type)),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


async def update_member_role(db: AsyncSession, org_id: UUID, user_id: UUID, new_role: str) -> dict:
    if new_role not in ROLES:
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


async def reset_invite_password(db: AsyncSession, org_id: UUID, user_id: UUID) -> dict:
    """Rotate an existing member's temporary password so their invite can be re-sent.

    An invite whose *email* failed still leaves a real ``User`` row behind, and
    :func:`invite_team_member` then refuses that address forever with "User with
    this email already exists". Without this, an invitee whose mail never went
    out is unreachable through the UI — exactly what happened when
    ``AGENTMAIL_API_KEY`` was missing in production: accounts were created, no
    mail was sent, and every retry 400'd.

    The password is rotated rather than reused. The original was handed to the
    inviter in an API response and a toast, so it may already sit in a log or a
    screenshot; a resend must not keep that one valid.
    """
    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == org_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return {"error": "User not found"}

    temp_password = str(uuid4())[:12]
    user.password_hash = _pwd_context.hash(temp_password)
    await db.commit()

    return {
        "status": "reset",
        "email": user.email,
        "role": user.role,
        "temp_password": temp_password,
        "user_id": str(user.id),
    }
