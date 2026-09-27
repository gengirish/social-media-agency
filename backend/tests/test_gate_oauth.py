"""Capability gates on ``routers/oauth.py`` — the highest-consequence gate in the set.

Connecting a social account is what makes real publishing to a live client account
possible: the ``PlatformAccount`` row written by the callback is exactly what
``services/publishing.py`` later selects. Before this gate, *any* authenticated user
in an org could create or destroy one. All three routes now require
``Capability.OAUTH_CONNECT`` — owner and admin only.

Every test here is written to fail when its ``dependencies=[_OAUTH_GATE]`` is deleted
from the decorator, which is why the denial cases assert on the 403 *body* and on the
absence of the side effect, not merely on a status code.
"""

from uuid import uuid4

import pytest

from tests.conftest import (
    auth_for,
    auth_header_for,
    create_client_row,
    create_org,
    create_platform_account,
)

API = "/api/v1"

#: The shape ``agency.permissions.forbidden`` raises. Asserted in full so a gate that
#: 403s for the wrong reason (a tenancy miss, say) cannot pass for a capability denial.
DENIED = {"code": "insufficient_permissions", "required": "oauth.connect"}

#: Roles the matrix denies ``oauth.connect``, and the ones it grants.
DENIED_ROLES = ["member", "viewer"]
ALLOWED_ROLES = ["owner", "admin"]


@pytest.fixture
async def org(session_factory):
    """One business org with one client — the shape every OAuth flow needs."""
    org_id = await create_org(session_factory, "Gate Org", slug=f"gate-{uuid4().hex[:6]}")
    client_id = await create_client_row(session_factory, org_id, "Gate Brand")
    return {"org_id": org_id, "client_id": client_id}


@pytest.fixture
def linkedin_configured(monkeypatch):
    """Give LinkedIn app credentials so ``authorize`` can reach a 200.

    ``get_settings`` is ``lru_cache``d, so the instance is a singleton and patching
    the attribute on it is enough. LinkedIn (not X) because X requires a PKCE
    ``code_challenge``, which would add a second failure mode to an authorization test.
    """
    from agency.routers.oauth import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "linkedin_client_id", "test-client-id")
    monkeypatch.setattr(settings, "linkedin_client_secret", "test-client-secret")
    return settings


# ---------------------------------------------------------------------------
# GET /oauth/{platform}/authorize
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", DENIED_ROLES)
async def test_authorize_denies_under_privileged_roles(
    client, session_factory, org, linkedin_configured, role
):
    headers = await auth_for(session_factory, org["org_id"], role)
    resp = await client.get(f"{API}/oauth/linkedin/authorize", headers=headers)

    assert resp.status_code == 403
    assert resp.json()["detail"] == DENIED


@pytest.mark.parametrize("role", ALLOWED_ROLES)
async def test_authorize_admits_privileged_roles(
    client, session_factory, org, linkedin_configured, role
):
    headers = await auth_for(session_factory, org["org_id"], role)
    resp = await client.get(
        f"{API}/oauth/linkedin/authorize",
        params={"client_id": str(org["client_id"])},
        headers=headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "linkedin"
    assert body["authorize_url"].startswith("https://www.linkedin.com/oauth/v2/authorization?")


async def test_authorize_denies_a_token_with_no_user_row(client, org, linkedin_configured):
    """The gate fails closed. ``auth_header_for`` mints a token whose ``sub`` has no row.

    Its ``role`` claim says ``owner``; the database says nothing at all. The database wins.
    """
    resp = await client.get(
        f"{API}/oauth/linkedin/authorize",
        headers=auth_header_for(org["org_id"], "owner"),
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == DENIED


async def test_authorize_denies_before_the_platform_check(client, session_factory, org):
    """A denied caller learns nothing about the route — not even which platforms exist.

    An unsupported platform is a 400 from the handler body; the gate is a route
    dependency, so it runs first and the member still gets 403.
    """
    headers = await auth_for(session_factory, org["org_id"], "member")
    resp = await client.get(f"{API}/oauth/nosuchplatform/authorize", headers=headers)

    assert resp.status_code == 403
    assert resp.json()["detail"] == DENIED


# ---------------------------------------------------------------------------
# POST /oauth/{platform}/callback — the route that writes the PlatformAccount
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", DENIED_ROLES)
async def test_callback_denies_under_privileged_roles(client, session_factory, org, role):
    from sqlalchemy import select

    from agency.models.tables import PlatformAccount

    headers = await auth_for(session_factory, org["org_id"], role)
    resp = await client.post(
        f"{API}/oauth/linkedin/callback",
        json={"code": "auth-code", "client_id": str(org["client_id"]), "state": "x"},
        headers=headers,
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == DENIED

    # No row was written. A 403 that still connected the account would be worthless.
    async with session_factory() as session:
        rows = await session.execute(
            select(PlatformAccount).where(PlatformAccount.org_id == org["org_id"])
        )
        assert rows.scalars().all() == []


@pytest.mark.parametrize("role", ALLOWED_ROLES)
async def test_callback_admits_privileged_roles(client, session_factory, org, role):
    """Past the gate, into the handler.

    The request omits ``code`` deliberately: a complete callback would have to reach
    the provider's token endpoint over the network. A 400 from the handler's own
    validation is proof the capability check let the caller through, which is all this
    file is testing — the exchange itself is covered elsewhere.
    """
    headers = await auth_for(session_factory, org["org_id"], role)
    resp = await client.post(
        f"{API}/oauth/linkedin/callback",
        json={"client_id": str(org["client_id"])},
        headers=headers,
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Authorization code required"


# ---------------------------------------------------------------------------
# DELETE /oauth/{platform}/{account_id}
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", DENIED_ROLES)
async def test_disconnect_denies_under_privileged_roles(client, session_factory, org, role):
    from agency.models.tables import PlatformAccount

    account_id = await create_platform_account(
        session_factory, org["org_id"], org["client_id"], platform="linkedin"
    )
    headers = await auth_for(session_factory, org["org_id"], role)

    resp = await client.delete(f"{API}/oauth/linkedin/{account_id}", headers=headers)

    assert resp.status_code == 403
    assert resp.json()["detail"] == DENIED

    # Still connected, tokens intact — the denial had no side effect.
    async with session_factory() as session:
        account = await session.get(PlatformAccount, account_id)
        assert account is not None
        assert account.status == "connected"
        assert account.access_token_enc == "enc-token"


@pytest.mark.parametrize("role", ALLOWED_ROLES)
async def test_disconnect_admits_privileged_roles(client, session_factory, org, role):
    from agency.models.tables import PlatformAccount

    account_id = await create_platform_account(
        session_factory, org["org_id"], org["client_id"], platform="linkedin"
    )
    headers = await auth_for(session_factory, org["org_id"], role)

    resp = await client.delete(f"{API}/oauth/linkedin/{account_id}", headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {"status": "disconnected", "platform": "linkedin"}

    async with session_factory() as session:
        account = await session.get(PlatformAccount, account_id)
        assert account is not None
        assert account.status == "disconnected"
        assert account.access_token_enc is None


# ---------------------------------------------------------------------------
# account_type is not a permission axis — see permissions.PERSONAL_DENIED.
# ---------------------------------------------------------------------------
async def test_personal_account_owner_may_still_connect(
    client, session_factory, org, linkedin_configured
):
    """A solo creator connects their own accounts.

    ``PERSONAL_DENIED`` is empty by decision (filling it deadlocked the account model),
    so ``account_type`` changes UI affordances and nothing about capabilities. Pinned
    here so a personal org's owner cannot be locked out of publishing by a later edit.
    """
    headers = await auth_for(session_factory, org["org_id"], "owner", account_type="personal")
    resp = await client.get(
        f"{API}/oauth/linkedin/authorize",
        params={"client_id": str(org["client_id"])},
        headers=headers,
    )

    assert resp.status_code == 200


async def test_personal_account_viewer_is_still_denied(client, session_factory, org):
    headers = await auth_for(session_factory, org["org_id"], "viewer", account_type="personal")
    resp = await client.get(f"{API}/oauth/linkedin/authorize", headers=headers)

    assert resp.status_code == 403
    assert resp.json()["detail"] == DENIED
