"""Capability gates on ``POST /content/{id}/approve`` (RBAC phase 2C).

Two checks, deliberately split, and the split *is* the feature:

* ``content.approve`` gates the route. A ``viewer`` cannot approve anything.
* ``content.override`` is checked inside the handler, only on ``?override=true``.
  A ``member`` is a human and product rule 2 wants a human to approve, so a member
  may approve clean copy — but overriding a moderation flag puts unreviewed copy on
  a live client account, so that stays with ``owner`` / ``admin``.

Every refusal test asserts the row did not move as well as the status code: a 403
raised after the piece was already approved would not be a gate.

Moderation behaviour is untouched here — ``test_approval_gate.py`` owns it and must
stay green. The brain-tier LLM is stubbed; no test touches a real provider.
"""

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select

from agency.models.tables import ContentPiece
from tests.conftest import (
    auth_for,
    auth_header_for,
    create_client_row,
    create_content_row,
    create_org,
    create_subscription,
)

API = "/api/v1"
CLEAN = '{"issues": []}'
FLAGGED = (
    '{"issues": [{"severity": "high", "message": "Guarantees a 3x ROI with no evidence."}]}'
)


class StubLLM:
    """Brain-tier stand-in; records every prompt it is handed."""

    def __init__(self, reply: str = CLEAN):
        self.reply = reply
        self.prompts: list[Any] = []

    async def ainvoke(self, prompt: Any) -> SimpleNamespace:
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.reply)


@pytest.fixture
def brain(monkeypatch):
    def _install(reply: str = CLEAN) -> StubLLM:
        stub = StubLLM(reply)
        monkeypatch.setattr(
            "agency.services.llm_provider.get_brain_llm", lambda *a, **k: stub
        )
        return stub

    return _install


@pytest.fixture
async def tenant(session_factory):
    org_id = await create_org(session_factory, "Gate Content Org")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org_id, "Gate Content Brand")
    return SimpleNamespace(org_id=org_id, client_id=client_id)


async def _status(session_factory, content_id: UUID) -> str:
    async with session_factory() as s:
        row = (
            await s.execute(select(ContentPiece).where(ContentPiece.id == content_id))
        ).scalar_one()
        return str(row.status)


async def _piece(session_factory, tenant) -> UUID:
    return await create_content_row(session_factory, tenant.org_id, tenant.client_id)


def _assert_forbidden(resp, required: str) -> None:
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == {
        "code": "insufficient_permissions",
        "required": required,
    }


# ---------------------------------------------------------------------------
# content.approve — the route-level gate
# ---------------------------------------------------------------------------
async def test_viewer_cannot_approve(client, session_factory, tenant, brain):
    stub = brain(CLEAN)
    headers = await auth_for(session_factory, tenant.org_id, "viewer")
    content_id = await _piece(session_factory, tenant)

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=headers)

    _assert_forbidden(resp, "content.approve")
    assert await _status(session_factory, content_id) == "draft"
    assert stub.prompts == []  # refused before moderation ever ran


async def test_caller_without_a_user_row_cannot_approve(
    client, session_factory, tenant, brain
):
    """Fails closed: a valid token whose ``sub`` has no row gets nothing."""
    brain(CLEAN)
    content_id = await _piece(session_factory, tenant)

    resp = await client.post(
        f"{API}/content/{content_id}/approve",
        headers=auth_header_for(tenant.org_id, "owner"),
    )

    _assert_forbidden(resp, "content.approve")
    assert await _status(session_factory, content_id) == "draft"


@pytest.mark.parametrize("role", ["member", "admin", "owner"])
async def test_member_admin_owner_can_approve(client, session_factory, tenant, brain, role):
    stub = brain(CLEAN)
    headers = await auth_for(session_factory, tenant.org_id, role)
    content_id = await _piece(session_factory, tenant)

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    assert resp.json()["moderation"]["status"] == "passed"
    assert len(stub.prompts) == 1  # moderation still runs for every role
    assert await _status(session_factory, content_id) == "approved"


# ---------------------------------------------------------------------------
# content.override — the in-handler gate on ?override=true
# ---------------------------------------------------------------------------
async def test_member_cannot_override(client, session_factory, tenant, brain):
    """The point of the whole task: approve yes, override no."""
    stub = brain(FLAGGED)
    headers = await auth_for(session_factory, tenant.org_id, "member")
    content_id = await _piece(session_factory, tenant)

    resp = await client.post(
        f"{API}/content/{content_id}/approve?override=true", headers=headers
    )

    _assert_forbidden(resp, "content.override")
    # A gate that 403s *after* mutating is not a gate.
    assert await _status(session_factory, content_id) == "draft"
    assert stub.prompts == []


async def test_viewer_override_is_refused_on_approve_first(
    client, session_factory, tenant, brain
):
    """A viewer holds neither capability; the route-level one answers first."""
    brain(FLAGGED)
    headers = await auth_for(session_factory, tenant.org_id, "viewer")
    content_id = await _piece(session_factory, tenant)

    resp = await client.post(
        f"{API}/content/{content_id}/approve?override=true", headers=headers
    )

    _assert_forbidden(resp, "content.approve")
    assert await _status(session_factory, content_id) == "draft"


@pytest.mark.parametrize("role", ["admin", "owner"])
async def test_admin_and_owner_can_override_a_flag(
    client, session_factory, tenant, brain, role
):
    brain(FLAGGED)
    headers = await auth_for(session_factory, tenant.org_id, role)
    content_id = await _piece(session_factory, tenant)

    # Without the flag the piece is refused — moderation behaviour is unchanged.
    refused = await client.post(f"{API}/content/{content_id}/approve", headers=headers)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "moderation_flagged"
    assert await _status(session_factory, content_id) == "draft"

    resp = await client.post(
        f"{API}/content/{content_id}/approve?override=true", headers=headers
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    assert resp.json()["moderation"]["status"] == "overridden"
    assert await _status(session_factory, content_id) == "approved"


async def test_member_can_still_approve_after_being_refused_an_override(
    client, session_factory, tenant, brain
):
    """The override refusal leaves the piece approvable — it is a gate, not a wedge."""
    brain(CLEAN)
    headers = await auth_for(session_factory, tenant.org_id, "member")
    content_id = await _piece(session_factory, tenant)

    refused = await client.post(
        f"{API}/content/{content_id}/approve?override=true", headers=headers
    )
    _assert_forbidden(refused, "content.override")

    ok = await client.post(f"{API}/content/{content_id}/approve", headers=headers)
    assert ok.status_code == 200, ok.text
    assert await _status(session_factory, content_id) == "approved"


async def test_personal_account_member_is_unchanged(client, session_factory, brain):
    """``account_type`` subtracts nothing — a personal org's member behaves identically."""
    brain(CLEAN)
    org_id = await create_org(session_factory, "Solo Org", account_type="personal")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org_id, "Solo Brand")
    headers = await auth_for(session_factory, org_id, "member", account_type="personal")
    content_id = await create_content_row(session_factory, org_id, client_id)

    ok = await client.post(f"{API}/content/{content_id}/approve", headers=headers)
    assert ok.status_code == 200, ok.text

    second = await create_content_row(session_factory, org_id, client_id)
    denied = await client.post(
        f"{API}/content/{second}/approve?override=true", headers=headers
    )
    _assert_forbidden(denied, "content.override")
    assert await _status(session_factory, second) == "draft"
