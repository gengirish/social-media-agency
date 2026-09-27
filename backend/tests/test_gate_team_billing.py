"""Phase 2D gates: team management, billing, and the B2C → B2B account flip.

Three things are under test, and they are not independent:

1. **`team.manage` on the two team write routes.** Before this, *any*
   authenticated user in an org could `PATCH /team/{user_id}/role` and promote
   themselves to admin. That was the hole.
2. **`billing.manage` on checkout — owner only.** `admin` holds `team.manage`
   but not `billing.manage`; the admin row is the one that proves the matrix is
   actually consulted rather than a coarse "is staff" check. `POST
   /billing/webhook` stays ungated: Stripe authenticates with a signature and
   sends no user, so a gate there would strand every subscription change.
3. **The account-type flip.** A new org is `personal`; the first successful
   invite makes it `business`, one way, in the invite's own transaction. The
   round trip is asserted end-to-end in
   :func:`test_personal_org_owner_invites_and_org_becomes_business` — it is the
   proof that the deadlock of §1 of the phase plan (`PERSONAL_DENIED` holding
   `team.manage`, so a personal org could never invite and so never become a
   business one) is gone.

Every caller here comes from ``auth_for``, which persists a real ``users`` row —
``require_cap`` reads the role from the database and fails closed, so a token
minted by ``auth_header_for`` alone cannot pass any of these gates.
"""

from __future__ import annotations

import types
from typing import Any
from uuid import UUID, uuid4

import pytest
import stripe
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agency.models.tables import Organization, User
from agency.permissions import Capability

from .conftest import auth_for, create_org, create_subscription, create_user_row

UNPRIVILEGED = ["member", "viewer"]


async def _account_type(
    session_factory: async_sessionmaker[AsyncSession], org_id: UUID
) -> str:
    async with session_factory() as session:
        org = await session.get(Organization, org_id)
        assert org is not None
        return org.account_type


async def _invited_exists(
    session_factory: async_sessionmaker[AsyncSession], email: str
) -> bool:
    from sqlalchemy import select

    async with session_factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none() is not None


async def _role_of(
    session_factory: async_sessionmaker[AsyncSession], user_id: UUID
) -> str:
    async with session_factory() as session:
        row = await session.get(User, user_id)
        assert row is not None
        return row.role


def _assert_forbidden(response: Any, cap: Capability) -> None:
    """A 403 from ``require_cap`` has exactly one shape."""
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == {
        "code": "insufficient_permissions",
        "required": str(cap),
    }


# ---------------------------------------------------------------------------
# POST /team/invite  →  team.manage
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", UNPRIVILEGED)
async def test_invite_is_forbidden_without_team_manage(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    role: str,
) -> None:
    org_id = await create_org(session_factory)
    headers = await auth_for(session_factory, org_id, role)

    response = await client.post(
        "/api/v1/team/invite",
        json={"email": "new@test.com", "role": "member"},
        headers=headers,
    )

    _assert_forbidden(response, Capability.TEAM_MANAGE)
    # The gate ran before the handler: no user row was created.
    assert not await _invited_exists(session_factory, "new@test.com")


@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_invite_succeeds_with_team_manage(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    role: str,
) -> None:
    """Both rows that hold ``team.manage`` can invite — admin included."""
    org_id = await create_org(session_factory)
    headers = await auth_for(session_factory, org_id, role)

    response = await client.post(
        "/api/v1/team/invite",
        json={"email": f"invited-by-{role}@test.com", "role": "member"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "user_created"
    assert await _invited_exists(session_factory, f"invited-by-{role}@test.com")


# ---------------------------------------------------------------------------
# PATCH /team/{user_id}/role  →  team.manage
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", UNPRIVILEGED)
async def test_role_update_is_forbidden_without_team_manage(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    role: str,
) -> None:
    """The hole this phase closes, stated directly.

    The caller is targeting *another* user here, so nothing but the capability
    gate can reject it — the self-promotion block below is a separate rule.
    """
    org_id = await create_org(session_factory)
    headers = await auth_for(session_factory, org_id, role)
    victim = await create_user_row(session_factory, org_id, role="viewer")

    response = await client.patch(
        f"/api/v1/team/{victim}/role", json={"role": "admin"}, headers=headers
    )

    _assert_forbidden(response, Capability.TEAM_MANAGE)
    assert await _role_of(session_factory, victim) == "viewer"


async def test_member_cannot_promote_themselves(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The exact escalation that was possible before Phase 2D.

    Two headers, one person: ``auth_for`` is asked for the same ``user_id`` so
    the row the gate loads is the row being targeted.
    """
    org_id = await create_org(session_factory)
    me = uuid4()
    headers = await auth_for(session_factory, org_id, "member", user_id=me)

    response = await client.patch(
        f"/api/v1/team/{me}/role", json={"role": "admin"}, headers=headers
    )

    # Capability first — a member never reaches the self-promotion block.
    _assert_forbidden(response, Capability.TEAM_MANAGE)
    assert await _role_of(session_factory, me) == "member"


@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_role_update_succeeds_with_team_manage(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    role: str,
) -> None:
    org_id = await create_org(session_factory)
    headers = await auth_for(session_factory, org_id, role)
    target = await create_user_row(session_factory, org_id, role="viewer")

    response = await client.patch(
        f"/api/v1/team/{target}/role", json={"role": "member"}, headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "updated", "role": "member"}
    assert await _role_of(session_factory, target) == "member"


# ---------------------------------------------------------------------------
# The two router-level blocks
# ---------------------------------------------------------------------------
async def test_owner_cannot_change_their_own_role(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Holding ``team.manage`` is not permission to edit your own seat.

    Without this, an admin self-promotes to owner and an owner demotes the only
    owner an org has.
    """
    org_id = await create_org(session_factory)
    me = uuid4()
    headers = await auth_for(session_factory, org_id, "owner", user_id=me)

    response = await client.patch(
        f"/api/v1/team/{me}/role", json={"role": "member"}, headers=headers
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == {"code": "cannot_change_own_role"}
    assert await _role_of(session_factory, me) == "owner"


async def test_admin_cannot_self_promote_to_owner(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    org_id = await create_org(session_factory)
    me = uuid4()
    headers = await auth_for(session_factory, org_id, "admin", user_id=me)

    response = await client.patch(
        f"/api/v1/team/{me}/role", json={"role": "owner"}, headers=headers
    )

    assert response.status_code == 403, response.text
    assert await _role_of(session_factory, me) == "admin"


@pytest.mark.parametrize("caller_role", ["owner", "admin"])
async def test_no_update_may_assign_owner(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    caller_role: str,
) -> None:
    """An org has one owner. A transfer is a different operation than an update.

    The service layer stays permissive on purpose (Phase 1B) so a real transfer
    remains expressible; the block is the router's.
    """
    org_id = await create_org(session_factory)
    headers = await auth_for(session_factory, org_id, caller_role)
    target = await create_user_row(session_factory, org_id, role="member")

    response = await client.patch(
        f"/api/v1/team/{target}/role", json={"role": "owner"}, headers=headers
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == {"code": "cannot_assign_owner"}
    assert await _role_of(session_factory, target) == "member"


# ---------------------------------------------------------------------------
# POST /billing/checkout  →  billing.manage  (owner only)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["admin", "member", "viewer"])
async def test_checkout_is_forbidden_without_billing_manage(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    role: str,
) -> None:
    """``admin`` is the interesting row: it manages the team but not the money."""
    org_id = await create_org(session_factory)
    headers = await auth_for(session_factory, org_id, role)

    response = await client.post(
        "/api/v1/billing/checkout", json={"plan_tier": "growth"}, headers=headers
    )

    _assert_forbidden(response, Capability.BILLING_MANAGE)


async def test_owner_can_start_checkout(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stripe is stubbed — what is asserted is that the request reaches it."""
    org_id = await create_org(session_factory, "Payer")
    await create_subscription(session_factory, org_id, plan_tier="free")
    headers = await auth_for(session_factory, org_id, "owner")

    monkeypatch.setattr(
        stripe.Customer,
        "create",
        lambda **kwargs: types.SimpleNamespace(id="cus_test"),
    )
    monkeypatch.setattr(
        stripe.checkout.Session,
        "create",
        lambda **kwargs: types.SimpleNamespace(
            id="cs_test", url="https://stripe.test/checkout/cs_test"
        ),
    )

    response = await client.post(
        "/api/v1/billing/checkout", json={"plan_tier": "growth"}, headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["checkout_url"] == "https://stripe.test/checkout/cs_test"


# ---------------------------------------------------------------------------
# POST /billing/webhook  →  ungated, on purpose
# ---------------------------------------------------------------------------
async def test_stripe_webhook_works_with_no_user_at_all(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Authorization header, no org on the request — and it must still land.

    Stripe does not send a bearer token; it signs the body. Gating this route
    would 403 every callback and silently strand every subscription change, so
    the test sends nothing but a signature header.
    """
    from agency.config import get_settings
    from agency.routers import billing as billing_router
    from agency.services.billing import PLAN_CONFIG

    org_id = await create_org(session_factory, "Webhooked")
    await create_subscription(session_factory, org_id, plan_tier="free")

    settings = get_settings()
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test", raising=False)
    monkeypatch.setattr(billing_router, "get_settings", lambda: settings)
    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        lambda payload, sig, secret: {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"org_id": str(org_id), "plan_tier": "growth"},
                    "subscription": "sub_hook",
                    "customer": "cus_hook",
                }
            },
        },
    )

    response = await client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=deadbeef"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "activated"

    from sqlalchemy import select

    from agency.models.tables import Subscription

    async with session_factory() as session:
        sub = (
            await session.execute(
                select(Subscription).where(Subscription.org_id == org_id)
            )
        ).scalar_one()
        assert sub.plan_tier == "growth"
        assert sub.clients_limit == PLAN_CONFIG["growth"]["clients_limit"]


# ---------------------------------------------------------------------------
# The account-type flip — the round trip
# ---------------------------------------------------------------------------
async def test_personal_org_owner_invites_and_org_becomes_business(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """THE ROUND TRIP. A solo account hires someone and is now an agency.

    This is the proof the §1 deadlock is gone. It only passes because
    ``PERSONAL_DENIED`` is empty: a personal org's owner keeps ``team.manage``,
    so the invite gate admits them, and the invite itself performs the upgrade.
    If someone refills ``PERSONAL_DENIED`` with ``team.manage``, this test goes
    red at the 403 and tells them exactly why.
    """
    org_id = await create_org(session_factory, "Solo Creator", account_type="personal")
    headers = await auth_for(session_factory, org_id, "owner")
    assert await _account_type(session_factory, org_id) == "personal"

    response = await client.post(
        "/api/v1/team/invite",
        json={"email": "first-hire@test.com", "role": "member"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "user_created"
    assert await _invited_exists(session_factory, "first-hire@test.com")
    assert await _account_type(session_factory, org_id) == "business"


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"email": "taken@test.com", "role": "member"}, "duplicate email"),
        ({"email": "fresh@test.com", "role": "owner"}, "invite cannot mint an owner"),
        ({"email": "fresh@test.com", "role": "manager"}, "legacy role string"),
    ],
)
async def test_failed_invite_leaves_the_org_personal(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    payload: dict[str, str],
    reason: str,
) -> None:
    """The flip shares the invite's transaction, so a rejected invite changes nothing."""
    org_id = await create_org(session_factory, "Still Solo", account_type="personal")
    headers = await auth_for(session_factory, org_id, "owner")
    await create_user_row(session_factory, org_id, email="taken@test.com", role="member")

    response = await client.post("/api/v1/team/invite", json=payload, headers=headers)

    assert response.status_code == 400, f"{reason}: {response.text}"
    assert await _account_type(session_factory, org_id) == "personal"


async def test_second_invite_against_a_business_org_is_a_no_op(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Already business: the invite still succeeds and the column does not move.

    One way — nothing in the flip ever writes ``personal`` back.
    """
    org_id = await create_org(session_factory, "Agency", account_type="business")
    headers = await auth_for(session_factory, org_id, "owner")

    for email in ("hire-one@test.com", "hire-two@test.com"):
        response = await client.post(
            "/api/v1/team/invite",
            json={"email": email, "role": "member"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert await _account_type(session_factory, org_id) == "business"


async def test_invite_by_an_admin_also_flips_the_account_type(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The flip belongs to the invite, not to the owner seat."""
    org_id = await create_org(session_factory, "Solo With Admin", account_type="personal")
    headers = await auth_for(session_factory, org_id, "admin")

    response = await client.post(
        "/api/v1/team/invite",
        json={"email": "hired@test.com", "role": "viewer"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert await _account_type(session_factory, org_id) == "business"
