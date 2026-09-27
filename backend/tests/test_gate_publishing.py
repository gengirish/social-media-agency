"""Capability gates on the publishing router — ``publish.write``.

Publishing here is real: ``POST /publishing/{id}/publish`` posts to a client's live
social account and ``POST /publishing/{id}/schedule`` hands the piece to the background
scheduler, which publishes it unattended when it comes due. Both therefore require
``Capability.PUBLISH_WRITE``, which only ``owner`` and ``admin`` hold.

**This is the row where ``member`` is deliberately denied.** A member *may* approve copy
(``content.approve`` is theirs — approval is a human saying the wording is fine, and a
member is a human), but may not push it to a live account. Every test below that names
``member`` exists to keep that distinction from being quietly widened.

The capability gate sits in *front* of the existing approval gate, it does not replace
it: ``test_approval_gate.py`` still owns "only approved content may be published". Here
the content is always ``approved`` and the platform account always connected, so the only
thing that can produce a 403 is the capability check itself.

No test reaches a real publisher: ``no_real_publish`` replaces ``publisher.publish`` and
fails the test outright if a denied caller somehow got through.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from agency.models.tables import ContentPiece
from tests.conftest import (
    auth_for,
    auth_header_for,
    create_client_row,
    create_content_row,
    create_org,
    create_platform_account,
    create_subscription,
)

API = "/api/v1"

FORBIDDEN = {"code": "insufficient_permissions", "required": "publish.write"}

#: Roles that hold ``publish.write`` and the ones that do not. ``member`` is in the
#: denied list on purpose — see the module docstring.
ALLOWED_ROLES = ["owner", "admin"]
DENIED_ROLES = ["member", "viewer"]


@pytest.fixture
def no_real_publish(monkeypatch):
    """Fail the test if anything reaches a real platform publisher."""
    from agency.services.publishing import publisher

    async def _boom(*args, **kwargs):
        raise AssertionError("publisher reached by a caller without publish.write")

    monkeypatch.setattr(publisher, "publish", _boom)


@pytest.fixture
def fake_publish(monkeypatch):
    """A publisher stub that reports success, for the allowed-role paths."""
    from agency.services.publishing import publisher

    calls: list[tuple] = []

    async def _ok(platform, content_data, credentials):
        calls.append((platform, content_data, credentials))
        return {"success": True, "post_id": "p1", "url": "https://example.test/p1"}

    monkeypatch.setattr(publisher, "publish", _ok)
    return calls


@pytest.fixture
async def tenant(session_factory):
    """An org with a connected LinkedIn account and room in its plan."""
    org_id = await create_org(session_factory, "Publish Gate Org")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org_id, "Gate Brand")
    await create_platform_account(session_factory, org_id, client_id, platform="linkedin")
    return SimpleNamespace(org_id=org_id, client_id=client_id)


async def _approved_piece(session_factory, tenant) -> UUID:
    return await create_content_row(
        session_factory, tenant.org_id, tenant.client_id, status="approved"
    )


async def _piece(session_factory, content_id: UUID) -> ContentPiece:
    async with session_factory() as s:
        return (
            await s.execute(select(ContentPiece).where(ContentPiece.id == content_id))
        ).scalar_one()


def _when() -> str:
    return (datetime.now(UTC) + timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# POST /publishing/{id}/publish
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", DENIED_ROLES)
async def test_publish_denied_for_member_and_viewer(
    client, session_factory, tenant, no_real_publish, role
):
    """A member may approve copy but may not push it to a live account."""
    headers = await auth_for(session_factory, tenant.org_id, role)
    content_id = await _approved_piece(session_factory, tenant)

    resp = await client.post(f"{API}/publishing/{content_id}/publish", headers=headers)

    assert resp.status_code == 403
    assert resp.json()["detail"] == FORBIDDEN
    # The gate has to stop the *effect*, not merely return a status.
    assert (await _piece(session_factory, content_id)).status == "approved"


@pytest.mark.parametrize("role", ALLOWED_ROLES)
async def test_publish_allowed_for_owner_and_admin(
    client, session_factory, tenant, fake_publish, role
):
    headers = await auth_for(session_factory, tenant.org_id, role)
    content_id = await _approved_piece(session_factory, tenant)

    resp = await client.post(f"{API}/publishing/{content_id}/publish", headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "published"
    assert (await _piece(session_factory, content_id)).status == "published"
    assert len(fake_publish) == 1


async def test_publish_gate_runs_before_the_content_lookup(
    client, session_factory, tenant, no_real_publish
):
    """A denied caller gets 403, not 404 — the gate must not double as an oracle
    for which content ids exist in the org."""
    headers = await auth_for(session_factory, tenant.org_id, "viewer")

    resp = await client.post(f"{API}/publishing/{uuid4()}/publish", headers=headers)

    assert resp.status_code == 403
    assert resp.json()["detail"] == FORBIDDEN


async def test_publish_denied_without_a_user_row(
    client, session_factory, tenant, no_real_publish
):
    """``auth_header_for`` mints an owner token with no ``users`` row behind it.
    The gate reads the database and fails closed, so the claim buys nothing."""
    content_id = await _approved_piece(session_factory, tenant)

    resp = await client.post(
        f"{API}/publishing/{content_id}/publish",
        headers=auth_header_for(tenant.org_id, "owner"),
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == FORBIDDEN


# ---------------------------------------------------------------------------
# POST /publishing/{id}/schedule
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", DENIED_ROLES)
async def test_schedule_denied_for_member_and_viewer(
    client, session_factory, tenant, no_real_publish, role
):
    """Scheduling is publishing with a delay — a member is denied it for the same
    reason: the scheduler posts to the live account unattended when it comes due."""
    headers = await auth_for(session_factory, tenant.org_id, role)
    content_id = await _approved_piece(session_factory, tenant)

    resp = await client.post(
        f"{API}/publishing/{content_id}/schedule",
        json={"scheduled_at": _when()},
        headers=headers,
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == FORBIDDEN
    piece = await _piece(session_factory, content_id)
    assert piece.status == "approved"
    assert piece.scheduled_at is None


@pytest.mark.parametrize("role", ALLOWED_ROLES)
async def test_schedule_allowed_for_owner_and_admin(client, session_factory, tenant, role):
    headers = await auth_for(session_factory, tenant.org_id, role)
    content_id = await _approved_piece(session_factory, tenant)

    resp = await client.post(
        f"{API}/publishing/{content_id}/schedule",
        json={"scheduled_at": _when()},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    piece = await _piece(session_factory, content_id)
    assert piece.status == "scheduled"
    assert piece.scheduled_at is not None


async def test_schedule_denied_without_a_user_row(client, session_factory, tenant):
    content_id = await _approved_piece(session_factory, tenant)

    resp = await client.post(
        f"{API}/publishing/{content_id}/schedule",
        json={"scheduled_at": _when()},
        headers=auth_header_for(tenant.org_id, "owner"),
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == FORBIDDEN
    assert (await _piece(session_factory, content_id)).scheduled_at is None


# ---------------------------------------------------------------------------
# The capability gate is additional, not a replacement
# ---------------------------------------------------------------------------
async def test_approval_gate_still_applies_to_a_privileged_caller(
    client, session_factory, tenant, no_real_publish
):
    """An owner holds ``publish.write`` and still cannot publish a draft: the
    capability gate sits in front of the approval gate, it does not swallow it."""
    headers = await auth_for(session_factory, tenant.org_id, "owner")
    content_id = await create_content_row(
        session_factory, tenant.org_id, tenant.client_id, status="draft"
    )

    resp = await client.post(f"{API}/publishing/{content_id}/publish", headers=headers)

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "not_approved"
    assert (await _piece(session_factory, content_id)).status == "draft"


async def test_gate_denies_a_caller_whose_row_lives_in_another_org(
    client, session_factory, tenant, no_real_publish
):
    """An owner of a *different* org gets no capabilities here — the gate matches
    the ``users`` row on both id and org, because there is no RLS in this database."""
    other_org = await create_org(session_factory, "Other Org")
    other = await auth_for(session_factory, other_org, "owner")
    # Re-point the token at the target org while keeping the foreign ``sub``.
    from jose import jwt

    from tests.conftest import JWT_SECRET

    claims = jwt.decode(other["Authorization"].split()[1], JWT_SECRET, algorithms=["HS256"])
    forged = jwt.encode({**claims, "org_id": str(tenant.org_id)}, JWT_SECRET, algorithm="HS256")

    content_id = await _approved_piece(session_factory, tenant)
    resp = await client.post(
        f"{API}/publishing/{content_id}/publish",
        headers={"Authorization": f"Bearer {forged}"},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == FORBIDDEN
    assert (await _piece(session_factory, content_id)).status == "approved"


# ---------------------------------------------------------------------------
# GET /publishing/calendar stays ungated beyond ``read``
# ---------------------------------------------------------------------------
async def test_calendar_stays_readable_by_a_viewer(client, session_factory, tenant):
    """Only the two write routes are gated; a viewer can still see the calendar."""
    headers = await auth_for(session_factory, tenant.org_id, "viewer")
    start = datetime.now(UTC).isoformat()
    end = (datetime.now(UTC) + timedelta(days=7)).isoformat()

    resp = await client.get(
        f"{API}/publishing/calendar", params={"start": start, "end": end}, headers=headers
    )

    assert resp.status_code == 200
    assert "items" in resp.json()
