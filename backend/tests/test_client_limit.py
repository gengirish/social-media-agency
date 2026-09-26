"""CF-11 — the plan's client allowance is enforced when a client is created.

The Free plan advertises "1 client" and four existed: the limit was stored on
the subscription and never checked. The campaign limit was enforced in
`campaigns.py`; this was the matching gap.

Orgs already over the limit are deliberately grandfathered — see
`test_an_org_already_over_the_limit_keeps_its_clients`.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from agency.models.tables import Client
from tests.conftest import (
    auth_header_for,
    create_client_row,
    create_org,
    create_subscription,
    create_user_row,
)

API = "/api/v1/clients"
NEW = {"brand_name": "Second Brand", "industry": "SaaS"}


@pytest.fixture
async def free_org(session_factory):
    org_id = await create_org(session_factory, "Free Org")
    await create_subscription(session_factory, org_id, plan_tier="free")
    user_id = await create_user_row(session_factory, org_id)
    return SimpleNamespace(
        org_id=org_id, user_id=user_id, headers=auth_header_for(org_id, user_id=user_id)
    )


async def _active_count(session_factory, org_id) -> int:
    async with session_factory() as db:
        return (
            await db.execute(
                select(func.count(Client.id)).where(
                    Client.org_id == org_id, Client.is_active.is_(True)
                )
            )
        ).scalar() or 0


async def test_the_first_client_is_allowed_on_free(client, free_org):
    resp = await client.post(API, json=NEW, headers=free_org.headers)
    assert resp.status_code == 201, resp.text


async def test_a_second_client_on_free_is_refused_with_an_upgrade_message(
    client, session_factory, free_org
):
    await create_client_row(session_factory, free_org.org_id, "First Brand")

    resp = await client.post(API, json=NEW, headers=free_org.headers)

    assert resp.status_code == 402, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "client_limit_reached"
    assert detail["limit"] == 1
    assert detail["plan_tier"] == "free"
    # The message has to say what to do, not just that something is wrong.
    assert "Upgrade" in detail["message"] or "archive" in detail["message"]
    # And nothing was written.
    assert await _active_count(session_factory, free_org.org_id) == 1


async def test_an_archived_client_frees_a_slot(client, session_factory, free_org):
    """Archiving is the way out of the limit without paying, so it must work."""
    client_id = await create_client_row(session_factory, free_org.org_id, "First Brand")
    async with session_factory() as db:
        (await db.get(Client, client_id)).is_active = False
        await db.commit()

    resp = await client.post(API, json=NEW, headers=free_org.headers)
    assert resp.status_code == 201, resp.text


async def test_a_higher_plan_allows_more(client, session_factory):
    org_id = await create_org(session_factory, "Growth Org")
    await create_subscription(session_factory, org_id, plan_tier="growth")
    user_id = await create_user_row(session_factory, org_id)
    headers = auth_header_for(org_id, user_id=user_id)
    for i in range(3):
        await create_client_row(session_factory, org_id, f"Brand {i}")

    resp = await client.post(API, json=NEW, headers=headers)
    assert resp.status_code == 201, resp.text


async def test_an_org_already_over_the_limit_keeps_its_clients(
    client, session_factory, free_org
):
    """Grandfathering, deliberately.

    Four clients exist on a Free plan because the limit was never enforced while
    they were created. Making them read-only would punish the org for our bug;
    only *new* clients are refused.
    """
    for i in range(4):
        await create_client_row(session_factory, free_org.org_id, f"Existing {i}")

    listed = await client.get(API, headers=free_org.headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 4

    # Editing one still works.
    existing_id = listed.json()["items"][0]["id"]
    edited = await client.patch(
        f"{API}/{existing_id}", json={"description": "still editable"}, headers=free_org.headers
    )
    assert edited.status_code == 200, edited.text

    # Only adding a fifth is refused.
    assert (await client.post(API, json=NEW, headers=free_org.headers)).status_code == 402


async def test_another_orgs_clients_do_not_count_towards_the_limit(
    client, session_factory, free_org
):
    """The count must be org-scoped, or one busy tenant blocks every other."""
    other_org = await create_org(session_factory, "Other Org")
    for i in range(5):
        await create_client_row(session_factory, other_org, f"Theirs {i}")

    resp = await client.post(API, json=NEW, headers=free_org.headers)
    assert resp.status_code == 201, resp.text
