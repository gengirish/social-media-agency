"""Client review links — lifecycle, the secret, and what the agency is told.

Tenancy (another client / campaign / org) lives in ``test_tenancy_routers.py`` and the
moderation gate in ``test_approval_gate.py``; this file covers everything else a link
does. The brain-tier LLM is stubbed wherever an approval runs.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select

from agency.models.tables import Client, ClientReviewLink, ContentPiece, Notification
from tests.conftest import (
    auth_for,
    create_campaign_row,
    create_client_row,
    create_content_row,
    create_org,
    create_white_label,
)

API = "/api/v1"
CLEAN = '{"issues": []}'


class _Brain:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, _prompt: Any) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(content=CLEAN)


@pytest.fixture
def brain(monkeypatch):
    stub = _Brain()
    monkeypatch.setattr("agency.services.llm_provider.get_brain_llm", lambda *a, **k: stub)
    return stub


@pytest.fixture
async def shop(client, session_factory):
    org_id = await create_org(session_factory, "Review Agency")
    client_id = await create_client_row(session_factory, org_id, "Sunrise Coffee")
    creator = UUID(int=7)
    headers = await auth_for(session_factory, org_id, role="member", user_id=creator)
    return SimpleNamespace(org_id=org_id, client_id=client_id, creator=creator, headers=headers)


async def _link(client, shop, **body) -> dict:
    resp = await client.post(
        f"{API}/clients/{shop.client_id}/review-links", json=body, headers=shop.headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _row(session_factory, link_id: str) -> ClientReviewLink:
    async with session_factory() as s:
        row = await s.get(ClientReviewLink, UUID(link_id))
        assert row is not None
        return row


# ---------------------------------------------------------------------------
# Making a link
# ---------------------------------------------------------------------------
async def test_token_is_returned_once_and_only_its_hash_is_stored(client, session_factory, shop):
    made = await _link(client, shop)
    token = made["token"]
    assert token.startswith("rv_")
    assert made["path"] == f"/review/{token}"
    assert made["link"]["state"] == "active"

    row = await _row(session_factory, made["link"]["id"])
    assert row.token_hash != token
    assert token not in row.token_hash
    assert len(row.token_hash) == 64

    listed = await client.get(
        f"{API}/clients/{shop.client_id}/review-links", headers=shop.headers
    )
    assert token not in listed.text


async def test_default_expiry_is_fourteen_days(client, session_factory, shop):
    made = await _link(client, shop)
    expires = datetime.fromisoformat(made["link"]["expires_at"])
    delta = expires - datetime.now(UTC)
    assert timedelta(days=13, hours=23) < delta <= timedelta(days=14)


@pytest.mark.parametrize("ttl", [0, 31])
async def test_ttl_outside_bounds_is_refused(client, shop, ttl):
    resp = await client.post(
        f"{API}/clients/{shop.client_id}/review-links",
        json={"ttl_days": ttl},
        headers=shop.headers,
    )
    assert resp.status_code == 422


async def test_viewer_cannot_share(client, session_factory, shop):
    """Sharing hands out approval; a seat without ``content.approve`` cannot."""
    viewer = await auth_for(session_factory, shop.org_id, role="viewer")
    resp = await client.post(
        f"{API}/clients/{shop.client_id}/review-links", json={}, headers=viewer
    )
    assert resp.status_code == 403
    async with session_factory() as s:
        assert (await s.execute(select(ClientReviewLink))).scalars().all() == []


async def test_archived_client_cannot_be_shared(client, session_factory, shop):
    async with session_factory() as s:
        row = await s.get(Client, shop.client_id)
        row.is_active = False
        await s.commit()
    resp = await client.post(
        f"{API}/clients/{shop.client_id}/review-links", json={}, headers=shop.headers
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "client_archived"


# ---------------------------------------------------------------------------
# Opening a link
# ---------------------------------------------------------------------------
async def test_page_shows_agency_client_and_pending_only(client, session_factory, shop):
    await create_white_label(session_factory, shop.org_id, company_name="Northwind Social")
    pending = await create_content_row(session_factory, shop.org_id, shop.client_id)
    empty = await create_content_row(session_factory, shop.org_id, shop.client_id, body="[]")
    approved_elsewhere = await create_content_row(
        session_factory, shop.org_id, shop.client_id, status="approved"
    )
    token = (await _link(client, shop))["token"]

    resp = await client.get(f"{API}/portal/review/{token}")
    assert resp.status_code == 200, resp.text
    page = resp.json()
    assert page["agency"]["name"] == "Northwind Social"
    assert page["client"]["name"] == "Sunrise Coffee"
    assert page["campaign"] is None
    pending_ids = [i["id"] for i in page["pending"]]
    assert pending_ids == [str(pending)]
    assert page["pending"][0]["status"] == "pending"
    # Approved by the agency, not through this link: not the client's to see here.
    decided_ids = [i["id"] for i in page["decided"]]
    assert str(approved_elsewhere) not in decided_ids
    assert str(empty) not in pending_ids
    # Nothing internal leaks onto the public page.
    assert "metadata" not in resp.text
    assert "moderation" not in resp.text


async def test_white_label_logo_must_be_a_safe_link(client, session_factory, shop):
    from agency.models.tables import WhiteLabel

    await create_white_label(session_factory, shop.org_id)
    async with session_factory() as s:
        wl = (
            await s.execute(select(WhiteLabel).where(WhiteLabel.org_id == shop.org_id))
        ).scalar_one()
        wl.logo_url = "javascript:alert(1)"
        wl.primary_color = "red; background:url(x)"
        await s.commit()
    token = (await _link(client, shop))["token"]
    agency = (await client.get(f"{API}/portal/review/{token}")).json()["agency"]
    assert agency["logo_url"] is None
    assert agency["primary_color"] is None


async def test_unknown_token_is_404(client):
    assert (await client.get(f"{API}/portal/review/rv_nope")).status_code == 404
    assert (await client.get(f"{API}/portal/review/not-even-shaped")).status_code == 404


async def test_revoked_link_is_410(client, session_factory, shop):
    made = await _link(client, shop)
    resp = await client.post(
        f"{API}/review-links/{made['link']['id']}/revoke", headers=shop.headers
    )
    assert resp.status_code == 200
    assert resp.json()["link"]["state"] == "revoked"

    page = await client.get(f"{API}/portal/review/{made['token']}")
    assert page.status_code == 410
    assert page.json()["detail"]["code"] == "link_revoked"


async def test_expired_link_is_410_and_cannot_decide(client, session_factory, shop, brain):
    content_id = await create_content_row(session_factory, shop.org_id, shop.client_id)
    made = await _link(client, shop)
    async with session_factory() as s:
        row = await s.get(ClientReviewLink, UUID(made["link"]["id"]))
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()

    page = await client.get(f"{API}/portal/review/{made['token']}")
    assert page.status_code == 410
    assert page.json()["detail"]["code"] == "link_expired"

    resp = await client.post(
        f"{API}/portal/review/{made['token']}/content/{content_id}",
        json={"decision": "approve"},
    )
    assert resp.status_code == 410
    assert brain.calls == 0
    async with session_factory() as s:
        assert (await s.get(ContentPiece, content_id)).status == "draft"


async def test_archiving_the_client_ends_its_links(client, session_factory, shop):
    token = (await _link(client, shop))["token"]
    async with session_factory() as s:
        row = await s.get(Client, shop.client_id)
        row.is_active = False
        await s.commit()
    page = await client.get(f"{API}/portal/review/{token}")
    assert page.status_code == 410
    assert page.json()["detail"]["code"] == "link_inactive"


async def test_opening_records_last_used(client, session_factory, shop):
    made = await _link(client, shop)
    assert made["link"]["last_used_at"] is None
    await client.get(f"{API}/portal/review/{made['token']}")
    assert (await _row(session_factory, made["link"]["id"])).last_used_at is not None


# ---------------------------------------------------------------------------
# Deciding
# ---------------------------------------------------------------------------
async def test_request_changes_needs_a_comment(client, session_factory, shop):
    content_id = await create_content_row(session_factory, shop.org_id, shop.client_id)
    token = (await _link(client, shop))["token"]
    resp = await client.post(
        f"{API}/portal/review/{token}/content/{content_id}",
        json={"decision": "request_changes", "comment": "   "},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "comment_required"


async def test_unknown_decision_is_400(client, session_factory, shop):
    content_id = await create_content_row(session_factory, shop.org_id, shop.client_id)
    token = (await _link(client, shop))["token"]
    resp = await client.post(
        f"{API}/portal/review/{token}/content/{content_id}", json={"decision": "publish"}
    )
    assert resp.status_code == 400


async def test_decided_post_cannot_be_decided_again(client, session_factory, shop, brain):
    content_id = await create_content_row(session_factory, shop.org_id, shop.client_id)
    token = (await _link(client, shop))["token"]
    url = f"{API}/portal/review/{token}/content/{content_id}"
    assert (await client.post(url, json={"decision": "approve"})).status_code == 200
    again = await client.post(url, json={"decision": "request_changes", "comment": "wait"})
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "already_decided"


async def test_decisions_show_on_the_page_after_reload(client, session_factory, shop, brain):
    approve_me = await create_content_row(session_factory, shop.org_id, shop.client_id)
    change_me = await create_content_row(session_factory, shop.org_id, shop.client_id)
    token = (await _link(client, shop))["token"]
    await client.post(
        f"{API}/portal/review/{token}/content/{approve_me}", json={"decision": "approve"}
    )
    await client.post(
        f"{API}/portal/review/{token}/content/{change_me}",
        json={"decision": "request_changes", "comment": "Use the new logo"},
    )
    page = (await client.get(f"{API}/portal/review/{token}")).json()
    decided = {i["id"]: i for i in page["decided"]}
    assert decided[str(approve_me)]["client_review"]["decision"] == "approved"
    # Changes requested stays Pending, so it is listed there with the comment.
    pending = {i["id"]: i for i in page["pending"]}
    assert pending[str(change_me)]["client_review"]["comment"] == "Use the new logo"


async def test_decision_notifies_the_link_creator(client, session_factory, shop):
    content_id = await create_content_row(session_factory, shop.org_id, shop.client_id)
    token = (await _link(client, shop))["token"]
    await client.post(
        f"{API}/portal/review/{token}/content/{content_id}",
        json={"decision": "request_changes", "comment": "Shorter please", "name": "Dana"},
    )
    async with session_factory() as s:
        notes = list((await s.execute(select(Notification))).scalars().all())
    assert len(notes) == 1
    note = notes[0]
    assert note.user_id == shop.creator
    assert note.type == "client_review"
    assert note.title == "Dana asked for changes"
    assert "Shorter please" in note.body
    assert note.data["url"] == f"/content?client={shop.client_id}&status=draft"


async def test_client_approval_fires_the_approved_webhook(
    client, session_factory, shop, brain, monkeypatch
):
    sent: list[tuple[Any, str, dict]] = []

    async def _capture(org_id, event, payload):
        sent.append((org_id, event, payload))
        return []

    monkeypatch.setattr("agency.routers.portal.dispatch_webhook", _capture)
    campaign_id = await create_campaign_row(session_factory, shop.org_id, shop.client_id)
    content_id = await create_content_row(
        session_factory, shop.org_id, shop.client_id, campaign_id, body="Cold brew is back"
    )
    token = (await _link(client, shop, campaign_id=str(campaign_id)))["token"]
    resp = await client.post(
        f"{API}/portal/review/{token}/content/{content_id}", json={"decision": "approve"}
    )
    assert resp.status_code == 200, resp.text
    assert len(sent) == 1
    org_id, event, payload = sent[0]
    assert event == "content.approved"
    assert payload["content_id"] == str(content_id)
    assert payload["content"]["body"] == "Cold brew is back"
    assert payload["content"]["client_name"] == "Sunrise Coffee"
    assert payload["content"]["approved_via"] == "client_link"


async def test_request_changes_fires_no_webhook(client, session_factory, shop, monkeypatch):
    sent: list[Any] = []

    async def _capture(*args):
        sent.append(args)
        return []

    monkeypatch.setattr("agency.routers.portal.dispatch_webhook", _capture)
    content_id = await create_content_row(session_factory, shop.org_id, shop.client_id)
    token = (await _link(client, shop))["token"]
    await client.post(
        f"{API}/portal/review/{token}/content/{content_id}",
        json={"decision": "request_changes", "comment": "No"},
    )
    assert sent == []


async def test_old_slug_portal_routes_are_gone(client, session_factory):
    """The org-slug routes listed every client's drafts; they must not come back."""
    await create_org(session_factory, "Slugged", slug="slugged")
    for path in ("/portal/slugged/campaigns", "/portal/slugged/content"):
        assert (await client.get(f"{API}{path}")).status_code == 404
