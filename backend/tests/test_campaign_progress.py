"""``GET /campaigns/{id}/progress`` — the durable replacement for SSE replay.

The stream is single-consumer and drops its queue when a run ends, so the browser
loses the whole pipeline view on any reconnect (tab switch, remount, refresh).
This endpoint reads the state back from ``agent_run`` rows instead; these tests
pin the three things the dashboard depends on: prior-run rows must not be
reported as the current run's progress, the review pause must be visible even
though ``human_review`` never writes a row, and another tenant must get a 404.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from tests.conftest import (
    auth_for,
    create_campaign_row,
    create_client_row,
    create_org,
)

API = "/api/v1"


async def _add_runs(session_factory, org_id, campaign_id, names, *, base=None, status="completed"):
    from agency.models.tables import AgentRun

    start = base or datetime.now(UTC)
    async with session_factory() as s:
        for i, name in enumerate(names):
            s.add(
                AgentRun(
                    id=uuid4(),
                    campaign_id=UUID(str(campaign_id)),
                    org_id=UUID(str(org_id)),
                    agent_name=name,
                    status=status,
                    created_at=start + timedelta(seconds=i),
                )
            )
        await s.commit()


async def _setup(session_factory, status="running"):
    org = await create_org(session_factory, "Progress Org")
    client_id = await create_client_row(session_factory, org, "Brand")
    campaign_id = await create_campaign_row(session_factory, org, client_id, status=status)
    return org, campaign_id


async def test_progress_reports_completed_agents(client, session_factory):
    org, campaign_id = await _setup(session_factory)
    await _add_runs(session_factory, org, campaign_id, ["orchestrate", "strategise"])

    resp = await client.get(
        f"{API}/campaigns/{campaign_id}/progress", headers=await auth_for(session_factory, org)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent_statuses"]["orchestrate"] == "complete"
    assert body["agent_statuses"]["strategise"] == "complete"
    assert body["progress"] == 22  # 2 of 9 nodes
    assert body["campaign_status"] == "running"


async def test_progress_ignores_the_previous_run(client, session_factory):
    """A re-run starts at orchestrate again; the old run's rows must not count."""
    org, campaign_id = await _setup(session_factory)
    old = datetime.now(UTC) - timedelta(hours=1)
    await _add_runs(
        session_factory,
        org,
        campaign_id,
        ["orchestrate", "strategise", "seo_research", "create_content", "write_ads"],
        base=old,
    )
    await _add_runs(session_factory, org, campaign_id, ["orchestrate"])

    resp = await client.get(
        f"{API}/campaigns/{campaign_id}/progress", headers=await auth_for(session_factory, org)
    )
    body = resp.json()
    assert set(body["agent_statuses"]) == {"orchestrate"}
    assert body["progress"] == 11


async def test_progress_surfaces_the_review_pause(client, session_factory):
    """The graph interrupts *before* human_review, so that node never writes a row."""
    org, campaign_id = await _setup(session_factory)
    await _add_runs(
        session_factory,
        org,
        campaign_id,
        ["orchestrate", "strategise", "seo_research", "create_content", "write_ads"],
    )

    resp = await client.get(
        f"{API}/campaigns/{campaign_id}/progress", headers=await auth_for(session_factory, org)
    )
    assert resp.json()["agent_statuses"]["human_review"] == "waiting"


async def test_progress_marks_failed_runs(client, session_factory):
    org, campaign_id = await _setup(session_factory, status="failed")
    await _add_runs(session_factory, org, campaign_id, ["orchestrate"])
    await _add_runs(session_factory, org, campaign_id, ["strategise"], status="failed")

    body = (
        await client.get(
            f"{API}/campaigns/{campaign_id}/progress", headers=await auth_for(session_factory, org)
        )
    ).json()
    assert body["agent_statuses"]["strategise"] == "error"


async def test_progress_rejects_other_orgs_campaign(client, session_factory):
    org, campaign_id = await _setup(session_factory)
    await _add_runs(session_factory, org, campaign_id, ["orchestrate"])
    other = await create_org(session_factory, "Other Org")

    resp = await client.get(
        f"{API}/campaigns/{campaign_id}/progress", headers=await auth_for(session_factory, other)
    )
    assert resp.status_code == 404
