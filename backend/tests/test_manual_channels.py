"""Manual channels — a page the operator posts to themselves, registered without OAuth.

Phase 1 of ``docs/manual-publish-plan-260929.md``. A manual channel is a
``platform_account`` row with ``status = 'manual'`` and **no tokens**.

The load-bearing property of that design, and the first test below, is negative:
a manual row must be invisible to every path that needs a real token. Eight
queries filter ``PlatformAccount.status``; exactly two were widened to include
``'manual'`` (``routers/setup.py::client_accounts`` and ``routers/clients.py``'s
overview count), both display-only. If a later edit widens
``routers/publishing.py`` by reflex, ``test_publish_now_ignores_a_manual_channel``
is what fails — and the alternative is a publisher selecting a row whose
``access_token_enc`` is ``NULL`` and posting nothing while reporting success.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from tests.conftest import (
    auth_for,
    create_client_row,
    create_content_row,
    create_org,
    create_platform_account,
    create_subscription,
)

API = "/api/v1"


@pytest.fixture
async def org(session_factory):
    org_id = await create_org(session_factory, "Manual Org", slug=f"manual-{uuid4().hex[:6]}")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org_id, "Manual Brand")
    headers = await auth_for(session_factory, org_id, "owner")
    return {"org_id": org_id, "client_id": client_id, "headers": headers}


def manual_url(client_id, account_id=None):
    base = f"{API}/setup/{client_id}/accounts/manual"
    return base if account_id is None else f"{base}/{account_id}"


# ---------------------------------------------------------------------------
# THE test of this phase: a tokenless row must never reach a publisher.
# ---------------------------------------------------------------------------
async def test_publish_now_ignores_a_manual_channel(client, session_factory, org):
    """A client whose only Instagram channel is manual still cannot be published to.

    ``publish_now``'s account lookup requires ``status == "connected"``. This asserts
    the refusal message, not just the status code, because a 400 for some other
    reason (an unapproved piece, say) would pass a status-only check while the real
    regression — a manual row being selected — went unnoticed.
    """
    await create_platform_account(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform="linkedin",
        status="manual",
    )
    content_id = await create_content_row(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform="linkedin",
        status="approved",
    )

    resp = await client.post(f"{API}/publishing/{content_id}/publish", headers=org["headers"])

    assert resp.status_code == 400, resp.text
    assert "no connected platform account" in resp.json()["detail"].lower()


async def test_publish_now_still_works_with_a_connected_account(client, session_factory, org):
    """The negative test above must not be passing for the wrong reason.

    With a *connected* account the lookup succeeds and the route gets as far as the
    publisher, which fails on a fake token — anything but 400 "no connected platform
    account". Without this, deleting the account lookup entirely would leave the
    test above green.
    """
    await create_platform_account(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform="linkedin",
        status="connected",
    )
    content_id = await create_content_row(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform="linkedin",
        status="approved",
    )

    resp = await client.post(f"{API}/publishing/{content_id}/publish", headers=org["headers"])

    body = resp.text.lower()
    assert "no connected platform account" not in body


# ---------------------------------------------------------------------------
# Registering
# ---------------------------------------------------------------------------
async def test_register_writes_a_manual_row_with_no_tokens(client, session_factory, org):
    from agency.models.tables import PlatformAccount

    resp = await client.post(
        manual_url(org["client_id"]),
        json={
            "platform": "instagram",
            "account_handle": "@ownpage",
            "profile_url": "https://www.instagram.com/ownpage",
        },
        headers=org["headers"],
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "manual"
    assert body["platform"] == "instagram"
    assert body["profile_url"] == "https://www.instagram.com/ownpage"

    async with session_factory() as session:
        row = await session.get(PlatformAccount, UUID(body["id"]))
        assert row is not None
        assert row.status == "manual"
        # The whole point: no token to publish with, and none to leak.
        assert row.access_token_enc is None
        assert row.refresh_token_enc is None


async def test_register_accepts_no_profile_url(client, org):
    resp = await client.post(
        manual_url(org["client_id"]),
        json={"platform": "tiktok", "account_handle": "ownstudio"},
        headers=org["headers"],
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["profile_url"] is None


async def test_register_rejects_an_unknown_platform(client, session_factory, org):
    from agency.models.tables import PlatformAccount

    resp = await client.post(
        manual_url(org["client_id"]),
        json={"platform": "myspace", "account_handle": "tom"},
        headers=org["headers"],
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unknown_platform"

    async with session_factory() as session:
        rows = await session.execute(
            select(PlatformAccount).where(PlatformAccount.org_id == org["org_id"])
        )
        assert rows.scalars().all() == []


@pytest.mark.parametrize(
    "bad_url",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "http://user:pw@example.com/page",
        "http://example.com:8080/page",
        "not a url at all",
    ],
)
async def test_register_rejects_an_unsafe_profile_url(client, session_factory, org, bad_url):
    """``profile_url`` is rendered as a link and opened in a new tab, so the scheme
    is checked before it is stored — ``services/url_safety.py::assert_safe_link``."""
    from agency.models.tables import PlatformAccount

    resp = await client.post(
        manual_url(org["client_id"]),
        json={"platform": "facebook", "account_handle": "page", "profile_url": bad_url},
        headers=org["headers"],
    )

    assert resp.status_code == 400, resp.text

    async with session_factory() as session:
        rows = await session.execute(
            select(PlatformAccount).where(PlatformAccount.org_id == org["org_id"])
        )
        assert rows.scalars().all() == []


# ---------------------------------------------------------------------------
# Display: the two widened filters
# ---------------------------------------------------------------------------
async def test_manual_row_appears_in_client_accounts(client, session_factory, org):
    await create_platform_account(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform="instagram",
        status="manual",
        account_handle="@ownpage",
        profile_url="https://www.instagram.com/ownpage",
    )

    resp = await client.get(f"{API}/setup/{org['client_id']}/accounts", headers=org["headers"])

    assert resp.status_code == 200, resp.text
    accounts = resp.json()["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["status"] == "manual"
    assert accounts[0]["profile_url"] == "https://www.instagram.com/ownpage"


async def test_disconnected_row_still_does_not_appear(client, session_factory, org):
    """The widening is to ``('connected', 'manual')`` exactly — not to everything."""
    await create_platform_account(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform="linkedin",
        status="disconnected",
    )

    resp = await client.get(f"{API}/setup/{org['client_id']}/accounts", headers=org["headers"])

    assert resp.status_code == 200
    assert resp.json()["accounts"] == []


async def test_manual_row_counts_in_clients_overview(client, session_factory, org):
    await create_platform_account(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform="instagram",
        status="manual",
    )

    resp = await client.get(f"{API}/clients/overview", headers=org["headers"])

    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json()["items"] if i["id"] == str(org["client_id"]))
    assert item["connected_accounts"] == 1


# ---------------------------------------------------------------------------
# PATCH / DELETE
# ---------------------------------------------------------------------------
async def test_patch_updates_handle_and_url(client, session_factory, org):
    account_id = await create_platform_account(
        session_factory, org["org_id"], org["client_id"], platform="facebook", status="manual"
    )

    resp = await client.patch(
        manual_url(org["client_id"], account_id),
        json={"account_handle": "renamed", "profile_url": "https://facebook.com/renamed"},
        headers=org["headers"],
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["account_handle"] == "renamed"
    assert resp.json()["profile_url"] == "https://facebook.com/renamed"


async def test_patch_only_writes_the_fields_it_was_sent(client, session_factory, org):
    account_id = await create_platform_account(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform="facebook",
        status="manual",
        account_handle="keepme",
    )

    resp = await client.patch(
        manual_url(org["client_id"], account_id),
        json={"profile_url": "https://facebook.com/keepme"},
        headers=org["headers"],
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["account_handle"] == "keepme"


async def test_patch_can_clear_the_url(client, session_factory, org):
    account_id = await create_platform_account(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform="facebook",
        status="manual",
        profile_url="https://facebook.com/old",
    )

    resp = await client.patch(
        manual_url(org["client_id"], account_id),
        json={"profile_url": None},
        headers=org["headers"],
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["profile_url"] is None


async def test_patch_rejects_an_unsafe_url(client, session_factory, org):
    from agency.models.tables import PlatformAccount

    account_id = await create_platform_account(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform="facebook",
        status="manual",
        profile_url="https://facebook.com/ok",
    )

    resp = await client.patch(
        manual_url(org["client_id"], account_id),
        json={"profile_url": "javascript:alert(1)"},
        headers=org["headers"],
    )

    assert resp.status_code == 400
    async with session_factory() as session:
        row = await session.get(PlatformAccount, account_id)
        assert row is not None
        assert row.profile_url == "https://facebook.com/ok"


async def test_delete_removes_the_manual_row(client, session_factory, org):
    from agency.models.tables import PlatformAccount

    account_id = await create_platform_account(
        session_factory, org["org_id"], org["client_id"], platform="tiktok", status="manual"
    )

    resp = await client.delete(manual_url(org["client_id"], account_id), headers=org["headers"])

    assert resp.status_code == 200, resp.text
    async with session_factory() as session:
        assert await session.get(PlatformAccount, account_id) is None


@pytest.mark.parametrize("method", ["patch", "delete"])
async def test_manual_routes_refuse_an_oauth_account(client, session_factory, org, method):
    """These routes touch manual rows only.

    Without the ``status == "manual"`` filter, DELETE would drop a connected
    account's row outright — leaving no trace of a live connection — and PATCH
    would rewrite the handle a publisher uses as the page id.
    """
    from agency.models.tables import PlatformAccount

    account_id = await create_platform_account(
        session_factory, org["org_id"], org["client_id"], platform="linkedin", status="connected"
    )
    url = manual_url(org["client_id"], account_id)

    if method == "patch":
        resp = await client.patch(
            url, json={"account_handle": "hijacked"}, headers=org["headers"]
        )
    else:
        resp = await client.delete(url, headers=org["headers"])

    assert resp.status_code == 404
    async with session_factory() as session:
        row = await session.get(PlatformAccount, account_id)
        assert row is not None
        assert row.status == "connected"
        assert row.access_token_enc == "enc-token"
