"""``PATCH /publishing/{id}/post-url`` — attaching the link after the fact.

The link is optional at ``mark-posted`` time on purpose: forcing it would strand
anyone who posted from their phone, and the queue would fill with ``approved`` rows
that are actually live. This route is how the link arrives later, and the "Add link"
affordance behind it never expires.

What is worth testing here, and why none of it is cosmetic:

1. **It changes ``post_url`` and nothing else.** This is the *only* edit in the product
   that touches an approved/published piece without resetting it to ``draft`` for
   re-moderation, because the link records reality rather than the copy. If it moved
   ``status`` or ``published_at`` it would be corrupting the record it exists to
   complete; if it reset to ``draft`` a live post would silently leave the published
   count and the Queue would offer to publish it again.
2. **Only a ``published`` piece.** A link on a draft is a claim that it went out.
   ``not_published``, deliberately a different code from ``not_approved``.
3. **The link goes through the same shape check as every user-supplied URL** — it is
   rendered as a link and opened in a new tab by colleagues.
4. **Nothing is written on a refusal.** A 400 or 409 that still persisted the link
   would be worthless.

The capability split (``member`` yes, ``viewer`` no) is here too, since this route is
the only holder of ``publish.manual`` besides ``mark-posted``. The cross-org case lives
in ``test_tenancy_routers.py`` with the rest of the per-router isolation suite.
"""

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from agency.models.tables import ContentPiece
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

#: Roles that hold ``publish.manual``, and the one that does not. A ``member`` may
#: record where a post ended up: nothing is sent anywhere and they already hold
#: ``content.approve``. A ``viewer`` may not — it is still a write.
ALLOWED_ROLES = ["owner", "admin", "member"]
DENIED_ROLES = ["viewer"]

FORBIDDEN = {"code": "insufficient_permissions", "required": "publish.manual"}


def _url(content_id: UUID) -> str:
    return f"{API}/publishing/{content_id}/post-url"


@pytest.fixture
def no_real_publish(monkeypatch):
    """Fail the test if anything reaches a real platform publisher.

    Installed on the success paths too: this route is pure bookkeeping, and a link
    patch that somehow re-posted the piece would be the worst possible bug here.
    """
    from agency.services.publishing import publisher

    async def _boom(*_a: Any, **_k: Any) -> dict:
        raise AssertionError("publisher reached by post-url patch")

    monkeypatch.setattr(publisher, "publish", _boom)


@pytest.fixture
def link_checks(monkeypatch):
    """Record the links handed to the shape check, keeping its real behaviour.

    ``assert_safe_link`` needs no network (unlike ``assert_public_url``, which resolves
    the host — the reason this route must not use it: a link pasted from a phone can be
    momentarily unresolvable and is still a perfectly good record). So this spies rather
    than stubs, and an unsafe link still earns its 400.
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
    """An org with a *manual* LinkedIn channel and an owner."""
    org_id = await create_org(session_factory, "Link Later Org")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=10)
    client_id = await create_client_row(session_factory, org_id, "Link Later Brand")
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


async def _posted(session_factory, tenant, **kwargs: Any) -> UUID:
    """A piece already recorded as manually posted, with no link."""
    from datetime import UTC, datetime

    metadata = {
        "publish_mode": "manual",
        "posted_by": str(uuid4()),
        "post_url": None,
        "moderation": {"status": "passed"},
    }
    metadata.update(kwargs.pop("metadata", {}))
    content_id = await create_content_row(
        session_factory,
        tenant.org_id,
        tenant.client_id,
        status="published",
        metadata=metadata,
        **kwargs,
    )
    async with session_factory() as s:
        row = await s.get(ContentPiece, content_id)
        assert row is not None
        row.published_at = datetime.now(UTC)
        await s.commit()
    return content_id


# ---------------------------------------------------------------------------
# Success — and the record it must not disturb
# ---------------------------------------------------------------------------
async def test_attaching_a_link_changes_only_the_link(
    client, session_factory, tenant, no_real_publish, link_checks
):
    """The whole point of the route, and the whole risk of it.

    Every other edit to an approved or published piece is either refused or resets it
    to ``draft`` for re-moderation. This one does not, because the link is a record of
    reality rather than the copy — so the test pins that it also leaves the rest of the
    record untouched.
    """
    content_id = await _posted(session_factory, tenant)
    before = await _piece(session_factory, content_id)
    published_at = before.published_at
    body, hashtags = before.body, list(before.hashtags or [])

    resp = await client.patch(
        _url(content_id), json={"post_url": POST_URL}, headers=tenant.headers
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"content_id": str(content_id), "post_url": POST_URL}

    piece = await _piece(session_factory, content_id)
    assert (piece.metadata_ or {})["post_url"] == POST_URL
    # Not reset, not re-dated, not re-moderated, and the copy is the copy that went out.
    assert piece.status == "published"
    assert piece.published_at == published_at
    assert piece.body == body
    assert list(piece.hashtags or []) == hashtags
    # The rest of the manual record survives the merge.
    assert (piece.metadata_ or {})["publish_mode"] == "manual"
    assert (piece.metadata_ or {})["moderation"] == {"status": "passed"}
    # Attributable: self-reported, so who reported it is part of it.
    assert UUID((piece.metadata_ or {})["post_url_by"])
    assert link_checks == [POST_URL]


async def test_a_link_can_be_corrected(client, session_factory, tenant, no_real_publish):
    """"Add link" never expires, and neither does "fix the link I pasted wrong"."""
    content_id = await _posted(session_factory, tenant, metadata={"post_url": POST_URL})
    other = "https://x.com/acme/status/42"

    resp = await client.patch(_url(content_id), json={"post_url": other}, headers=tenant.headers)

    assert resp.status_code == 200, resp.text
    assert ((await _piece(session_factory, content_id)).metadata_ or {})["post_url"] == other


async def test_a_product_published_post_can_also_be_linked(
    client, session_factory, tenant, no_real_publish
):
    """Nothing about this route is manual-only. A post the product published has its
    URL from the platform response, but if that came back empty the operator can still
    supply it — and the gate is "is it live", not "how did it get there"."""
    content_id = await _posted(
        session_factory, tenant, metadata={"publish_mode": None, "post_id": "p1"}
    )

    resp = await client.patch(
        _url(content_id), json={"post_url": POST_URL}, headers=tenant.headers
    )

    assert resp.status_code == 200, resp.text
    assert ((await _piece(session_factory, content_id)).metadata_ or {})["post_url"] == POST_URL


# ---------------------------------------------------------------------------
# Only a published piece
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_status", ["draft", "approved", "scheduled", "failed", "rejected"])
async def test_a_piece_that_is_not_live_is_409(
    client, session_factory, tenant, no_real_publish, bad_status
):
    """A link on anything but a live post is a claim that it went out. ``not_published``
    is its own code — "not live yet" and "never approved" are different problems."""
    content_id = await create_content_row(
        session_factory, tenant.org_id, tenant.client_id, status=bad_status
    )

    resp = await client.patch(
        _url(content_id), json={"post_url": POST_URL}, headers=tenant.headers
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "not_published", "status": bad_status}

    piece = await _piece(session_factory, content_id)
    assert piece.status == bad_status
    assert "post_url" not in (piece.metadata_ or {})


async def test_unknown_content_id_is_404(client, session_factory, tenant, no_real_publish):
    resp = await client.patch(_url(uuid4()), json={"post_url": POST_URL}, headers=tenant.headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# The link gets the same shape check as every user-supplied URL
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad",
    [
        "javascript:alert(1)",
        "http://localhost/x",
        "http://127.0.0.1/x",
        "http://10.0.0.5/x",
        "file:///etc/passwd",
        "not a url",
        "",
    ],
)
async def test_an_unsafe_link_is_refused_and_writes_nothing(
    client, session_factory, tenant, no_real_publish, bad
):
    """Colleagues click this link out of the Queue. No stub — the real check runs, and
    none of these needs the network to be refused."""
    content_id = await _posted(session_factory, tenant)

    resp = await client.patch(_url(content_id), json={"post_url": bad}, headers=tenant.headers)

    assert resp.status_code == 400
    piece = await _piece(session_factory, content_id)
    assert (piece.metadata_ or {})["post_url"] is None
    assert piece.status == "published"


async def test_the_status_gate_runs_before_the_url_check(
    client, session_factory, tenant, no_real_publish
):
    """A draft with a junk link hears about the draft. Reversing the two would send the
    operator off fixing a URL on a piece that could never take one."""
    content_id = await create_content_row(
        session_factory, tenant.org_id, tenant.client_id, status="draft"
    )

    resp = await client.patch(
        _url(content_id), json={"post_url": "javascript:alert(1)"}, headers=tenant.headers
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "not_published"


# ---------------------------------------------------------------------------
# Capability gate — ``publish.manual``
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", ALLOWED_ROLES)
async def test_allowed_for_member_and_up(
    client, session_factory, tenant, no_real_publish, role
):
    headers = await auth_for(session_factory, tenant.org_id, role)
    content_id = await _posted(session_factory, tenant)

    resp = await client.patch(_url(content_id), json={"post_url": POST_URL}, headers=headers)

    assert resp.status_code == 200, resp.text
    assert ((await _piece(session_factory, content_id)).metadata_ or {})["post_url"] == POST_URL


@pytest.mark.parametrize("role", DENIED_ROLES)
async def test_denied_for_viewer(client, session_factory, tenant, no_real_publish, role):
    headers = await auth_for(session_factory, tenant.org_id, role)
    content_id = await _posted(session_factory, tenant)

    resp = await client.patch(_url(content_id), json={"post_url": POST_URL}, headers=headers)

    assert resp.status_code == 403
    assert resp.json()["detail"] == FORBIDDEN
    assert ((await _piece(session_factory, content_id)).metadata_ or {})["post_url"] is None
