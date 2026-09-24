"""Capability gates on the routes that spend an org's generation allowance.

``POST /campaigns``, ``POST /campaigns/{id}/rerun``, ``POST /campaigns/autonomous``,
``PATCH /campaigns/{id}/review``, ``POST /amplify/preview`` and
``POST /amplify/{pack_id}/commit`` all require ``campaign.run``.

Why these and not the rest: each one either starts an agent run or commits its
output, and the run is metered — ``subscription.generations_used`` for Amplify,
``campaigns_limit`` for campaign creation. A ``viewer`` who could call them could
burn a month's allowance without being able to do anything with the result.
``PATCH /review`` is also the human-in-the-loop decision point (product rule 2):
a viewer is not the human who has final say, and the decision resumes the rest
of the paused run.

``member`` is on the allowed side of every one of these — creating and running
campaigns is ordinary work. The gate separates ``viewer`` from everyone else.

Deliberately ungated: ``GET /campaigns/{id}/stream``. It is an ``EventSource``
carrying the JWT in a query param because EventSource cannot set headers, so it
never goes through ``get_current_user``/``get_org_id`` at all; a ``require_cap``
there would have nothing to resolve. Read access is enough — the last test here
pins that a viewer can still watch a run. Every other ``GET`` on both routers,
including ``GET /amplify/packs``, is likewise read-only and ungated.
"""

import json
from datetime import date
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from agency.models.tables import Campaign, ContentPiece, RepurposePack, Subscription
from agency.services.repurpose import plan_atoms
from tests.conftest import (
    _persist,
    auth_for,
    create_campaign_row,
    create_client_row,
    create_org,
    create_subscription,
)

API = "/api/v1"

FORBIDDEN = {"code": "insufficient_permissions", "required": "campaign.run"}


# ---------------------------------------------------------------------------
# Stubs. Nothing here may reach a real LLM, the real graph, or a real pipeline —
# the point is the gate, and with the gate deleted these have to let the call
# through so the test fails loudly instead of erroring for an unrelated reason.
# ---------------------------------------------------------------------------
class _StubLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def ainvoke(self, _messages: Any) -> SimpleNamespace:
        return SimpleNamespace(content=self.reply)


class _FakeCheckpointer:
    async def adelete_thread(self, thread_id: str) -> None:
        return None


class _FakeGraph:
    def __init__(self) -> None:
        self.checkpointer = _FakeCheckpointer()
        self.updates: list[dict[str, Any]] = []

    async def aget_state(self, _config: dict) -> Any:
        return SimpleNamespace(values={})

    async def aupdate_state(self, _config: dict, values: dict, **_kw: Any) -> None:
        self.updates.append(values)


def _atoms_reply(platforms: list[str], n: int = 2) -> str:
    return json.dumps(
        {
            "atoms": [
                {
                    "platform": r["platform"],
                    "angle": r["angle"],
                    "title": f"{r['angle']} title",
                    "body": f"A distinct line about {r['angle']} and nothing else at all.",
                    "hashtags": ["coffee"],
                }
                for r in plan_atoms(platforms, n)
            ]
        }
    )


@pytest.fixture
def stubs(monkeypatch):
    """Fake the graph, the background pipeline, the planner and the model."""
    from agency.routers import campaigns as campaigns_router

    graph = _FakeGraph()
    launched: list[dict[str, Any]] = []
    resumed: list[str] = []

    async def _fake_pipeline(**kwargs: Any) -> None:
        launched.append(kwargs)

    async def _fake_resume(*args: Any, **_kw: Any) -> None:
        resumed.append(str(args[2]) if len(args) > 2 else "")

    async def _fake_plan(_goal: str, _brand: dict) -> dict:
        return {"weeks": []}

    monkeypatch.setattr(campaigns_router, "get_runtime_compiled_graph", lambda: graph)
    monkeypatch.setattr(campaigns_router, "_run_campaign_pipeline", _fake_pipeline)
    monkeypatch.setattr(campaigns_router, "_resume_pipeline", _fake_resume)
    monkeypatch.setattr(
        "agency.agents.autonomous_operator.plan_autonomous_cycle", _fake_plan
    )
    monkeypatch.setattr(
        "agency.agents.amplify.get_worker_llm",
        lambda temperature=0.7: _StubLLM(_atoms_reply(["twitter"])),
    )

    yield SimpleNamespace(graph=graph, launched=launched, resumed=resumed)

    campaigns_router._active_pipelines.clear()
    campaigns_router._campaign_streams.clear()


@pytest.fixture
async def env(session_factory):
    """One business org with a campaign, a pack, and a caller per role."""
    org_id = await create_org(session_factory, "Gate Campaign Org")
    await create_subscription(session_factory, org_id, plan_tier="starter")
    client_id = await create_client_row(session_factory, org_id, "Sunrise Coffee")
    campaign_id = await create_campaign_row(
        session_factory, org_id, client_id, "Autumn", status="failed"
    )
    pack = RepurposePack(
        id=uuid4(),
        org_id=org_id,
        client_id=client_id,
        source_text="A short source paragraph worth repurposing.",
        platforms=["twitter"],
        atom_count=2,
        committed_count=0,
    )
    await _persist(session_factory, pack)

    return SimpleNamespace(
        org_id=org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        pack_id=pack.id,
        viewer=await auth_for(session_factory, org_id, "viewer"),
        member=await auth_for(session_factory, org_id, "member"),
    )


def _brief(client_id) -> dict[str, Any]:
    return {
        "client_id": str(client_id),
        "campaign_name": "Launch Q3",
        "objective": "Drive signups for the new launch",
        "channels": ["linkedin"],
        "start_date": date.today().isoformat(),
        "end_date": date.today().isoformat(),
    }


def _calls(env) -> dict[str, tuple[str, str, dict[str, Any] | None]]:
    """Every gated route, as (method, path, json body)."""
    return {
        "create": ("POST", f"{API}/campaigns", _brief(env.client_id)),
        "rerun": ("POST", f"{API}/campaigns/{env.campaign_id}/rerun", None),
        "autonomous": (
            "POST",
            f"{API}/campaigns/autonomous",
            {"client_id": str(env.client_id), "goal": "Grow the newsletter"},
        ),
        "review": (
            "PATCH",
            f"{API}/campaigns/{env.campaign_id}/review",
            {"decision": "approved"},
        ),
        "preview": (
            "POST",
            f"{API}/amplify/preview",
            {
                "client_id": str(env.client_id),
                "source_text": "A short source paragraph worth repurposing.",
                "platforms": ["twitter"],
                "max_atoms": 2,
            },
        ),
        "commit": (
            "POST",
            f"{API}/amplify/{env.pack_id}/commit",
            {
                "atoms": [
                    {
                        "platform": "twitter",
                        "angle": "hook",
                        "title": "t",
                        "body": "A distinct line about hook and nothing else at all.",
                        "hashtags": [],
                    }
                ]
            },
        ),
    }


async def _call(http, env, name: str, headers: dict[str, str]):
    method, path, body = _calls(env)[name]
    return await http.request(method, path, json=body, headers=headers)


ROUTES = ["create", "rerun", "autonomous", "review", "preview", "commit"]


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("route", ROUTES)
async def test_viewer_is_refused(client, env, stubs, route):
    resp = await _call(client, env, route, env.viewer)
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == FORBIDDEN


@pytest.mark.parametrize("route", ROUTES)
async def test_member_is_admitted(client, env, stubs, route):
    """``member`` holds ``campaign.run`` — running campaigns is ordinary work."""
    resp = await _call(client, env, route, env.member)
    assert resp.status_code < 400, resp.text


async def test_viewer_rejection_does_not_spend_a_generation(
    client, env, stubs, session_factory
):
    """A gate that 403s *after* charging quota is not a gate.

    Amplify's preview charges one generation as soon as a usable pack comes
    back, so the counter is the honest witness: it must be untouched by a
    refused call, and must move for the same call from a member.
    """

    async def used() -> int:
        async with session_factory() as s:
            sub = (
                await s.execute(
                    select(Subscription).where(Subscription.org_id == env.org_id)
                )
            ).scalar_one()
            return int(sub.generations_used or 0)

    assert await used() == 0

    resp = await _call(client, env, "preview", env.viewer)
    assert resp.status_code == 403
    assert await used() == 0, "the refused call charged the org a generation"

    # No pack row either — the gate runs before the handler opens its work.
    async with session_factory() as s:
        packs = (
            await s.execute(
                select(func.count(RepurposePack.id)).where(
                    RepurposePack.org_id == env.org_id
                )
            )
        ).scalar()
    assert packs == 1  # only the fixture's pack

    resp = await _call(client, env, "preview", env.member)
    assert resp.status_code == 200, resp.text
    assert await used() == 1


async def test_viewer_rejection_creates_no_campaign(client, env, stubs, session_factory):
    """Campaign creation is metered by ``campaigns_limit``; the row must not appear."""

    async def count() -> int:
        async with session_factory() as s:
            return int(
                (
                    await s.execute(
                        select(func.count(Campaign.id)).where(
                            Campaign.org_id == env.org_id
                        )
                    )
                ).scalar()
                or 0
            )

    before = await count()
    resp = await _call(client, env, "create", env.viewer)
    assert resp.status_code == 403
    assert await count() == before
    assert stubs.launched == []


async def test_viewer_commit_writes_no_drafts(client, env, stubs, session_factory):
    resp = await _call(client, env, "commit", env.viewer)
    assert resp.status_code == 403
    async with session_factory() as s:
        rows = (
            await s.execute(
                select(ContentPiece).where(ContentPiece.org_id == env.org_id)
            )
        ).scalars().all()
    assert rows == []


async def test_viewer_review_does_not_resume_the_pipeline(client, env, stubs):
    """The paused graph must be untouched: no state update, no resume task."""
    resp = await _call(client, env, "review", env.viewer)
    assert resp.status_code == 403
    assert stubs.graph.updates == []
    assert stubs.resumed == []


# ---------------------------------------------------------------------------
# Deliberately ungated
# ---------------------------------------------------------------------------
async def test_viewer_can_still_watch_the_stream(client, env, session_factory):
    """``GET /{id}/stream`` stays open to a viewer.

    EventSource cannot set an ``Authorization`` header, so this route reads the
    JWT from ``?token=`` and never resolves a user through the normal
    dependencies. Gating it would break SSE auth for everyone, and watching a
    run is read access.
    """
    token = env.viewer["Authorization"].removeprefix("Bearer ")
    resp = await client.get(
        f"{API}/campaigns/{env.campaign_id}/stream", params={"token": token}
    )
    assert resp.status_code == 200
    assert "insufficient_permissions" not in resp.text


async def test_viewer_can_list_amplify_packs(client, env):
    resp = await client.get(f"{API}/amplify/packs", headers=env.viewer)
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


async def test_viewer_can_read_campaigns(client, env):
    resp = await client.get(f"{API}/campaigns", headers=env.viewer)
    assert resp.status_code == 200
