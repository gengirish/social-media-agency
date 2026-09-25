"""The team service speaks one role vocabulary — the one in ``agency.permissions``.

Two separate concerns are under test here:

1. **There is no second vocabulary.** ``services/team.py`` used to carry its own
   ``ROLE_PERMISSIONS`` map (``admin``/``manager``/``content_creator``/``viewer``)
   whose strings could drift from the ones a gate reads. The permissions the team
   list reports must now come from :func:`capabilities_for`, and a role the matrix
   does not know must report nothing rather than a plausible-looking default.
2. **An invite cannot mint a second owner.** The owner is established once, at
   provisioning; ``invite_team_member`` is not a path to a second one.

These are service-level tests on purpose. No ``require_cap`` gate exists on the
team router yet (Phase 2D adds it) and gates never live in services anyway, so
nothing here asserts a 403.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agency.permissions import ROLES, Capability, capabilities_for
from agency.services import team as team_service
from agency.services.team import (
    INVITABLE_ROLES,
    invite_team_member,
    list_team_members,
    update_member_role,
)

from .conftest import create_org, create_user_row


async def _org(
    session_factory: async_sessionmaker[AsyncSession], account_type: str = "business"
) -> UUID:
    """An org with an explicit ``account_type``.

    The column is set here rather than through ``create_org`` so this file does
    not depend on a factory signature Phase 1C is still changing.
    """
    from agency.models.tables import Organization

    org_id = await create_org(session_factory)
    async with session_factory() as session:
        org = await session.get(Organization, org_id)
        assert org is not None
        org.account_type = account_type
        await session.commit()
    return org_id


# ---------------------------------------------------------------------------
# One vocabulary
# ---------------------------------------------------------------------------
def test_no_second_role_map_on_the_module() -> None:
    """The old map is gone, not merely unused.

    Left in place it would keep answering ``ROLE_PERMISSIONS["manager"]`` with a
    confident-looking permission list for a role the database CHECK now rejects.
    """
    assert not hasattr(team_service, "ROLE_PERMISSIONS")
    assert not hasattr(team_service, "check_permission")


def test_invitable_roles_are_the_canonical_four_minus_owner() -> None:
    assert set(INVITABLE_ROLES) == set(ROLES) - {"owner"}


@pytest.mark.parametrize("role", ["member", "viewer", "admin"])
async def test_list_reports_capabilities_from_the_matrix(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
    role: str,
) -> None:
    org_id = await _org(session_factory, "business")
    await create_user_row(session_factory, org_id, role=role)

    members = await list_team_members(db, org_id)

    assert len(members) == 1
    expected = sorted(str(c) for c in capabilities_for(role, "business"))
    assert members[0]["permissions"] == expected
    assert members[0]["role"] == role


async def test_account_type_does_not_change_reported_permissions(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
) -> None:
    """A personal org's owner keeps ``team.manage`` — inviting IS the upgrade.

    Asserted the opposite until 260924, when emptying ``PERSONAL_DENIED`` broke
    the deadlock: ``account_type`` only flips to 'business' on a successful
    invite, so gating the invite on a capability that 'personal' subtracts left
    no way out of 'personal'.
    """
    business = await _org(session_factory, "business")
    personal = await _org(session_factory, "personal")
    await create_user_row(session_factory, business, role="owner")
    await create_user_row(session_factory, personal, role="owner")

    [on_business] = await list_team_members(db, business)
    [on_personal] = await list_team_members(db, personal)

    assert str(Capability.TEAM_MANAGE) in on_business["permissions"]
    assert str(Capability.TEAM_MANAGE) in on_personal["permissions"]
    assert on_personal["permissions"] == on_business["permissions"]


async def test_unknown_legacy_role_reports_no_capabilities(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
) -> None:
    """A row that escaped the migration fails closed, it does not guess.

    ``content_creator`` maps to ``member`` through ``LEGACY_ROLE_MAP``; a string
    outside the map entirely has no capabilities at all.
    """
    org_id = await _org(session_factory, "business")
    await create_user_row(session_factory, org_id, role="content_creator")
    await create_user_row(session_factory, org_id, role="wizard", email="wizard@test.com")

    by_role = {m["role"]: m["permissions"] for m in await list_team_members(db, org_id)}

    assert by_role["content_creator"] == sorted(
        str(c) for c in capabilities_for("member", "business")
    )
    assert by_role["wizard"] == []


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------
async def test_invite_rejects_owner(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
) -> None:
    """The whole point of the row: an invite must not create a second owner."""
    org_id = await _org(session_factory)

    result = await invite_team_member(db, org_id, "new@test.com", "owner", "me@test.com")

    assert "error" in result
    assert (await list_team_members(db, org_id)) == []


@pytest.mark.parametrize("role", ["manager", "content_creator", "", "superuser"])
async def test_invite_rejects_non_canonical_roles(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
    role: str,
) -> None:
    """Legacy strings included — they are what the database CHECK now rejects, so
    accepting one here would only move the failure to the INSERT."""
    org_id = await _org(session_factory)

    result = await invite_team_member(db, org_id, "new@test.com", role, "me@test.com")

    assert "error" in result
    assert (await list_team_members(db, org_id)) == []


@pytest.mark.parametrize("role", ["admin", "member", "viewer"])
async def test_invite_accepts_each_canonical_non_owner_role(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
    role: str,
) -> None:
    org_id = await _org(session_factory)

    result = await invite_team_member(db, org_id, f"{role}@test.com", role, "me@test.com")

    assert result.get("status") == "invited"
    assert result["role"] == role
    [member] = await list_team_members(db, org_id)
    assert member["role"] == role
    assert member["permissions"] == sorted(str(c) for c in capabilities_for(role, "business"))


# ---------------------------------------------------------------------------
# Role updates
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["manager", "content_creator", "nonsense"])
async def test_update_rejects_non_canonical_roles(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
    role: str,
) -> None:
    org_id = await _org(session_factory)
    user_id = await create_user_row(session_factory, org_id, role="member")

    result = await update_member_role(db, org_id, user_id, role)

    assert result == {"error": "Invalid role"}
    [member] = await list_team_members(db, org_id)
    assert member["role"] == "member"


async def test_update_accepts_a_canonical_role(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
) -> None:
    org_id = await _org(session_factory)
    user_id = await create_user_row(session_factory, org_id, role="viewer")

    result = await update_member_role(db, org_id, user_id, "admin")

    assert result == {"status": "updated", "role": "admin"}
    [member] = await list_team_members(db, org_id)
    assert member["role"] == "admin"


async def test_update_is_scoped_to_the_org(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
) -> None:
    """No RLS in this database — the service's own filter is the only one."""
    mine = await _org(session_factory)
    theirs = await _org(session_factory)
    victim = await create_user_row(session_factory, theirs, role="viewer")

    result = await update_member_role(db, mine, victim, "admin")

    assert result == {"error": "User not found"}
    [member] = await list_team_members(db, theirs)
    assert member["role"] == "viewer"


# ---------------------------------------------------------------------------
# Resend: the only route back from an invite whose email never arrived
# ---------------------------------------------------------------------------
async def test_resend_rotates_the_password_and_keeps_the_role(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
) -> None:
    """A resend must issue a *new* password, not re-serve the old one.

    The first password was handed to the inviter in an API response and a toast,
    so it may already be in a log or a screenshot. It must stop working.
    """
    from agency.models.tables import User

    org_id = await _org(session_factory)
    result = await invite_team_member(db, org_id, "stranded@test.com", "member", "boss@test.com")
    user_id = UUID(result["user_id"])
    original_hash = (await db.get(User, user_id)).password_hash

    resent = await team_service.reset_invite_password(db, org_id, user_id)

    assert resent["status"] == "reset"
    assert resent["email"] == "stranded@test.com"
    assert resent["role"] == "member"
    assert resent["temp_password"] != result["temp_password"]
    db.expire_all()
    assert (await db.get(User, user_id)).password_hash != original_hash


async def test_resend_is_scoped_to_the_org(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
) -> None:
    """No RLS in this database — this filter is the only thing stopping a
    cross-tenant password reset, which is strictly worse than a data read."""
    from agency.models.tables import User

    mine = await _org(session_factory)
    theirs = await _org(session_factory)
    victim = await create_user_row(session_factory, theirs, role="viewer")
    before = (await db.get(User, victim)).password_hash

    result = await team_service.reset_invite_password(db, mine, victim)

    assert result == {"error": "User not found"}
    db.expire_all()
    assert (await db.get(User, victim)).password_hash == before


async def test_resend_reaches_a_user_the_invite_route_now_refuses(
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
) -> None:
    """The bug this closes: re-inviting the same address is permanently rejected."""
    org_id = await _org(session_factory)
    first = await invite_team_member(db, org_id, "again@test.com", "member", "boss@test.com")

    retry = await invite_team_member(db, org_id, "again@test.com", "member", "boss@test.com")
    assert retry == {"error": "User with this email already exists"}

    resent = await team_service.reset_invite_password(db, org_id, UUID(first["user_id"]))
    assert resent.get("error") is None
    assert resent["temp_password"]
