"""Per-router tenant-isolation tests for the six routers fixed on 260817.

There is no row-level security in this database, so the ``org_id`` filter in each
router *is* the isolation boundary. Every test here is written to fail if its filter is
removed — that is the point of the file, and the reason each one asserts on a
cross-tenant identifier rather than just on a status code.

Companion to ``test_tenancy.py`` (clients / campaigns / content), which covers the paths
that were already scoped correctly.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from tests.conftest import (
    auth_header_for,
    create_client_row,
    create_content_row,
    create_notification_row,
    create_org,
    create_platform_account,
    create_subscription,
    create_user_row,
    create_white_label,
)

API = "/api/v1"


@pytest.fixture
async def orgs(session_factory):
    """Two orgs, each with a client, a content piece and a user."""
    org_a = await create_org(session_factory, "Org A", slug="org-a")
    org_b = await create_org(session_factory, "Org B", slug="org-b")

    await create_subscription(session_factory, org_a, plan_tier="growth", posts_limit=1000)
    await create_subscription(session_factory, org_b, plan_tier="growth", posts_limit=1000)

    client_a = await create_client_row(session_factory, org_a, "Brand A")
    client_b = await create_client_row(session_factory, org_b, "Brand B")

    user_a = await create_user_row(session_factory, org_a, full_name="Alice A")
    user_b = await create_user_row(session_factory, org_b, full_name="Bob B")

    content_a = await create_content_row(session_factory, org_a, client_a)
    content_b = await create_content_row(session_factory, org_b, client_b)

    return {
        "org_a": org_a,
        "org_b": org_b,
        "client_a": client_a,
        "client_b": client_b,
        "user_a": user_a,
        "user_b": user_b,
        "content_a": content_a,
        "content_b": content_b,
        "headers_a": auth_header_for(org_a, user_id=user_a),
        "headers_b": auth_header_for(org_b, user_id=user_b),
    }


# ---------------------------------------------------------------------------
# oauth — cross-tenant write. The worst of the six: a PlatformAccount bound to
# another tenant's client is what publishing.publish_now would then select.
# ---------------------------------------------------------------------------
async def test_oauth_callback_rejects_other_orgs_client(client, orgs, session_factory):
    from agency.models.tables import PlatformAccount

    resp = await client.post(
        f"{API}/oauth/twitter/callback",
        json={"code": "abc", "client_id": str(orgs["client_b"])},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 404

    # And nothing was written. A 404 that still persisted the row would be worthless.
    async with session_factory() as session:
        rows = await session.execute(
            select(PlatformAccount).where(PlatformAccount.client_id == orgs["client_b"])
        )
        assert rows.scalars().all() == []


async def test_oauth_callback_rejects_unknown_client(client, orgs):
    resp = await client.post(
        f"{API}/oauth/twitter/callback",
        json={"code": "abc", "client_id": str(uuid4())},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 404


async def test_oauth_callback_rejects_malformed_client_id(client, orgs):
    # Previously ``UUID(client_id_fk)`` raised straight out of the handler as a 500.
    resp = await client.post(
        f"{API}/oauth/twitter/callback",
        json={"code": "abc", "client_id": "not-a-uuid"},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# publishing — the other half of the chain above.
# ---------------------------------------------------------------------------
async def test_publish_ignores_other_orgs_platform_account(client, orgs, session_factory):
    """Org B holds an account row carrying org A's client id (the pre-fix attack shape).

    Org A's publish must not use it — it must report no connected account.
    """
    await create_platform_account(
        session_factory,
        orgs["org_b"],
        orgs["client_a"],
        platform="linkedin",
    )

    resp = await client.post(
        f"{API}/publishing/{orgs['content_a']}/publish",
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 400
    assert "no connected platform account" in resp.json()["detail"].lower()


async def test_publish_does_not_500_on_duplicate_accounts(client, orgs, session_factory):
    """Two matching rows used to hit ``scalar_one_or_none`` and 500 the route."""
    for handle in ("first", "second"):
        await create_platform_account(
            session_factory,
            orgs["org_b"],
            orgs["client_a"],
            platform="linkedin",
            account_handle=handle,
        )

    resp = await client.post(
        f"{API}/publishing/{orgs['content_a']}/publish",
        headers=orgs["headers_a"],
    )
    assert resp.status_code != 500


# ---------------------------------------------------------------------------
# comments — cross-tenant write against another org's content piece.
# ---------------------------------------------------------------------------
async def test_cannot_comment_on_other_orgs_content(client, orgs, session_factory):
    from agency.models.tables import ContentComment

    resp = await client.post(
        f"{API}/comments/content/{orgs['content_b']}",
        json={"body": "injected"},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 404

    async with session_factory() as session:
        rows = await session.execute(
            select(ContentComment).where(ContentComment.content_id == orgs["content_b"])
        )
        assert rows.scalars().all() == []


async def test_comment_on_own_content_succeeds(client, orgs):
    """Guards the fix from over-correcting into denying legitimate writes.

    Also covers the ``user.id``-on-a-dict bug: ``get_current_user`` returns the JWT
    payload in both auth modes, so attribute access here used to 500 unconditionally.
    """
    resp = await client.post(
        f"{API}/comments/content/{orgs['content_a']}",
        json={"body": "looks good"},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["user_id"] == str(orgs["user_a"])
    assert payload["user_name"] == "Alice A"


async def test_comment_list_excludes_other_orgs(client, orgs):
    await client.post(
        f"{API}/comments/content/{orgs['content_a']}",
        json={"body": "a-only"},
        headers=orgs["headers_a"],
    )
    resp = await client.get(
        f"{API}/comments/content/{orgs['content_a']}", headers=orgs["headers_b"]
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# notifications
# ---------------------------------------------------------------------------
async def test_cannot_mark_other_orgs_notification_read(client, orgs, session_factory):
    from agency.models.tables import Notification

    notif_b = await create_notification_row(session_factory, orgs["org_b"], orgs["user_b"])

    resp = await client.patch(
        f"{API}/notifications/{notif_b}/read", headers=orgs["headers_a"]
    )
    assert resp.status_code == 404

    async with session_factory() as session:
        row = await session.get(Notification, notif_b)
        assert row.read is False


async def test_notification_list_is_scoped_to_caller(client, orgs, session_factory):
    await create_notification_row(session_factory, orgs["org_a"], orgs["user_a"])
    await create_notification_row(session_factory, orgs["org_b"], orgs["user_b"])

    resp = await client.get(f"{API}/notifications", headers=orgs["headers_a"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["unread_count"] == 1


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------
async def test_cannot_list_report_periods_for_other_orgs_client(client, orgs):
    resp = await client.get(
        f"{API}/reports/clients/{orgs['client_b']}", headers=orgs["headers_a"]
    )
    assert resp.status_code == 404


async def test_report_periods_for_own_client(client, orgs):
    resp = await client.get(
        f"{API}/reports/clients/{orgs['client_a']}", headers=orgs["headers_a"]
    )
    assert resp.status_code == 200
    assert resp.json()["kind"] == "available_periods"


# ---------------------------------------------------------------------------
# portal — unauthenticated routes, so slug resolution is the whole boundary.
# ---------------------------------------------------------------------------
async def test_portal_resolves_on_slug_not_name(client, session_factory):
    """Two orgs sharing a ``name`` used to make ``scalar_one_or_none`` raise a 500.

    The name is now irrelevant: only the unique slug resolves.
    """
    org_a = await create_org(session_factory, "Shared Name", slug="tenant-a")
    org_b = await create_org(session_factory, "Shared Name", slug="tenant-b")
    await create_white_label(session_factory, org_a, company_name="Tenant A")
    await create_white_label(session_factory, org_b, company_name="Tenant B")

    client_a = await create_client_row(session_factory, org_a)
    await create_content_row(session_factory, org_a, client_a)

    resp = await client.get(f"{API}/portal/tenant-a/campaigns")
    assert resp.status_code == 200
    assert resp.json()["branding"]["company_name"] == "Tenant A"

    # The shared name resolves to nothing at all.
    assert (await client.get(f"{API}/portal/Shared Name/campaigns")).status_code == 404


async def test_portal_content_does_not_leak_across_orgs(client, session_factory):
    org_a = await create_org(session_factory, "Portal A", slug="portal-a")
    org_b = await create_org(session_factory, "Portal B", slug="portal-b")
    await create_white_label(session_factory, org_a)
    await create_white_label(session_factory, org_b)

    client_b = await create_client_row(session_factory, org_b)
    content_b = await create_content_row(session_factory, org_b, client_b)

    resp = await client.get(f"{API}/portal/portal-a/content")
    assert resp.status_code == 200
    assert str(content_b) not in {item["id"] for item in resp.json()["items"]}

    # And A's slug cannot mutate B's content.
    review = await client.patch(
        f"{API}/portal/portal-a/content/{content_b}", json={"decision": "approve"}
    )
    assert review.status_code == 404


async def test_portal_without_slug_is_unreachable(client, session_factory):
    """An org with no slug has no portal — the fail-closed default after the migration."""
    org = await create_org(session_factory, "No Slug Org", slug=None)
    await create_white_label(session_factory, org)

    assert (await client.get(f"{API}/portal/No Slug Org/campaigns")).status_code == 404
    assert (await client.get(f"{API}/portal/no-slug-org/campaigns")).status_code == 404


async def test_portal_requires_flag(client, session_factory):
    org = await create_org(session_factory, "Disabled Portal", slug="disabled-portal")
    await create_white_label(session_factory, org, portal_enabled=False)

    resp = await client.get(f"{API}/portal/disabled-portal/campaigns")
    assert resp.status_code == 403
