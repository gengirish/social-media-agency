"""``POST /campaigns/{id}/rerun`` — restart the agent pipeline on an existing campaign.

The graph and the background pipeline task are faked: what matters here is that the
old checkpoint is discarded, the original brief is carried into the new run, and the
endpoint refuses other tenants' campaigns and campaigns that are mid-run.
"""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from tests.conftest import (
    auth_header_for,
    create_campaign_row,
    create_client_row,
    create_org,
)

API = "/api/v1"


class _FakeCheckpointer:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


class _FakeGraph:
    def __init__(self, values: dict[str, Any] | None) -> None:
        self.values = values
        self.checkpointer = _FakeCheckpointer()

    async def aget_state(self, config: dict) -> Any:
        return SimpleNamespace(values=self.values or {})


@pytest.fixture
def fake_runtime(monkeypatch):
    """Swap in a fake graph and capture the pipeline launch instead of running it."""
    from agency.routers import campaigns as campaigns_router

    launched: list[dict[str, Any]] = []

    async def _fake_pipeline(**kwargs: Any) -> None:
        launched.append(kwargs)

    state = SimpleNamespace(graph=_FakeGraph(None), launched=launched)
    monkeypatch.setattr(campaigns_router, "get_runtime_compiled_graph", lambda: state.graph)
    monkeypatch.setattr(campaigns_router, "_run_campaign_pipeline", _fake_pipeline)
    yield state
    campaigns_router._active_pipelines.clear()
    campaigns_router._campaign_streams.clear()


async def _setup(session_factory, status: str = "failed"):
    org = await create_org(session_factory, "Rerun Org")
    client_id = await create_client_row(session_factory, org, "Brand")
    campaign_id = await create_campaign_row(session_factory, org, client_id, status=status)
    return org, campaign_id


async def test_rerun_restarts_pipeline_with_checkpointed_brief(
    client, session_factory, fake_runtime
):
    from agency.models.tables import Campaign

    org, campaign_id = await _setup(session_factory, status="failed")
    fake_runtime.graph = _FakeGraph(
        {"client_brief": "Target Audience: CFOs", "target_languages": ["es"]}
    )

    resp = await client.post(f"{API}/campaigns/{campaign_id}/rerun", headers=auth_header_for(org))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"

    await asyncio.sleep(0)  # let the create_task'd fake pipeline run
    assert fake_runtime.graph.checkpointer.deleted == [str(campaign_id)]
    assert len(fake_runtime.launched) == 1
    run = fake_runtime.launched[0]
    assert run["brief_text"] == "Target Audience: CFOs"
    assert run["target_languages"] == ["es"]

    async with session_factory() as s:
        row = (await s.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one()
        assert row.status == "running"


async def test_rerun_rebuilds_brief_when_checkpoint_missing(client, session_factory, fake_runtime):
    org, campaign_id = await _setup(session_factory)

    resp = await client.post(f"{API}/campaigns/{campaign_id}/rerun", headers=auth_header_for(org))
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0)
    assert fake_runtime.launched[0]["brief_text"].startswith("Campaign: Test Campaign")


async def test_rerun_rejects_other_orgs_campaign(client, session_factory, fake_runtime):
    _, campaign_id = await _setup(session_factory)
    other_org = await create_org(session_factory, "Other Org")

    resp = await client.post(
        f"{API}/campaigns/{campaign_id}/rerun", headers=auth_header_for(other_org)
    )
    assert resp.status_code == 404
    # A 404 that still wiped the owner's checkpoint would be worse than useless.
    assert fake_runtime.graph.checkpointer.deleted == []
    assert fake_runtime.launched == []


async def test_rerun_refuses_while_pipeline_active(client, session_factory, fake_runtime):
    from agency.routers import campaigns as campaigns_router

    org, campaign_id = await _setup(session_factory, status="running")
    campaigns_router._active_pipelines.add(str(campaign_id))

    resp = await client.post(f"{API}/campaigns/{campaign_id}/rerun", headers=auth_header_for(org))
    assert resp.status_code == 409
    assert fake_runtime.graph.checkpointer.deleted == []


async def test_rerun_refuses_autonomous_campaign(client, session_factory, fake_runtime):
    org, campaign_id = await _setup(session_factory, status="autonomous")

    resp = await client.post(f"{API}/campaigns/{campaign_id}/rerun", headers=auth_header_for(org))
    assert resp.status_code == 400
    assert fake_runtime.launched == []
