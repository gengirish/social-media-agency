"""CF-17 — `workspace.manage` on the routes that change the workspace itself.

The Team page said any member could read and change everything. Most of it was
already gated (`team.manage`, `billing.manage`, `oauth.connect`,
`publish.write`, `content.approve`), but three things were not:

- archiving and restoring a client — hides or restores every campaign, post and
  connected account behind it, for everyone in the org;
- API keys — a credential that acts for the whole org through
  `routers/public_api.py`, bypassing every seat-level check;
- writing posting preferences and exporting a client's whole record.

None of these is doing the marketing work, which is what `member` is for.

Callers come from `auth_for`, which persists a real `users` row: `require_cap`
reads the role from the database and fails closed, so a token alone cannot pass.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from .conftest import auth_for, create_client_row, create_org, create_subscription

UNPRIVILEGED = ["member", "viewer"]
PRIVILEGED = ["owner", "admin"]


@pytest.fixture
async def org(session_factory):
    org_id = await create_org(session_factory, "Gate Workspace Org")
    await create_subscription(session_factory, org_id, plan_tier="growth")
    client_id = await create_client_row(session_factory, org_id, "Gated Brand")
    return org_id, client_id


# ---------------------------------------------------------------------------
# Clients: archive / restore
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", UNPRIVILEGED)
async def test_archiving_a_client_is_refused_without_workspace_manage(
    client, session_factory, org, role
):
    org_id, client_id = org
    headers = await auth_for(session_factory, org_id, role)

    resp = await client.post(f"/api/v1/clients/{client_id}/archive", headers=headers)

    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["required"] == "workspace.manage"


@pytest.mark.parametrize("role", PRIVILEGED)
async def test_archiving_a_client_is_allowed_with_workspace_manage(
    client, session_factory, org, role
):
    org_id, client_id = org
    headers = await auth_for(session_factory, org_id, role)

    resp = await client.post(f"/api/v1/clients/{client_id}/archive", headers=headers)

    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("role", UNPRIVILEGED)
async def test_restoring_a_client_is_refused_without_workspace_manage(
    client, session_factory, org, role
):
    org_id, client_id = org
    headers = await auth_for(session_factory, org_id, role)

    resp = await client.post(f"/api/v1/clients/{client_id}/restore", headers=headers)

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", UNPRIVILEGED)
async def test_minting_an_api_key_is_refused_without_workspace_manage(
    client, session_factory, org, role
):
    """The worst of the three: a key acts for the org and skips every seat check."""
    org_id, _ = org
    headers = await auth_for(session_factory, org_id, role)

    resp = await client.post(
        "/api/v1/integrations/api-keys", json={"name": "mine"}, headers=headers
    )

    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize("role", UNPRIVILEGED)
async def test_listing_api_keys_is_refused_without_workspace_manage(
    client, session_factory, org, role
):
    org_id, _ = org
    headers = await auth_for(session_factory, org_id, role)
    assert (await client.get("/api/v1/integrations/api-keys", headers=headers)).status_code == 403


@pytest.mark.parametrize("role", UNPRIVILEGED)
async def test_revoking_an_api_key_is_refused_without_workspace_manage(
    client, session_factory, org, role
):
    org_id, _ = org
    headers = await auth_for(session_factory, org_id, role)
    resp = await client.delete(f"/api/v1/integrations/api-keys/{uuid4()}", headers=headers)
    # 403 before 404: the gate runs before the row is looked up.
    assert resp.status_code == 403


async def test_an_owner_can_still_mint_a_key(client, session_factory, org):
    org_id, _ = org
    headers = await auth_for(session_factory, org_id, "owner")
    resp = await client.post(
        "/api/v1/integrations/api-keys", json={"name": "mine"}, headers=headers
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Workspace settings
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", UNPRIVILEGED)
async def test_writing_posting_prefs_is_refused_without_workspace_manage(
    client, session_factory, org, role
):
    org_id, client_id = org
    headers = await auth_for(session_factory, org_id, role)

    resp = await client.put(
        f"/api/v1/workspace/posting-prefs?client_id={client_id}",
        json={"voice_register": "Bold & punchy"},
        headers=headers,
    )

    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize("role", UNPRIVILEGED)
async def test_reading_posting_prefs_stays_open(client, session_factory, org, role):
    """A member writes to this cadence and voice — they need to be able to see it."""
    org_id, client_id = org
    headers = await auth_for(session_factory, org_id, role)

    resp = await client.get(
        f"/api/v1/workspace/posting-prefs?client_id={client_id}", headers=headers
    )

    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("role", UNPRIVILEGED)
async def test_exporting_a_client_is_refused_without_workspace_manage(
    client, session_factory, org, role
):
    org_id, client_id = org
    headers = await auth_for(session_factory, org_id, role)
    resp = await client.get(f"/api/v1/workspace/export?client_id={client_id}", headers=headers)
    assert resp.status_code == 403
