"""Quota-enforcement tests.

Covers both the service-level check and the two HTTP surfaces that gate on
usage: campaign creation (campaigns/mo) and publishing (posts/mo). A blocked
request must return HTTP 402; an allowed request must get past the quota gate.
"""

from datetime import date

from agency.services.billing import PLAN_CONFIG
from tests.conftest import (
    auth_header_for,
    create_campaign_row,
    create_client_row,
    create_content_row,
    create_org,
    create_subscription,
)

API = "/api/v1"


def _brief(client_id):
    return {
        "client_id": str(client_id),
        "campaign_name": "Launch Q3",
        "objective": "Drive signups for the new launch",
        "channels": ["linkedin"],
        "start_date": date.today().isoformat(),
        "end_date": date.today().isoformat(),
    }


# ---------------------------------------------------------------------------
# Campaign creation quota (campaigns_limit)
# ---------------------------------------------------------------------------
async def test_campaign_creation_blocked_at_limit(client, session_factory):
    org_id = await create_org(session_factory, "CampCapped")
    await create_subscription(session_factory, org_id, plan_tier="free")
    client_id = await create_client_row(session_factory, org_id)

    limit = PLAN_CONFIG["free"]["campaigns_limit"]  # 5
    for i in range(limit):
        await create_campaign_row(session_factory, org_id, client_id, name=f"c{i}")

    resp = await client.post(
        f"{API}/campaigns", json=_brief(client_id), headers=auth_header_for(org_id)
    )
    assert resp.status_code == 402
    assert "limit" in resp.json()["detail"].lower()


async def test_campaign_creation_allowed_under_limit(client, session_factory, monkeypatch):
    # Neutralise the fire-and-forget LangGraph pipeline background task.
    async def _noop(**kwargs):
        return None

    monkeypatch.setattr("agency.routers.campaigns._run_campaign_pipeline", _noop)

    org_id = await create_org(session_factory, "CampOk")
    await create_subscription(session_factory, org_id, plan_tier="free")
    client_id = await create_client_row(session_factory, org_id)

    resp = await client.post(
        f"{API}/campaigns", json=_brief(client_id), headers=auth_header_for(org_id)
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "running"


# ---------------------------------------------------------------------------
# Publishing quota (posts_limit)
# ---------------------------------------------------------------------------
async def test_publish_blocked_when_posts_quota_exhausted(client, session_factory):
    org_id = await create_org(session_factory, "PubCapped")
    await create_subscription(session_factory, org_id, posts_limit=30, posts_used=30)
    client_id = await create_client_row(session_factory, org_id)
    content_id = await create_content_row(session_factory, org_id, client_id)

    resp = await client.post(
        f"{API}/publishing/{content_id}/publish", headers=auth_header_for(org_id)
    )
    assert resp.status_code == 402
    assert "limit" in resp.json()["detail"].lower()


async def test_publish_passes_quota_gate_under_limit(client, session_factory):
    # Under the limit the quota gate is passed; the request then fails on the
    # *next* check (no connected platform account -> 400), which proves it was
    # NOT blocked by quota (would be 402).
    org_id = await create_org(session_factory, "PubOk")
    await create_subscription(session_factory, org_id, posts_limit=30, posts_used=0)
    client_id = await create_client_row(session_factory, org_id)
    content_id = await create_content_row(session_factory, org_id, client_id)

    resp = await client.post(
        f"{API}/publishing/{content_id}/publish", headers=auth_header_for(org_id)
    )
    assert resp.status_code != 402
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Service-level boundary (mirrors the HTTP gate logic)
# ---------------------------------------------------------------------------
async def test_service_check_quota_boundary(session_factory):
    from sqlalchemy import select

    from agency.models.tables import Subscription
    from agency.services.billing import BillingService

    org_id = await create_org(session_factory, "Boundary")
    await create_subscription(session_factory, org_id, posts_limit=2, posts_used=1)
    svc = BillingService()

    # Fresh session per assertion to avoid identity-map staleness.
    async with session_factory() as s1:
        assert await svc.check_quota(s1, org_id) is True

    async with session_factory() as s2:
        sub = (
            await s2.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        sub.posts_used = 2
        await s2.commit()

    async with session_factory() as s3:
        assert await svc.check_quota(s3, org_id) is False
