"""Hand-off to the agency's scheduler: ``GET /public/content`` and the approved webhook.

Only approved-or-later content may leave through either exit — a draft handed to a
scheduler would post unreviewed copy to a client's account.
"""

from types import SimpleNamespace
from typing import Any

import pytest

from agency.services.api_keys import create_api_key
from tests.conftest import (
    auth_header_for,
    create_client_row,
    create_content_row,
    create_org,
    create_subscription,
    create_user_row,
)

API = "/api/v1"


@pytest.fixture
async def keyed(session_factory):
    org_id = await create_org(session_factory, "Handoff Agency")
    client_id = await create_client_row(session_factory, org_id, "Sunrise Coffee")
    async with session_factory() as s:
        key = (await create_api_key(s, org_id, "zapier"))["key"]
    return SimpleNamespace(org_id=org_id, client_id=client_id, headers={"X-API-Key": key})


async def test_requires_an_api_key(client):
    assert (await client.get(f"{API}/public/content")).status_code == 401


async def test_lists_approved_only_by_default(client, session_factory, keyed):
    approved = await create_content_row(
        session_factory,
        keyed.org_id,
        keyed.client_id,
        status="approved",
        body="Ready to post",
        hashtags=["coldbrew"],
        metadata={"approval": {"at": "2026-10-30T10:00:00+00:00", "via": "dashboard"}},
    )
    await create_content_row(session_factory, keyed.org_id, keyed.client_id, status="draft")
    await create_content_row(session_factory, keyed.org_id, keyed.client_id, status="failed")

    resp = await client.get(f"{API}/public/content", headers=keyed.headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [i["id"] for i in items] == [str(approved)]
    item = items[0]
    assert item["body"] == "Ready to post"
    assert item["hashtags"] == ["coldbrew"]
    assert item["client_name"] == "Sunrise Coffee"
    assert item["approved_at"] == "2026-10-30T10:00:00+00:00"
    assert item["approved_via"] == "dashboard"


@pytest.mark.parametrize("status", ["draft", "rejected", "failed", "anything"])
async def test_unapproved_statuses_are_refused(client, keyed, status):
    resp = await client.get(f"{API}/public/content?status={status}", headers=keyed.headers)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "status_not_handed_off"


async def test_scheduled_and_client_filter(client, session_factory, keyed):
    other_client = await create_client_row(session_factory, keyed.org_id, "Other Brand")
    mine = await create_content_row(
        session_factory, keyed.org_id, keyed.client_id, status="scheduled"
    )
    await create_content_row(session_factory, keyed.org_id, other_client, status="scheduled")
    resp = await client.get(
        f"{API}/public/content?status=scheduled&client_id={keyed.client_id}",
        headers=keyed.headers,
    )
    assert [i["id"] for i in resp.json()["items"]] == [str(mine)]


async def test_is_org_scoped(client, session_factory, keyed):
    other_org = await create_org(session_factory, "Someone Else")
    other_client = await create_client_row(session_factory, other_org)
    theirs = await create_content_row(session_factory, other_org, other_client, status="approved")
    resp = await client.get(f"{API}/public/content", headers=keyed.headers)
    assert str(theirs) not in {i["id"] for i in resp.json()["items"]}
    # Naming their client does not reach it either.
    resp = await client.get(
        f"{API}/public/content?client_id={other_client}", headers=keyed.headers
    )
    assert resp.json()["items"] == []


async def test_dashboard_approve_webhook_carries_the_post(
    client, session_factory, monkeypatch
):
    sent: list[tuple[Any, str, dict]] = []

    async def _capture(org_id, event, payload):
        sent.append((org_id, event, payload))
        return []

    monkeypatch.setattr("agency.routers.content.dispatch_webhook", _capture)

    class _Brain:
        async def ainvoke(self, _prompt):
            return SimpleNamespace(content='{"issues": []}')

    monkeypatch.setattr("agency.services.llm_provider.get_brain_llm", lambda *a, **k: _Brain())

    org_id = await create_org(session_factory, "Webhook Agency")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org_id, "Brand")
    user_id = await create_user_row(session_factory, org_id)
    content_id = await create_content_row(
        session_factory, org_id, client_id, body="Approve me", media_urls=["https://x.test/a.png"]
    )
    resp = await client.post(
        f"{API}/content/{content_id}/approve",
        headers=auth_header_for(org_id, user_id=user_id),
    )
    assert resp.status_code == 200, resp.text
    assert len(sent) == 1
    _, event, payload = sent[0]
    assert event == "content.approved"
    # The pre-261031 keys stay for existing receivers.
    assert payload["content_id"] == str(content_id)
    assert payload["client_id"] == str(client_id)
    assert payload["platform"] == "linkedin"
    assert payload["content"]["body"] == "Approve me"
    assert payload["content"]["media_urls"] == ["https://x.test/a.png"]
    assert payload["content"]["status"] == "approved"
    assert payload["content"]["approved_via"] == "dashboard"


def test_handoff_item_refuses_unapproved():
    from agency.services.handoff import handoff_item

    piece = SimpleNamespace(status="draft")
    with pytest.raises(ValueError):
        handoff_item(piece, client_name=None)
