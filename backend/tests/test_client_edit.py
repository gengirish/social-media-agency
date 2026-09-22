"""Editing, archiving and restoring a client, and the tenant boundary on each.

Each cross-tenant test asserts that the other org's row is unchanged, not just the
status code — a 404 that still wrote the edit would be worthless.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from agency.models.tables import BrandProfile, Client, ContentPiece
from tests.conftest import auth_header_for, create_client_row, create_content_row, create_org

API = "/api/v1"


@pytest.fixture
async def orgs(session_factory):
    org_a = await create_org(session_factory, "Org A")
    org_b = await create_org(session_factory, "Org B")
    return {
        "org_a": org_a,
        "client_a": await create_client_row(session_factory, org_a, "Brand A"),
        "client_b": await create_client_row(session_factory, org_b, "Brand B"),
        "headers_a": auth_header_for(org_a),
    }


async def _client_row(session_factory, client_id) -> Client:
    async with session_factory() as session:
        return (await session.execute(select(Client).where(Client.id == client_id))).scalar_one()


async def test_patch_updates_only_sent_fields(client, orgs, session_factory):
    resp = await client.patch(
        f"{API}/clients/{orgs['client_a']}",
        json={"brand_name": "Brand A Renamed", "contact_email": "hi@a.com"},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["brand_name"] == "Brand A Renamed"
    assert body["contact_email"] == "hi@a.com"

    row = await _client_row(session_factory, orgs["client_a"])
    assert row.brand_name == "Brand A Renamed"
    assert row.industry is not None  # untouched


async def test_patch_rejects_null_brand_name(client, orgs):
    resp = await client.patch(
        f"{API}/clients/{orgs['client_a']}",
        json={"brand_name": None},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 422


async def test_cannot_patch_other_orgs_client(client, orgs, session_factory):
    resp = await client.patch(
        f"{API}/clients/{orgs['client_b']}",
        json={"brand_name": "Hijacked"},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 404
    row = await _client_row(session_factory, orgs["client_b"])
    assert row.brand_name == "Brand B"


async def test_put_brand_profile_creates_then_updates_partially(client, orgs):
    url = f"{API}/clients/{orgs['client_a']}/brand-profile"
    assert (await client.get(url, headers=orgs["headers_a"])).status_code == 404

    resp = await client.put(
        url,
        json={"voice_description": "Warm", "vocabulary_exclude": ["cheap"]},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 200

    resp = await client.put(url, json={"target_audience": "Founders"}, headers=orgs["headers_a"])
    assert resp.status_code == 200

    body = (await client.get(url, headers=orgs["headers_a"])).json()
    assert body["voice_description"] == "Warm"
    assert body["vocabulary_exclude"] == ["cheap"]
    assert body["target_audience"] == "Founders"


async def test_cannot_read_or_write_other_orgs_brand_profile(client, orgs, session_factory):
    url = f"{API}/clients/{orgs['client_b']}/brand-profile"
    assert (await client.get(url, headers=orgs["headers_a"])).status_code == 404
    resp = await client.put(url, json={"voice_description": "x"}, headers=orgs["headers_a"])
    assert resp.status_code == 404

    async with session_factory() as session:
        rows = await session.execute(
            select(BrandProfile).where(BrandProfile.client_id == orgs["client_b"])
        )
        assert rows.scalars().all() == []


# ---------------------------------------------------------------------------
# Archive / restore
# ---------------------------------------------------------------------------
async def _ids(client, headers, archived=False) -> set[str]:
    resp = await client.get(f"{API}/clients?archived={str(archived).lower()}", headers=headers)
    assert resp.status_code == 200
    return {item["id"] for item in resp.json()["items"]}


async def test_archive_moves_client_to_archived_list_and_restore_undoes_it(client, orgs):
    cid, h = str(orgs["client_a"]), orgs["headers_a"]

    resp = await client.post(f"{API}/clients/{cid}/archive", headers=h)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    assert cid not in await _ids(client, h)
    assert cid in await _ids(client, h, archived=True)
    # Still readable, so the details page can offer Restore.
    assert (await client.get(f"{API}/clients/{cid}", headers=h)).status_code == 200

    resp = await client.post(f"{API}/clients/{cid}/restore", headers=h)
    assert resp.status_code == 200
    assert cid in await _ids(client, h)
    assert cid not in await _ids(client, h, archived=True)


async def test_archive_refused_while_posts_are_scheduled(client, orgs, session_factory):
    await create_content_row(
        session_factory, orgs["org_a"], orgs["client_a"], status="scheduled"
    )
    resp = await client.post(f"{API}/clients/{orgs['client_a']}/archive", headers=orgs["headers_a"])
    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "has_scheduled_posts", "count": 1}
    assert (await _client_row(session_factory, orgs["client_a"])).is_active is True


async def test_archive_with_unschedule_returns_scheduled_posts_to_approved(
    client, orgs, session_factory
):
    content_id = await create_content_row(
        session_factory, orgs["org_a"], orgs["client_a"], status="scheduled"
    )
    resp = await client.post(
        f"{API}/clients/{orgs['client_a']}/archive?unschedule=true", headers=orgs["headers_a"]
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    async with session_factory() as session:
        piece = await session.get(ContentPiece, content_id)
        assert piece.status == "approved"
        assert piece.scheduled_at is None


@pytest.mark.parametrize("action", ["archive", "restore"])
async def test_cannot_archive_or_restore_other_orgs_client(client, orgs, session_factory, action):
    url = f"{API}/clients/{orgs['client_b']}/{action}"
    resp = await client.post(url, headers=orgs["headers_a"])
    assert resp.status_code == 404
    assert (await _client_row(session_factory, orgs["client_b"])).is_active is True


async def _archive(session_factory, client_id) -> None:
    async with session_factory() as session:
        row = await session.get(Client, client_id)
        row.is_active = False
        await session.commit()


async def test_publish_refused_for_archived_client(client, orgs, session_factory, monkeypatch):
    from agency.services.publishing import publisher

    async def _boom(*_a, **_k):
        raise AssertionError("publisher reached for an archived client")

    monkeypatch.setattr(publisher, "publish", _boom)
    content_id = await create_content_row(
        session_factory, orgs["org_a"], orgs["client_a"], status="approved"
    )
    await _archive(session_factory, orgs["client_a"])

    resp = await client.post(f"{API}/publishing/{content_id}/publish", headers=orgs["headers_a"])
    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "client_archived"}


async def test_schedule_refused_for_archived_client(client, orgs, session_factory):
    content_id = await create_content_row(
        session_factory, orgs["org_a"], orgs["client_a"], status="approved"
    )
    await _archive(session_factory, orgs["client_a"])

    resp = await client.post(
        f"{API}/publishing/{content_id}/schedule",
        json={"scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        headers=orgs["headers_a"],
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "client_archived"}
    async with session_factory() as session:
        piece = await session.get(ContentPiece, content_id)
        assert piece.status == "approved"
        assert piece.scheduled_at is None
