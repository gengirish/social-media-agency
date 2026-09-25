"""The capability matrix, and that ``require_cap`` fails closed.

Three things are worth testing here and nothing else is:

1. The matrix in ``permissions.CAPS`` says what the plan says it says. Written out
   longhand rather than derived from the code, so a typo in ``CAPS`` shows up as a
   failure instead of being copied into the assertion.
2. ``capabilities_for`` subtracts for ``personal`` and returns the empty set for
   anything it does not recognise.
3. ``require_cap`` denies a caller with no ``users`` row, a row in another org, or
   an inactive row. That is the whole security property — a fallback to the JWT's
   ``role`` claim would make all three pass while granting the access.

Plus a drift guard: the roles the database's CHECK constraint permits must be
exactly the roles the matrix has keys for. The two are edited in different files
by different people; without this they part company silently.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agency.permissions import (
    ACCOUNT_TYPES,
    CAPS,
    LEGACY_ROLE_MAP,
    PERSONAL_DENIED,
    ROLES,
    Capability,
    capabilities_for,
    normalize_role,
    require_cap,
    resolve_capabilities,
)
from tests.conftest import auth_header_for, create_org, create_user_row

# Built once at import: ruff's B008 rightly objects to a call in a parameter default,
# and FastAPI caches the dependency by identity anyway.
_PUBLISH_GATE = Depends(require_cap(Capability.PUBLISH_WRITE))

INIT_SQL = Path(__file__).resolve().parents[2] / "db" / "init.sql"

# The matrix from the plan, transcribed. Deliberately not built from CAPS.
EXPECTED_MATRIX: dict[str, set[str]] = {
    "owner": {
        "read",
        "campaign.run",
        "content.approve",
        "publish.write",
        "content.override",
        "oauth.connect",
        "team.manage",
        "billing.manage",
        "workspace.manage",
    },
    "admin": {
        "read",
        "campaign.run",
        "content.approve",
        "publish.write",
        "content.override",
        "oauth.connect",
        "team.manage",
        "workspace.manage",
    },
    "member": {"read", "campaign.run", "content.approve"},
    "viewer": {"read"},
}


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------
def test_caps_matches_the_matrix() -> None:
    assert {role: {str(c) for c in caps} for role, caps in CAPS.items()} == EXPECTED_MATRIX


def test_every_capability_appears_somewhere() -> None:
    """A capability no role holds is dead weight — or a row someone forgot."""
    granted = {cap for caps in CAPS.values() for cap in caps}
    assert granted == set(Capability)


def test_roles_are_ordered_by_strictly_shrinking_privilege() -> None:
    assert CAPS["viewer"] < CAPS["member"] < CAPS["admin"] < CAPS["owner"]


def test_roles_tuple_matches_caps_keys() -> None:
    assert set(ROLES) == set(CAPS)


# ---------------------------------------------------------------------------
# capabilities_for
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", list(EXPECTED_MATRIX))
def test_business_account_gets_the_full_row(role: str) -> None:
    assert capabilities_for(role, "business") == CAPS[role]


@pytest.mark.parametrize("role", list(EXPECTED_MATRIX))
def test_personal_account_loses_exactly_personal_denied(role: str) -> None:
    caps = capabilities_for(role, "personal")
    assert caps == CAPS[role] - PERSONAL_DENIED


@pytest.mark.parametrize("role", list(EXPECTED_MATRIX))
def test_account_type_does_not_change_capabilities(role: str) -> None:
    """The two axes are independent: ``account_type`` gates UI, not permission.

    ``PERSONAL_DENIED`` was ``{team.manage}`` until 260924, which deadlocked the
    account model — a personal org could not invite, and only an invite flips it
    to business. See the note on ``PERSONAL_DENIED``. If someone refills that set,
    this test is the one that should stop them and make them re-read it.
    """
    assert capabilities_for(role, "personal") == capabilities_for(role, "business")


def test_personal_owner_keeps_billing_and_seats() -> None:
    """A solo account pays for itself, and inviting a teammate IS the upgrade."""
    caps = capabilities_for("owner", "personal")
    assert Capability.BILLING_MANAGE in caps
    assert Capability.PUBLISH_WRITE in caps
    assert Capability.TEAM_MANAGE in caps


@pytest.mark.parametrize("legacy, modern", sorted(LEGACY_ROLE_MAP.items()))
def test_legacy_role_strings_map_onto_the_new_vocabulary(legacy: str, modern: str) -> None:
    assert normalize_role(legacy) == modern
    assert capabilities_for(legacy, "business") == CAPS[modern]


@pytest.mark.parametrize("role", ["", "root", "ADMIN", "superuser", "Owner"])
def test_unknown_role_gets_nothing(role: str) -> None:
    assert capabilities_for(role, "business") == frozenset()
    assert normalize_role(role) is None


def test_none_role_gets_nothing() -> None:
    assert normalize_role(None) is None


def test_unknown_account_type_is_treated_as_personal() -> None:
    """The narrower shape wins, so a malformed column subtracts rather than grants."""
    assert capabilities_for("owner", "") == capabilities_for("owner", "personal")
    assert capabilities_for("owner", "enterprise") == capabilities_for("owner", "personal")


def test_account_types_are_the_two_the_check_constraint_allows() -> None:
    assert set(ACCOUNT_TYPES) == {"personal", "business"}


# ---------------------------------------------------------------------------
# Drift guard: init.sql CHECK constraints vs. the Python vocabulary
# ---------------------------------------------------------------------------
def _check_constraint_values(column: str) -> set[str]:
    sql = INIT_SQL.read_text(encoding="utf-8")
    match = re.search(rf"CHECK \({column} IN \(([^)]*)\)\)", sql)
    assert match, f"no CHECK constraint on {column} in db/init.sql"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_init_sql_role_check_matches_caps_keys() -> None:
    assert _check_constraint_values("role") == set(CAPS)


def test_init_sql_account_type_check_matches_account_types() -> None:
    assert _check_constraint_values("account_type") == set(ACCOUNT_TYPES)


def test_legacy_roles_are_rejected_by_the_check_constraint() -> None:
    """The migration rewrites them; the constraint is what stops them returning."""
    assert not _check_constraint_values("role") & set(LEGACY_ROLE_MAP)


# ---------------------------------------------------------------------------
# require_cap — the fail-closed behaviour
# ---------------------------------------------------------------------------
async def _make_org(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    account_type: str,
    name: str = "Perm Org",
) -> UUID:
    """An org with an explicit ``account_type``.

    ``conftest.create_org`` does not take one yet (Phase 1C owns that file), so
    this patches the column after the row lands rather than editing the factory.
    """
    from agency.models.tables import Organization

    org_id = await create_org(session_factory, name)
    async with session_factory() as session:
        org = await session.get(Organization, org_id)
        assert org is not None
        org.account_type = account_type
        await session.commit()
    return org_id


async def _deactivate(
    session_factory: async_sessionmaker[AsyncSession], user_id: UUID
) -> None:
    from agency.models.tables import User

    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.is_active = False
        await session.commit()


def _fake_request() -> Any:
    """Enough of a ``Request`` for the ``request.state`` cache."""
    return SimpleNamespace(state=SimpleNamespace())


async def test_resolve_capabilities_reads_the_database_row(
    session_factory: async_sessionmaker[AsyncSession], db: AsyncSession
) -> None:
    org_id = await _make_org(session_factory, account_type="business")
    user_id = await create_user_row(session_factory, org_id, role="member")

    caps = await resolve_capabilities(_fake_request(), user_id, org_id, db)
    assert caps == CAPS["member"]


async def test_resolve_capabilities_is_empty_for_a_missing_user_row(
    session_factory: async_sessionmaker[AsyncSession], db: AsyncSession
) -> None:
    org_id = await _make_org(session_factory, account_type="business")

    caps = await resolve_capabilities(_fake_request(), uuid4(), org_id, db)
    assert caps == frozenset()


async def test_resolve_capabilities_is_empty_for_a_row_in_another_org(
    session_factory: async_sessionmaker[AsyncSession], db: AsyncSession
) -> None:
    org_a = await _make_org(session_factory, account_type="business", name="A")
    org_b = await _make_org(session_factory, account_type="business", name="B")
    user_id = await create_user_row(session_factory, org_a, role="owner")

    assert await resolve_capabilities(_fake_request(), user_id, org_b, db) == frozenset()


async def test_resolve_capabilities_is_empty_for_an_inactive_user(
    session_factory: async_sessionmaker[AsyncSession], db: AsyncSession
) -> None:
    org_id = await _make_org(session_factory, account_type="business")
    user_id = await create_user_row(session_factory, org_id, role="owner")
    await _deactivate(session_factory, user_id)

    assert await resolve_capabilities(_fake_request(), user_id, org_id, db) == frozenset()


async def test_resolve_capabilities_caches_on_request_state(
    session_factory: async_sessionmaker[AsyncSession], db: AsyncSession
) -> None:
    """One read per request: a role change mid-request must not be observed twice."""
    from agency.models.tables import User

    org_id = await _make_org(session_factory, account_type="business")
    user_id = await create_user_row(session_factory, org_id, role="viewer")
    request = _fake_request()

    first = await resolve_capabilities(request, user_id, org_id, db)
    assert first == CAPS["viewer"]

    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.role = "owner"
        await session.commit()

    assert await resolve_capabilities(request, user_id, org_id, db) is first
    # ...but a *new* request sees the promotion. The cache is per-request, never global.
    assert await resolve_capabilities(_fake_request(), user_id, org_id, db) == CAPS["owner"]


# ---------------------------------------------------------------------------
# require_cap end-to-end, on a throwaway app (no product route is gated yet)
# ---------------------------------------------------------------------------
@pytest.fixture
async def gated_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> Any:
    from agency.dependencies import get_db

    app = FastAPI()

    @app.get("/gated", dependencies=[_PUBLISH_GATE])
    async def _gated() -> dict[str, bool]:
        return {"ok": True}

    async def _override_db() -> Any:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_privileged_caller_is_admitted(
    gated_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    org_id = await _make_org(session_factory, account_type="business")
    user_id = await create_user_row(session_factory, org_id, role="admin")

    resp = await gated_client.get(
        "/gated", headers=auth_header_for(org_id, user_id=user_id)
    )
    assert resp.status_code == 200


async def test_under_privileged_caller_gets_the_documented_403(
    gated_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    org_id = await _make_org(session_factory, account_type="business")
    user_id = await create_user_row(session_factory, org_id, role="member")

    resp = await gated_client.get(
        "/gated", headers=auth_header_for(org_id, user_id=user_id)
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == {
        "code": "insufficient_permissions",
        "required": "publish.write",
    }


async def test_token_role_claim_cannot_grant_what_the_row_does_not(
    gated_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The stale-token case. The claim says owner; the database says viewer."""
    org_id = await _make_org(session_factory, account_type="business")
    user_id = await create_user_row(session_factory, org_id, role="viewer")

    resp = await gated_client.get(
        "/gated", headers=auth_header_for(org_id, role="owner", user_id=user_id)
    )
    assert resp.status_code == 403


async def test_no_user_row_is_403_not_200(
    gated_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A deleted user's unexpired token keeps nothing."""
    org_id = await _make_org(session_factory, account_type="business")

    resp = await gated_client.get(
        "/gated", headers=auth_header_for(org_id, role="owner", user_id=uuid4())
    )
    assert resp.status_code == 403
