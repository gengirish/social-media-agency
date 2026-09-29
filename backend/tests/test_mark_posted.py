"""``POST /publishing/{id}/mark-posted`` — the "I posted it myself" record.

Manual mode exists for the operator whose pages were created outside CampaignForge
and who does not want the product touching them. Nothing is sent anywhere: a human
opens the platform, posts, and comes back. This route writes the record.

What is worth testing here, and why each one is not cosmetic:

1. **No publisher is reached.** ``no_real_publish`` fails the test outright if one is,
   on every path including success. That is the whole premise of the feature.
2. **A manual channel is required.** Without it the route would let an org mark a post
   published on a channel it never registered, and the lookup is ``org_id``-filtered
   because there is no RLS — another tenant's manual row carrying this client's id
   must not satisfy it.
3. **It costs a post.** ``posts_limit`` is the product's only usage meter and the plan
   copy sells it as published posts; a free manual post would make manual mode an
   unlimited free tier.
4. **A 402 writes nothing.** The row must not move when the charge cannot be made.

The approval gate itself (``draft`` → 409, already-``published`` → 409) lives in
``test_approval_gate.py``; the capability gate (``member`` yes, ``viewer`` no) lives in
``test_gate_publishing.py``.
"""

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from agency.models.tables import ContentPiece, Subscription
from tests.conftest import (
    auth_for,
    create_client_row,
    create_content_row,
    create_org,
    create_platform_account,
    create_subscription,
)

API = "/api/v1"

POST_URL = "https://www.linkedin.com/feed/update/urn:li:activity:1234567890/"


@pytest.fixture
def no_real_publish(monkeypatch):
    """Fail the test if anything reaches a real platform publisher.

    Installed on the success paths too, not only the refusals: "calls no publisher"
    is what makes this route safe for a channel with no token.
    """
    from agency.services.publishing import publisher

    async def _boom(*_a: Any, **_k: Any) -> dict:
        raise AssertionError("publisher reached by mark-posted")

    monkeypatch.setattr(publisher, "publish", _boom)


@pytest.fixture
def link_checks(monkeypatch):
    """Record the links handed to the shape check, keeping its real behaviour.

    ``mark_posted`` validates ``post_url`` with ``assert_safe_link``, which needs no
    network (unlike ``assert_public_url``, which resolves the host). So this spies
    rather than stubs: an unsafe link still gets its 400. The router calls through the
    module, so replacing the attribute is enough.
    """
    from agency.services import url_safety

    seen: list[str] = []
    real = url_safety.assert_safe_link

    def _spy(url: str) -> str:
        seen.append(url)
        return real(url)

    monkeypatch.setattr(url_safety, "assert_safe_link", _spy)
    return seen


@pytest.fixture
async def tenant(session_factory):
    """An org with a *manual* LinkedIn channel and room in its plan."""
    org_id = await create_org(session_factory, "Manual Org")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=10)
    client_id = await create_client_row(session_factory, org_id, "Manual Brand")
    await create_platform_account(
        session_factory, org_id, client_id, platform="linkedin", status="manual"
    )
    headers = await auth_for(session_factory, org_id, "owner")
    return SimpleNamespace(org_id=org_id, client_id=client_id, headers=headers)


async def _piece(session_factory, content_id: UUID) -> ContentPiece:
    async with session_factory() as s:
        return (
            await s.execute(select(ContentPiece).where(ContentPiece.id == content_id))
        ).scalar_one()


async def _posts_used(session_factory, org_id: UUID) -> int:
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        return sub.posts_used or 0


async def _approved(session_factory, tenant, **kwargs: Any) -> UUID:
    return await create_content_row(
        session_factory, tenant.org_id, tenant.client_id, status="approved", **kwargs
    )


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------
async def test_success_records_the_post_and_charges_one(
    client, session_factory, tenant, no_real_publish, link_checks
):
    content_id = await _approved(session_factory, tenant)
    before = await _posts_used(session_factory, tenant.org_id)

    resp = await client.post(
        f"{API}/publishing/{content_id}/mark-posted",
        json={"post_url": POST_URL},
        headers=tenant.headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "status": "published",
        "content_id": str(content_id),
        "publish_mode": "manual",
        "post_url": POST_URL,
    }

    piece = await _piece(session_factory, content_id)
    assert piece.status == "published"
    assert piece.published_at is not None
    meta = piece.metadata_ or {}
    assert meta["publish_mode"] == "manual"
    assert meta["post_url"] == POST_URL
    # Attributable: the record is self-reported, so who reported it is part of it.
    assert UUID(meta["posted_by"])
    # A live post carries no stale warning.
    assert meta["publish_blocked"] is None
    assert meta["publish_error"] is None

    assert await _posts_used(session_factory, tenant.org_id) == before + 1
    assert link_checks == [POST_URL]


async def test_post_url_is_optional(
    client, session_factory, tenant, no_real_publish, link_checks
):
    """Forcing the link would strand anyone who posted from their phone, and the queue
    would fill with ``approved`` rows that are actually live."""
    content_id = await _approved(session_factory, tenant)

    resp = await client.post(
        f"{API}/publishing/{content_id}/mark-posted", json={}, headers=tenant.headers
    )

    assert resp.status_code == 200, resp.text
    piece = await _piece(session_factory, content_id)
    assert piece.status == "published"
    assert (piece.metadata_ or {})["post_url"] is None
    # Nothing to check, so the URL check was not run at all.
    assert link_checks == []


async def test_blank_post_url_is_stored_as_none(
    client, session_factory, tenant, no_real_publish, link_checks
):
    """An empty field from the UI is "no link", not the empty string — otherwise the
    Queue would render a broken "Add link" state as a present one."""
    content_id = await _approved(session_factory, tenant)

    resp = await client.post(
        f"{API}/publishing/{content_id}/mark-posted",
        json={"post_url": "   "},
        headers=tenant.headers,
    )

    assert resp.status_code == 200, resp.text
    assert ((await _piece(session_factory, content_id)).metadata_ or {})["post_url"] is None
    assert link_checks == []


async def test_calendar_exposes_publish_mode(
    client, session_factory, tenant, no_real_publish, link_checks
):
    """The Queue and Calendar must be able to tell a manual post from a real one, or
    they will say "Publishes <time>" about something the product will not publish."""
    from datetime import UTC, datetime, timedelta

    content_id = await _approved(session_factory, tenant)
    # ``get_calendar`` ranges on ``scheduled_at``, so the piece needs one to appear.
    async with session_factory() as s:
        row = await s.get(ContentPiece, content_id)
        assert row is not None
        row.scheduled_at = datetime.now(UTC)
        await s.commit()

    await client.post(
        f"{API}/publishing/{content_id}/mark-posted", json={}, headers=tenant.headers
    )

    start = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    end = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    resp = await client.get(
        f"{API}/publishing/calendar",
        params={"start": start, "end": end},
        headers=tenant.headers,
    )

    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json()["items"] if i["id"] == str(content_id))
    assert item["publish_mode"] == "manual"


# ---------------------------------------------------------------------------
# A manual channel is required
# ---------------------------------------------------------------------------
async def test_no_manual_channel_is_400(client, session_factory, no_real_publish):
    """Without this the route could mark a post published on a channel the org never
    registered."""
    org_id = await create_org(session_factory, "No Channel Org")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=10)
    client_id = await create_client_row(session_factory, org_id, "No Channel Brand")
    headers = await auth_for(session_factory, org_id, "owner")
    content_id = await create_content_row(session_factory, org_id, client_id, status="approved")

    resp = await client.post(
        f"{API}/publishing/{content_id}/mark-posted", json={}, headers=headers
    )

    assert resp.status_code == 400
    assert "manually managed channel" in resp.json()["detail"].lower()
    assert (await _piece(session_factory, content_id)).status == "approved"
    assert await _posts_used(session_factory, org_id) == 0


async def test_a_connected_channel_is_not_a_manual_one(
    client, session_factory, no_real_publish
):
    """``status = 'manual'`` is the whole distinction (see the plan's §1 table). An
    OAuth-connected channel has a publisher path and must use it."""
    org_id = await create_org(session_factory, "Connected Org")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=10)
    client_id = await create_client_row(session_factory, org_id, "Connected Brand")
    await create_platform_account(
        session_factory, org_id, client_id, platform="linkedin", status="connected"
    )
    headers = await auth_for(session_factory, org_id, "owner")
    content_id = await create_content_row(session_factory, org_id, client_id, status="approved")

    resp = await client.post(
        f"{API}/publishing/{content_id}/mark-posted", json={}, headers=headers
    )

    assert resp.status_code == 400
    assert (await _piece(session_factory, content_id)).status == "approved"


async def test_a_manual_channel_on_another_platform_does_not_count(
    client, session_factory, tenant, no_real_publish
):
    """Mode is per channel, not per client: a manual LinkedIn page says nothing about
    Instagram."""
    content_id = await _approved(session_factory, tenant, platform="instagram")

    resp = await client.post(
        f"{API}/publishing/{content_id}/mark-posted", json={}, headers=tenant.headers
    )

    assert resp.status_code == 400
    assert (await _piece(session_factory, content_id)).status == "approved"


# ---------------------------------------------------------------------------
# TENANCY — the two cross-org tests for this route live in
# ``test_tenancy_routers.py`` with the rest of the per-router isolation suite.
# What stays here is the not-found case, which is behaviour rather than tenancy.
# ---------------------------------------------------------------------------
async def test_unknown_content_id_is_404(client, session_factory, tenant, no_real_publish):
    resp = await client.post(
        f"{API}/publishing/{uuid4()}/mark-posted", json={}, headers=tenant.headers
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Quota
# ---------------------------------------------------------------------------
async def test_quota_exhausted_is_402_and_writes_nothing(
    client, session_factory, no_real_publish
):
    org_id = await create_org(session_factory, "Exhausted Org")
    await create_subscription(
        session_factory, org_id, plan_tier="growth", posts_limit=3, posts_used=3
    )
    client_id = await create_client_row(session_factory, org_id, "Exhausted Brand")
    await create_platform_account(
        session_factory, org_id, client_id, platform="linkedin", status="manual"
    )
    headers = await auth_for(session_factory, org_id, "owner")
    content_id = await create_content_row(session_factory, org_id, client_id, status="approved")

    resp = await client.post(
        f"{API}/publishing/{content_id}/mark-posted",
        json={"post_url": POST_URL},
        headers=headers,
    )

    assert resp.status_code == 402
    piece = await _piece(session_factory, content_id)
    assert piece.status == "approved"
    assert piece.published_at is None
    assert "publish_mode" not in (piece.metadata_ or {})
    # Not over-charged either: a refused call costs nothing.
    assert await _posts_used(session_factory, org_id) == 3


async def test_no_subscription_at_all_is_402(client, session_factory, no_real_publish):
    """``check_quota`` returns False with no subscription row, and this route must
    honour that rather than treating "no plan" as unlimited."""
    org_id = await create_org(session_factory, "Planless Org")
    client_id = await create_client_row(session_factory, org_id, "Planless Brand")
    await create_platform_account(
        session_factory, org_id, client_id, platform="linkedin", status="manual"
    )
    headers = await auth_for(session_factory, org_id, "owner")
    content_id = await create_content_row(session_factory, org_id, client_id, status="approved")

    resp = await client.post(
        f"{API}/publishing/{content_id}/mark-posted", json={}, headers=headers
    )

    assert resp.status_code == 402
    assert (await _piece(session_factory, content_id)).status == "approved"


# ---------------------------------------------------------------------------
# The post URL goes through the same public-internet check as any user URL
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad",
    [
        "http://localhost/post/1",
        "http://127.0.0.1/post/1",
        "file:///etc/passwd",
        "not a url",
    ],
)
async def test_unsafe_post_url_is_refused_and_writes_nothing(
    client, session_factory, tenant, no_real_publish, bad
):
    """The link is rendered as a link and opened in a new tab. No stub here — the real
    check runs, and none of these needs the network to be refused."""
    content_id = await _approved(session_factory, tenant)

    resp = await client.post(
        f"{API}/publishing/{content_id}/mark-posted",
        json={"post_url": bad},
        headers=tenant.headers,
    )

    assert resp.status_code == 400
    piece = await _piece(session_factory, content_id)
    assert piece.status == "approved"
    assert "publish_mode" not in (piece.metadata_ or {})
    assert await _posts_used(session_factory, tenant.org_id) == 0
