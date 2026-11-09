"""The human review gate: a run that pauses is paused, not finished.

The graph compiles with ``interrupt_before=["human_review"]``, so ``astream``
simply returns at the gate. The router used to treat that return as the end of
the run: it sent ``complete``, marked the campaign ``completed`` (hiding the gate
on every reload, so QA/Brand never ran) and saved the drafts — then saved them a
second time when the review decision resumed the run. These tests pin the fix:

- pausing saves the drafts once, marked pre-review, and parks the campaign as
  ``paused`` behind a single ``waiting_human`` event;
- finishing replaces the pre-review drafts nobody touched, keeps the ones a
  person acted on, and never inserts a second copy of a kept piece;
- ``PATCH /review`` resumes only a run the checkpoint says is at the gate.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import select

from agency.models.tables import Campaign, ContentPiece, Organization, Subscription
from agency.services.billing import PLAN_CONFIG, BillingService
from agency.services.content_approval import PRE_REVIEW_MARKER, apply_content_edit
from tests.conftest import (
    auth_for,
    create_campaign_row,
    create_client_row,
    create_org,
    create_subscription,
)

API = "/api/v1"


class _Graph:
    def __init__(self, values: dict[str, Any], next_: tuple[str, ...]) -> None:
        self.values = values
        self.next = next_

    async def aget_state(self, _config: dict) -> Any:
        return SimpleNamespace(values=self.values, next=self.next)


def _piece(platform: str, body: str) -> dict[str, Any]:
    return {"platform": platform, "title": f"{platform} post", "body": body, "hashtags": []}


def _ad() -> dict[str, Any]:
    return {
        "platform": "google",
        "headlines": ["Fresh coffee, delivered"],
        "descriptions": ["Roasted this week. Order today."],
        "angle": "benefit",
    }


async def _setup(session_factory):
    org = await create_org(session_factory, "Gate Org")
    client_id = await create_client_row(session_factory, org, "Sunrise Coffee")
    campaign_id = await create_campaign_row(session_factory, org, client_id, status="running")
    return org, client_id, campaign_id


async def _rows(session_factory, campaign_id) -> list[ContentPiece]:
    async with session_factory() as s:
        return list(
            (
                await s.execute(
                    select(ContentPiece).where(ContentPiece.campaign_id == campaign_id)
                )
            ).scalars().all()
        )


async def _campaign_status(session_factory, campaign_id) -> str:
    async with session_factory() as s:
        return (await s.get(Campaign, campaign_id)).status


def _drain(queue: asyncio.Queue) -> list[str]:
    events = []
    while not queue.empty():
        events.append(json.loads(queue.get_nowait())["type"])
    return events


async def _finish(graph, org, client_id, campaign_id, *, resumed=False) -> list[str]:
    from agency.routers import campaigns as router

    queue: asyncio.Queue = asyncio.Queue()
    await router._finish_run(
        queue, graph, {}, str(campaign_id), str(org), str(client_id), resumed=resumed
    )
    return _drain(queue)


async def test_pause_saves_marked_drafts_and_parks_the_campaign(session_factory):
    org, client_id, campaign_id = await _setup(session_factory)
    graph = _Graph(
        {
            "content_pieces": [_piece("linkedin", "A"), _piece("twitter", "B")],
            "ad_variants": [_ad()],
        },
        ("human_review",),
    )

    events = await _finish(graph, org, client_id, campaign_id)

    assert events == ["waiting_human"]  # never "complete" at the gate
    assert await _campaign_status(session_factory, campaign_id) == "paused"
    rows = await _rows(session_factory, campaign_id)
    assert len(rows) == 3
    assert all((r.metadata_ or {}).get(PRE_REVIEW_MARKER) for r in rows)


async def test_finishing_replaces_untouched_drafts_and_keeps_the_rest(session_factory):
    org, client_id, campaign_id = await _setup(session_factory)
    pre = {
        "content_pieces": [_piece("linkedin", "A"), _piece("twitter", "B"), _piece("x", "C")],
        "ad_variants": [_ad()],
    }
    await _finish(_Graph(pre, ("human_review",)), org, client_id, campaign_id)

    # At the gate: one draft approved, one edited, the rest left alone.
    async with session_factory() as s:
        rows = {
            r.body: r
            for r in (
                await s.execute(
                    select(ContentPiece).where(ContentPiece.campaign_id == campaign_id)
                )
            ).scalars()
        }
        rows["A"].status = "approved"
        apply_content_edit(rows["B"], body="B, edited by a person")
        await s.commit()

    final = {
        # A unchanged by QA, B and C revised, ad unchanged.
        "content_pieces": [_piece("linkedin", "A"), _piece("twitter", "B2"), _piece("x", "C2")],
        "ad_variants": [_ad()],
    }
    events = await _finish(_Graph(final, ()), org, client_id, campaign_id, resumed=True)

    assert events == ["complete"]
    assert await _campaign_status(session_factory, campaign_id) == "completed"
    bodies = sorted(r.body for r in await _rows(session_factory, campaign_id))
    ad_bodies = [b for b in bodies if b not in {"A", "B, edited by a person", "B2", "C2"}]
    # A once (kept, not re-inserted); the person's B kept beside the revised B2;
    # untouched C replaced by C2; the untouched ad replaced by one copy.
    assert [b for b in bodies if b in {"A", "B, edited by a person", "B2", "C2"}] == [
        "A",
        "B, edited by a person",
        "B2",
        "C2",
    ]
    assert len(ad_bodies) == 1
    assert not any(
        (r.metadata_ or {}).get(PRE_REVIEW_MARKER)
        for r in await _rows(session_factory, campaign_id)
        if r.status == "draft" and r.body in {"B2", "C2"}
    )


async def test_pausing_twice_does_not_stack_drafts(session_factory):
    """"Request revisions" loops back through the gate and pauses again."""
    org, client_id, campaign_id = await _setup(session_factory)
    await _finish(
        _Graph({"content_pieces": [_piece("linkedin", "A")]}, ("human_review",)),
        org, client_id, campaign_id,
    )
    await _finish(
        _Graph({"content_pieces": [_piece("linkedin", "A2")]}, ("human_review",)),
        org, client_id, campaign_id,
    )

    assert [r.body for r in await _rows(session_factory, campaign_id)] == ["A2"]


async def test_review_is_refused_when_the_run_is_not_at_the_gate(
    client, session_factory, monkeypatch
):
    from agency.routers import campaigns as router

    org, _client_id, campaign_id = await _setup(session_factory)
    monkeypatch.setattr(router, "get_runtime_compiled_graph", lambda: _Graph({}, ()))
    resumed: list[Any] = []

    async def _fake_resume(*args: Any, **_kw: Any) -> None:
        resumed.append(args)

    monkeypatch.setattr(router, "_resume_pipeline", _fake_resume)

    resp = await client.patch(
        f"{API}/campaigns/{campaign_id}/review",
        json={"decision": "approved"},
        headers=await auth_for(session_factory, org),
    )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "not_awaiting_review"
    assert resumed == []


async def test_review_resumes_a_paused_run_and_marks_it_running(
    client, session_factory, monkeypatch
):
    from agency.routers import campaigns as router

    org, _client_id, campaign_id = await _setup(session_factory)
    async with session_factory() as s:
        (await s.get(Campaign, campaign_id)).status = "paused"
        await s.commit()

    class _Paused(_Graph):
        async def aupdate_state(self, *_a: Any, **_kw: Any) -> None:
            return None

    paused = _Paused({}, ("human_review",))
    monkeypatch.setattr(router, "get_runtime_compiled_graph", lambda: paused)

    async def _fake_resume(*_args: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(router, "_resume_pipeline", _fake_resume)
    try:
        resp = await client.patch(
            f"{API}/campaigns/{campaign_id}/review",
            json={"decision": "approved"},
            headers=await auth_for(session_factory, org),
        )
        assert resp.status_code == 200, resp.text
        assert await _campaign_status(session_factory, campaign_id) == "running"
    finally:
        router._active_pipelines.clear()
        router._campaign_streams.clear()


# ---------------------------------------------------------------------------
# Paying for more than one client makes the workspace a business one
# ---------------------------------------------------------------------------
async def test_multi_client_plan_unlocks_adding_clients(db, session_factory):
    org_id = await create_org(session_factory, "Solo Agency", account_type="personal")
    await create_subscription(
        session_factory, org_id, plan_tier="free", billing_subscription_id="sub_solo"
    )

    await BillingService().handle_webhook(
        db,
        {
            "type": "subscription.plan_changed",
            "data": {
                "subscription_id": "sub_solo",
                "metadata": {},
                "product_id": PLAN_CONFIG["growth"]["product_id"],
                "status": "active",
            },
        },
        "wh_solo",
    )

    async with session_factory() as s:
        org = await s.get(Organization, UUID(str(org_id)))
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
    assert sub.clients_limit > 1
    assert org.account_type == "business"


async def test_single_client_plan_leaves_a_personal_workspace_alone(db, session_factory):
    org_id = await create_org(session_factory, "Solo Brand", account_type="personal")
    await create_subscription(session_factory, org_id, plan_tier="free")

    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        await BillingService()._unlock_clients(s, sub)
        await s.commit()
        org = await s.get(Organization, UUID(str(org_id)))
    assert org.account_type == "personal"


async def test_brand_learnings_recorded_once_from_the_final_output(session_factory, monkeypatch):
    """Errors here are swallowed with a warning, so a type slip would go unseen."""
    calls: list[Any] = []

    async def _fake_learn(_db: Any, client_id: Any, summary: dict) -> None:
        calls.append((client_id, summary))

    monkeypatch.setattr(
        "agency.services.brand_learning.update_brand_learnings", _fake_learn
    )
    org, client_id, campaign_id = await _setup(session_factory)
    values = {"content_pieces": [_piece("linkedin", "A")]}

    await _finish(_Graph(values, ("human_review",)), org, client_id, campaign_id)
    assert calls == []  # not at the gate

    await _finish(_Graph(values, ()), org, client_id, campaign_id, resumed=True)
    assert len(calls) == 1
    assert calls[0][0] == UUID(str(client_id))
