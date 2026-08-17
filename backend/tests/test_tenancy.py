"""Tenant-isolation tests — the critical multi-tenant safety net.

Org A must never be able to read or mutate Org B's clients, campaigns, or
content. Cross-tenant access must resolve to 404/empty (never leak data),
regardless of the HTTP verb.
"""

import pytest

from tests.conftest import (
    auth_header_for,
    create_campaign_row,
    create_client_row,
    create_content_row,
    create_org,
    create_subscription,
)

API = "/api/v1"


@pytest.fixture
async def two_orgs(session_factory):
    """Two fully populated orgs. Returns a dict of ids + auth headers."""
    org_a = await create_org(session_factory, "Org A")
    org_b = await create_org(session_factory, "Org B")

    await create_subscription(session_factory, org_a, plan_tier="growth", posts_limit=1000)
    await create_subscription(session_factory, org_b, plan_tier="growth", posts_limit=1000)

    client_a = await create_client_row(session_factory, org_a, "Brand A")
    client_b = await create_client_row(session_factory, org_b, "Brand B")

    camp_a = await create_campaign_row(session_factory, org_a, client_a, "Campaign A")
    camp_b = await create_campaign_row(session_factory, org_b, client_b, "Campaign B")

    content_a = await create_content_row(session_factory, org_a, client_a, camp_a)
    content_b = await create_content_row(session_factory, org_b, client_b, camp_b)

    return {
        "org_a": org_a,
        "org_b": org_b,
        "headers_a": auth_header_for(org_a),
        "client_a": client_a,
        "client_b": client_b,
        "camp_a": camp_a,
        "camp_b": camp_b,
        "content_a": content_a,
        "content_b": content_b,
    }


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
async def test_client_list_only_returns_own_org(client, two_orgs):
    resp = await client.get(f"{API}/clients", headers=two_orgs["headers_a"])
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data["items"]}
    assert str(two_orgs["client_a"]) in ids
    assert str(two_orgs["client_b"]) not in ids
    assert data["total"] == 1


async def test_cannot_read_other_orgs_client(client, two_orgs):
    resp = await client.get(
        f"{API}/clients/{two_orgs['client_b']}", headers=two_orgs["headers_a"]
    )
    assert resp.status_code == 404


async def test_cannot_attach_brand_profile_to_other_orgs_client(client, two_orgs):
    resp = await client.post(
        f"{API}/clients/{two_orgs['client_b']}/brand-profile",
        json={},
        headers=two_orgs["headers_a"],
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------
async def test_campaign_list_only_returns_own_org(client, two_orgs):
    resp = await client.get(f"{API}/campaigns", headers=two_orgs["headers_a"])
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data["items"]}
    assert str(two_orgs["camp_a"]) in ids
    assert str(two_orgs["camp_b"]) not in ids
    assert data["total"] == 1


async def test_cannot_read_other_orgs_campaign(client, two_orgs):
    resp = await client.get(
        f"{API}/campaigns/{two_orgs['camp_b']}", headers=two_orgs["headers_a"]
    )
    assert resp.status_code == 404


async def test_other_orgs_campaign_content_is_empty(client, two_orgs):
    # Campaign belongs to B; querying under A's org filter must leak nothing.
    resp = await client.get(
        f"{API}/campaigns/{two_orgs['camp_b']}/content", headers=two_orgs["headers_a"]
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_cannot_submit_review_on_other_orgs_campaign(client, two_orgs):
    resp = await client.patch(
        f"{API}/campaigns/{two_orgs['camp_b']}/review",
        json={"decision": "approved"},
        headers=two_orgs["headers_a"],
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Content / publishing
# ---------------------------------------------------------------------------
async def test_cannot_publish_other_orgs_content(client, two_orgs):
    resp = await client.post(
        f"{API}/publishing/{two_orgs['content_b']}/publish",
        headers=two_orgs["headers_a"],
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Missing / invalid auth
# ---------------------------------------------------------------------------
async def test_unauthenticated_request_rejected(client, two_orgs):
    resp = await client.get(f"{API}/clients")
    assert resp.status_code in (401, 403)
