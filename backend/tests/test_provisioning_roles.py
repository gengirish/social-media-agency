"""Both provisioning paths, and what ``GET /auth/me`` tells the frontend.

There are two places an org is born — ``POST /auth/signup`` (local HS256) and
``_resolve_clerk_user`` (Clerk/production). Both used to hardcode ``role="admin"``
and neither created a client. If they ever drift apart again the two auth modes
disagree about who owns an org, so every assertion below is made against both.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import auth_header_for, create_org, create_user_row

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
async def _set_account_type(
    session_factory: async_sessionmaker[AsyncSession], org_id: UUID, value: str
) -> None:
    """Set ``organization.account_type`` without depending on the row factory's
    signature — ``conftest.create_org`` belongs to another phase."""
    from agency.models.tables import Organization

    async with session_factory() as session:
        await session.execute(
            update(Organization).where(Organization.id == org_id).values(account_type=value)
        )
        await session.commit()


async def _org_row(session_factory: async_sessionmaker[AsyncSession], org_id: UUID) -> Any:
    from agency.models.tables import Organization

    async with session_factory() as session:
        result = await session.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one()


async def _clients_for(
    session_factory: async_sessionmaker[AsyncSession], org_id: UUID
) -> list[Any]:
    from agency.models.tables import Client

    async with session_factory() as session:
        result = await session.execute(select(Client).where(Client.org_id == org_id))
        return list(result.scalars().all())


def _clerk_settings(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "clerk_secret_key": "sk_test",
        "clerk_jwks_url": "https://clerk.test/jwks",
        "demo_org_id": "",
        "demo_org_allowlist": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _clerk_info(email: str, first: str = "Ada", last: str = "Lovelace") -> dict[str, Any]:
    return {
        "email_addresses": [{"id": "eml_1", "email_address": email}],
        "primary_email_address_id": "eml_1",
        "first_name": first,
        "last_name": last,
    }


async def _resolve(
    monkeypatch: pytest.MonkeyPatch, email: str, settings: Any, **info: Any
) -> dict[str, Any]:
    import agency.dependencies as deps

    async def _fake_info(clerk_user_id: str, secret_key: str) -> dict[str, Any]:
        return _clerk_info(email, **info)

    monkeypatch.setattr(deps, "_get_clerk_user_info", _fake_info)
    return await deps._resolve_clerk_user({"sub": "user_clerk_1"}, settings)


# ---------------------------------------------------------------------------
# path 1 — POST /auth/signup
# ---------------------------------------------------------------------------
async def test_signup_first_user_is_owner_of_a_personal_org_with_one_client(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from agency.models.tables import Subscription, User

    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "founder@example.com",
            "password": "hunter2hunter2",
            "full_name": "Founder Person",
            "org_name": "Acme Studio",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "owner"
    org_id = UUID(body["org_id"])

    async with session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == "founder@example.com"))
        ).scalar_one()
        assert user.role == "owner"
        assert user.org_id == org_id
        sub = (
            await session.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        assert sub.plan_tier == "free"

    org = await _org_row(session_factory, org_id)
    assert org.account_type == "personal"

    clients = await _clients_for(session_factory, org_id)
    assert len(clients) == 1
    assert clients[0].brand_name == "Acme Studio"


async def test_signup_rejects_duplicate_email_without_creating_a_second_org(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from agency.models.tables import Organization

    payload = {
        "email": "dupe@example.com",
        "password": "hunter2hunter2",
        "full_name": "Dupe Person",
        "org_name": "Dupe Org",
    }
    first = await client.post("/api/v1/auth/signup", json=payload)
    assert first.status_code == 201
    second = await client.post("/api/v1/auth/signup", json=payload)
    assert second.status_code == 409

    async with session_factory() as session:
        orgs = (
            (await session.execute(select(Organization).where(Organization.name == "Dupe Org")))
            .scalars()
            .all()
        )
    assert len(orgs) == 1


# ---------------------------------------------------------------------------
# path 2 — Clerk auto-provisioning
# ---------------------------------------------------------------------------
async def test_clerk_new_user_is_owner_of_a_personal_org_with_one_client(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    from agency.models.tables import Subscription

    payload = await _resolve(monkeypatch, "ada@example.com", _clerk_settings())

    assert payload["role"] == "owner"
    assert payload["email"] == "ada@example.com"
    org_id = UUID(payload["org_id"])

    org = await _org_row(session_factory, org_id)
    assert org.account_type == "personal"
    assert org.name == "Ada Lovelace" + "'s Org"

    clients = await _clients_for(session_factory, org_id)
    assert len(clients) == 1
    assert clients[0].brand_name == "Ada Lovelace"

    async with session_factory() as session:
        sub = (
            await session.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        assert sub.plan_tier == "free"


async def test_clerk_resolver_matches_on_email_so_an_invited_user_keeps_their_role(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user invited through the team service already has a row and a role.

    The resolver looks the row up by email before provisioning, so signing in
    through Clerk must neither mint a second org nor promote them to owner.
    """
    from agency.models.tables import Organization

    org_id = await create_org(session_factory, name="Existing Agency")
    user_id = await create_user_row(
        session_factory, org_id, email="invited@example.com", role="member"
    )

    payload = await _resolve(monkeypatch, "invited@example.com", _clerk_settings())

    assert payload["role"] == "member"
    assert payload["org_id"] == str(org_id)
    assert payload["sub"] == str(user_id)

    async with session_factory() as session:
        orgs = (await session.execute(select(Organization))).scalars().all()
    assert len(orgs) == 1  # nothing was provisioned
    assert await _clients_for(session_factory, org_id) == []


async def test_clerk_demo_allowlist_user_joins_the_demo_org_as_admin(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The demo path keeps ``admin``: those users join an org that has an owner."""
    from agency.models.tables import Organization

    demo_org_id = await create_org(session_factory, name="Demo Org")
    settings = _clerk_settings(
        demo_org_id=str(demo_org_id), demo_org_allowlist="Demo@Example.com , other@x.com"
    )

    payload = await _resolve(monkeypatch, "demo@example.com", settings)

    assert payload["role"] == "admin"
    assert payload["org_id"] == str(demo_org_id)

    async with session_factory() as session:
        orgs = (await session.execute(select(Organization))).scalars().all()
    assert len(orgs) == 1
    assert await _clients_for(session_factory, demo_org_id) == []


async def test_clerk_demo_org_id_that_does_not_exist_falls_back_to_a_new_owner_org(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _clerk_settings(demo_org_id=str(uuid4()), demo_org_allowlist="ghost@example.com")

    payload = await _resolve(monkeypatch, "ghost@example.com", settings)

    assert payload["role"] == "owner"
    org = await _org_row(session_factory, UUID(payload["org_id"]))
    assert org.account_type == "personal"


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("role", "account_type", "expected"),
    [
        (
            "owner",
            "business",
            [
                "billing.manage",
                "campaign.run",
                "content.approve",
                "content.override",
                "oauth.connect",
                "publish.write",
                "read",
                "team.manage",
            ],
        ),
        (
            "owner",
            "personal",
            [
                "billing.manage",
                "campaign.run",
                "content.approve",
                "content.override",
                "oauth.connect",
                "publish.write",
                "read",
                "team.manage",
            ],
        ),
        (
            "admin",
            "business",
            [
                "campaign.run",
                "content.approve",
                "content.override",
                "oauth.connect",
                "publish.write",
                "read",
                "team.manage",
            ],
        ),
        (
            "admin",
            "personal",
            [
                "campaign.run",
                "content.approve",
                "content.override",
                "oauth.connect",
                "publish.write",
                "read",
                "team.manage",
            ],
        ),
        ("member", "business", ["campaign.run", "content.approve", "read"]),
        ("member", "personal", ["campaign.run", "content.approve", "read"]),
        ("viewer", "business", ["read"]),
        ("viewer", "personal", ["read"]),
    ],
)
async def test_me_returns_the_capability_set_for_each_role_and_account_type(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    role: str,
    account_type: str,
    expected: list[str],
) -> None:
    org_id = await create_org(session_factory, name=f"Org {role} {account_type}")
    await _set_account_type(session_factory, org_id, account_type)
    user_id = await create_user_row(
        session_factory,
        org_id,
        email=f"{role}-{account_type}-{uuid4().hex[:6]}@test.com",
        role=role,
    )

    resp = await client.get(
        "/api/v1/auth/me", headers=auth_header_for(org_id, role=role, user_id=user_id)
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == str(user_id)
    assert body["org_id"] == str(org_id)
    assert body["role"] == role
    assert body["account_type"] == account_type
    assert body["capabilities"] == expected
    assert set(body) == {
        "user_id",
        "email",
        "role",
        "org_id",
        "account_type",
        "capabilities",
    }


async def test_me_is_reachable_by_a_viewer(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """No capability gate on ``/auth/me`` — a client that cannot read its own
    permissions cannot render anything."""
    org_id = await create_org(session_factory, name="Viewer Org")
    user_id = await create_user_row(
        session_factory, org_id, email="viewer-only@test.com", role="viewer"
    )

    resp = await client.get(
        "/api/v1/auth/me", headers=auth_header_for(org_id, role="viewer", user_id=user_id)
    )
    assert resp.status_code == 200
    assert resp.json()["capabilities"] == ["read"]


async def test_me_normalizes_a_legacy_role_string(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    org_id = await create_org(session_factory, name="Legacy Org")
    await _set_account_type(session_factory, org_id, "business")
    user_id = await create_user_row(
        session_factory, org_id, email="legacy@test.com", role="content_creator"
    )

    resp = await client.get("/api/v1/auth/me", headers=auth_header_for(org_id, user_id=user_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "member"
    assert body["capabilities"] == ["campaign.run", "content.approve", "read"]


async def test_me_ignores_the_token_role_claim_and_reads_the_database(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A demotion must take effect before the token expires."""
    org_id = await create_org(session_factory, name="Stale Token Org")
    user_id = await create_user_row(
        session_factory, org_id, email="demoted@test.com", role="viewer"
    )

    resp = await client.get(
        "/api/v1/auth/me",
        headers=auth_header_for(org_id, role="owner", user_id=user_id),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "viewer"
    assert resp.json()["capabilities"] == ["read"]


async def test_me_404s_for_a_user_row_in_another_org(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """There is no row-level security here: the row must match id *and* org."""
    org_id = await create_org(session_factory, name="Home Org")
    other_org_id = await create_org(session_factory, name="Other Org")
    user_id = await create_user_row(
        session_factory, org_id, email="crosstenant@test.com", role="owner"
    )

    resp = await client.get(
        "/api/v1/auth/me", headers=auth_header_for(other_org_id, user_id=user_id)
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "user_not_found"


async def test_me_404s_when_there_is_no_user_row(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    org_id = await create_org(session_factory, name="Empty Org")

    resp = await client.get("/api/v1/auth/me", headers=auth_header_for(org_id))
    assert resp.status_code == 404


async def test_me_404s_for_a_deactivated_user(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from agency.models.tables import User

    org_id = await create_org(session_factory, name="Deactivated Org")
    user_id = await create_user_row(session_factory, org_id, email="gone@test.com", role="owner")
    async with session_factory() as session:
        await session.execute(update(User).where(User.id == user_id).values(is_active=False))
        await session.commit()

    resp = await client.get("/api/v1/auth/me", headers=auth_header_for(org_id, user_id=user_id))
    assert resp.status_code == 404


async def test_me_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)
