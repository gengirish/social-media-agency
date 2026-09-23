"""Cadence-parity foundation: the creative-asset store, the client overview and
the shared generation-quota helpers.

Tenancy tests follow ``test_tenancy_routers.py``: each asserts on a
cross-tenant identifier so it fails if its ``org_id`` filter is removed.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from tests.conftest import (
    auth_header_for,
    create_client_row,
    create_content_row,
    create_org,
    create_platform_account,
    create_subscription,
    create_user_row,
)

API = "/api/v1"


@pytest.fixture
async def orgs(session_factory):
    org_a = await create_org(session_factory, "Org A", slug="org-a")
    org_b = await create_org(session_factory, "Org B", slug="org-b")
    await create_subscription(session_factory, org_a, plan_tier="growth", posts_limit=1000)
    await create_subscription(session_factory, org_b, plan_tier="growth", posts_limit=1000)
    client_a = await create_client_row(session_factory, org_a, "Brand A")
    client_b = await create_client_row(session_factory, org_b, "Brand B")
    user_a = await create_user_row(session_factory, org_a, full_name="Alice A")
    user_b = await create_user_row(session_factory, org_b, full_name="Bob B")
    return {
        "org_a": org_a,
        "org_b": org_b,
        "client_a": client_a,
        "client_b": client_b,
        "headers_a": auth_header_for(org_a, user_id=user_a),
        "headers_b": auth_header_for(org_b, user_id=user_b),
    }


async def _asset(session_factory, org_id, client_id, kind="blog_post", title="Post"):
    from agency.services.creative_assets import save_asset

    async with session_factory() as session:
        asset = await save_asset(
            session,
            org_id=org_id,
            client_id=client_id,
            kind=kind,
            title=title,
            payload={"body": "hello"},
        )
        await session.commit()
        return asset.id


# ---------------------------------------------------------------------------
# /assets
# ---------------------------------------------------------------------------
async def test_list_assets_scoped_to_client_and_kind(client, orgs, session_factory):
    await _asset(session_factory, orgs["org_a"], orgs["client_a"], "blog_post", "Blog one")
    await _asset(session_factory, orgs["org_a"], orgs["client_a"], "email_campaign", "Welcome")

    resp = await client.get(
        f"{API}/assets",
        params={"client_id": str(orgs["client_a"]), "kind": "blog_post"},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert [a["title"] for a in body["items"]] == ["Blog one"]


async def test_list_assets_rejects_other_orgs_client(client, orgs, session_factory):
    await _asset(session_factory, orgs["org_b"], orgs["client_b"], title="B secret")
    resp = await client.get(
        f"{API}/assets", params={"client_id": str(orgs["client_b"])}, headers=orgs["headers_a"]
    )
    assert resp.status_code == 404


async def test_list_assets_ignores_foreign_rows_on_own_client(client, orgs, session_factory):
    """A row carrying org A's client id but org B's org id must not leak into A's list."""
    await _asset(session_factory, orgs["org_b"], orgs["client_a"], title="planted")
    resp = await client.get(
        f"{API}/assets", params={"client_id": str(orgs["client_a"])}, headers=orgs["headers_a"]
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_list_assets_rejects_unknown_kind(client, orgs):
    resp = await client.get(
        f"{API}/assets",
        params={"client_id": str(orgs["client_a"]), "kind": "nope"},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
async def test_asset_by_id_is_org_scoped(client, orgs, session_factory, method):
    asset_b = await _asset(session_factory, orgs["org_b"], orgs["client_b"], title="B")
    kwargs = {"json": {"title": "hijacked"}} if method == "patch" else {}
    resp = await getattr(client, method)(
        f"{API}/assets/{asset_b}", headers=orgs["headers_a"], **kwargs
    )
    assert resp.status_code == 404

    from agency.models.tables import CreativeAsset

    async with session_factory() as session:
        row = (
            await session.execute(select(CreativeAsset).where(CreativeAsset.id == asset_b))
        ).scalar_one()
        assert row.title == "B"


async def test_update_and_delete_asset(client, orgs, session_factory):
    asset_a = await _asset(session_factory, orgs["org_a"], orgs["client_a"], title="Old")
    resp = await client.patch(
        f"{API}/assets/{asset_a}", json={"title": "New"}, headers=orgs["headers_a"]
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "New"

    resp = await client.delete(f"{API}/assets/{asset_a}", headers=orgs["headers_a"])
    assert resp.status_code == 204
    resp = await client.get(f"{API}/assets/{asset_a}", headers=orgs["headers_a"])
    assert resp.status_code == 404


async def test_save_asset_rejects_unknown_kind(orgs, session_factory):
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await _asset(session_factory, orgs["org_a"], orgs["client_a"], kind="made_up")


# ---------------------------------------------------------------------------
# /clients/overview
# ---------------------------------------------------------------------------
async def test_overview_counts_real_rows_and_stays_in_org(client, orgs, session_factory):
    await create_content_row(session_factory, orgs["org_a"], orgs["client_a"], status="draft")
    await create_content_row(session_factory, orgs["org_a"], orgs["client_a"], status="published")
    await create_platform_account(
        session_factory, orgs["org_a"], orgs["client_a"], platform="linkedin"
    )
    # Org B rows on org A's client id — must not be counted for A.
    await create_content_row(session_factory, orgs["org_b"], orgs["client_a"], status="draft")
    await create_platform_account(
        session_factory, orgs["org_b"], orgs["client_a"], platform="twitter"
    )

    resp = await client.get(f"{API}/clients/overview", headers=orgs["headers_a"])
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["id"] for i in items] == [str(orgs["client_a"])]
    a = items[0]
    assert a["pending"] == 1
    assert a["published"] == 1
    assert a["total_posts"] == 2
    assert a["connected_accounts"] == 1
    assert a["has_brand_profile"] is False


async def test_overview_is_not_parsed_as_client_id(client, orgs):
    # Declared before /{client_id}; otherwise "overview" would 422 as a bad UUID.
    resp = await client.get(f"{API}/clients/overview", headers=orgs["headers_b"])
    assert resp.status_code == 200
    assert [i["brand_name"] for i in resp.json()["items"]] == ["Brand B"]


# ---------------------------------------------------------------------------
# generation quota helpers
# ---------------------------------------------------------------------------
async def test_generation_quota_blocks_at_limit_and_charges(orgs, session_factory):
    from fastapi import HTTPException

    from agency.models.tables import Subscription
    from agency.services.generation_quota import charge_generation, require_generation_quota

    async with session_factory() as session:
        sub = (
            await session.execute(select(Subscription).where(Subscription.org_id == orgs["org_a"]))
        ).scalar_one()
        sub.generations_limit = 1
        sub.generations_used = 0
        await session.commit()

    async with session_factory() as session:
        await require_generation_quota(session, orgs["org_a"])
        await charge_generation(session, orgs["org_a"])
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc:
            await require_generation_quota(session, orgs["org_a"])
        assert exc.value.status_code == 402

    # Org B untouched by A's charge.
    async with session_factory() as session:
        sub_b = (
            await session.execute(select(Subscription).where(Subscription.org_id == orgs["org_b"]))
        ).scalar_one()
        assert (sub_b.generations_used or 0) == 0


async def test_require_quota_without_subscription(session_factory):
    from fastapi import HTTPException

    from agency.services.generation_quota import require_generation_quota

    org = await create_org(session_factory, "No Sub", slug="no-sub")
    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc:
            await require_generation_quota(session, org)
        assert exc.value.status_code == 402


async def test_get_org_client_404s_across_orgs(orgs, session_factory):
    from fastapi import HTTPException

    from agency.services.brand_context import get_org_client

    async with session_factory() as session:
        with pytest.raises(HTTPException):
            await get_org_client(session, orgs["client_b"], orgs["org_a"])
        with pytest.raises(HTTPException):
            await get_org_client(session, uuid4(), orgs["org_a"])
        found = await get_org_client(session, orgs["client_a"], orgs["org_a"])
        assert found.id == orgs["client_a"]
