"""Posts › Queue / Calendar single-post actions (Cadence parity).

Generate, regenerate, creative brief, manual post, delete, the per-client
channel list and the calendar's client/pending filters. The LLM is a stub;
SQL, tenancy filters and quota arithmetic run for real against SQLite.

Every tenancy test asserts on the other org's row, so it fails if the
``org_id`` filter it covers is removed.
"""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from agency.agents.post_writer import BRIEF_FIELDS, PostWriterError, validate_brief, validate_post
from agency.models.tables import BrandProfile, Client, ContentPiece, Subscription
from agency.services import post_studio
from tests.conftest import (
    _persist,
    auth_header_for,
    create_client_row,
    create_content_row,
    create_org,
    create_platform_account,
    create_subscription,
    create_user_row,
)

API = "/api/v1"

POST_REPLY = json.dumps(
    {"title": "Roast day", "body": "Friday roast is back. Come early.", "hashtags": ["#coffee"]}
)
BRIEF_REPLY = json.dumps({k: f"{k} text" for k in BRIEF_FIELDS})


class StubLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[Any] = []

    async def ainvoke(self, messages: Any) -> SimpleNamespace:
        self.calls.append(messages)
        return SimpleNamespace(content=self.reply)


class FailingLLM:
    calls: list[Any] = []

    async def ainvoke(self, _messages: Any) -> SimpleNamespace:
        raise RuntimeError("provider 503")


@pytest.fixture
def stub_llm(monkeypatch):
    seen: dict[str, Any] = {}

    def _install(reply: str = POST_REPLY, *, fail: bool = False):
        stub: Any = FailingLLM() if fail else StubLLM(reply)

        def _get_worker_llm(temperature: float = 0.7):
            seen["temperature"] = temperature
            return stub

        def _no_lite(*_a, **_k):  # pragma: no cover - fails the test if reached
            raise AssertionError("post writer must not use the lite tier")

        monkeypatch.setattr("agency.agents.post_writer.get_worker_llm", _get_worker_llm)
        monkeypatch.setattr("agency.services.llm_provider.get_lite_llm", _no_lite)
        stub.seen = seen
        return stub

    return _install


@pytest.fixture
async def orgs(session_factory):
    org_a = await create_org(session_factory, "Studio A")
    org_b = await create_org(session_factory, "Studio B")
    await create_subscription(session_factory, org_a, plan_tier="starter")
    await create_subscription(session_factory, org_b, plan_tier="starter")
    user_a = await create_user_row(session_factory, org_a)
    user_b = await create_user_row(session_factory, org_b)
    client_a = await create_client_row(session_factory, org_a, "Sunrise Coffee")
    client_b = await create_client_row(session_factory, org_b, "Other Tenant")
    return SimpleNamespace(
        org_a=org_a,
        org_b=org_b,
        client_a=client_a,
        client_b=client_b,
        headers_a=auth_header_for(org_a, user_id=user_a),
        headers_b=auth_header_for(org_b, user_id=user_b),
    )


async def _row(session_factory, content_id) -> ContentPiece | None:
    async with session_factory() as s:
        return await s.get(ContentPiece, UUID(str(content_id)))


async def _used(session_factory, org_id) -> int:
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        return int(sub.generations_used or 0)


async def _count(session_factory, org_id) -> int:
    async with session_factory() as s:
        rows = await s.execute(select(ContentPiece.id).where(ContentPiece.org_id == org_id))
        return len(rows.all())


# --- pure validation ---------------------------------------------------------


def test_validate_post_strips_hash_and_enforces_limit():
    ok = validate_post({"body": "Hi", "hashtags": ["#a", "a", "b c"]}, "twitter")
    assert ok["hashtags"] == ["a"]
    assert ok["title"] == "Hi"
    with pytest.raises(PostWriterError):
        validate_post({"body": "x" * 281}, "twitter")
    with pytest.raises(PostWriterError):
        validate_post({"body": "  "}, "twitter")
    with pytest.raises(PostWriterError):
        validate_post(["not", "a", "dict"], "twitter")


def test_validate_brief_requires_every_field():
    assert validate_brief(json.loads(BRIEF_REPLY))["altText"] == "altText text"
    partial = {k: "x" for k in BRIEF_FIELDS if k != "altText"}
    with pytest.raises(PostWriterError, match="altText"):
        validate_brief(partial)


# --- generate ----------------------------------------------------------------


async def test_generate_creates_pending_draft_and_charges(
    client, orgs, session_factory, stub_llm
):
    await _persist(
        session_factory,
        BrandProfile(
            client_id=orgs.client_a,
            org_id=orgs.org_a,
            voice_description="warm and neighbourly",
            vocabulary_exclude=["synergy"],
            tone_attributes={},
            vocabulary_include=[],
            style_rules=[],
            example_posts=[],
        ),
    )
    async with session_factory() as s:
        c = await s.get(Client, orgs.client_a)
        assert c is not None
        c.settings = {"campaign_focus": {"description": "Autumn blend launch"}}
        await s.commit()

    stub = stub_llm()
    planned = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0)
    resp = await client.post(
        f"{API}/content/generate",
        json={
            "client_id": str(orgs.client_a),
            "platform": "twitter",
            "context_note": "we need early testers",
            "planned_for": planned.isoformat(),
            "status": "approved",  # ignored: not part of the request model
        },
        headers=orgs.headers_a,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "draft"
    assert data["hashtags"] == ["coffee"]
    assert data["metadata_"]["context_note"] == "we need early testers"

    row = await _row(session_factory, data["id"])
    assert row is not None and row.status == "draft" and row.org_id == orgs.org_a
    assert row.scheduled_at is not None  # planned day only — status is still draft
    assert await _used(session_factory, orgs.org_a) == 1
    assert stub.seen["temperature"] == 0.8

    prompt = stub.calls[0][1].content
    assert "warm and neighbourly" in prompt
    assert "synergy" in prompt
    assert "Autumn blend launch" in prompt
    assert "we need early testers" in prompt


async def test_generate_rejects_unsupported_platform_without_charge(
    client, orgs, session_factory, stub_llm
):
    stub = stub_llm()
    resp = await client.post(
        f"{API}/content/generate",
        json={"client_id": str(orgs.client_a), "platform": "myspace"},
        headers=orgs.headers_a,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "unsupported_platform"
    assert stub.calls == []
    assert await _used(session_factory, orgs.org_a) == 0


async def test_generate_quota_exhausted_is_402_before_llm(client, session_factory, stub_llm):
    org = await create_org(session_factory, "Broke")
    await create_subscription(
        session_factory, org, plan_tier="free", generations_used=5, generations_limit=5
    )
    cid = await create_client_row(session_factory, org)
    stub = stub_llm()
    resp = await client.post(
        f"{API}/content/generate",
        json={"client_id": str(cid), "platform": "linkedin"},
        headers=auth_header_for(org),
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["code"] == "generation_quota_exceeded"
    assert stub.calls == []


@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        json.dumps({"title": "t", "body": ""}),
        json.dumps({"title": "t", "body": "x" * 300}),  # over X's 280
    ],
)
async def test_generate_unusable_output_is_502_nothing_saved(
    client, orgs, session_factory, stub_llm, reply
):
    stub_llm(reply)
    resp = await client.post(
        f"{API}/content/generate",
        json={"client_id": str(orgs.client_a), "platform": "twitter"},
        headers=orgs.headers_a,
    )
    assert resp.status_code == 502
    assert "no quota was used" in resp.json()["detail"]
    assert await _count(session_factory, orgs.org_a) == 0
    assert await _used(session_factory, orgs.org_a) == 0


async def test_generate_provider_failure_is_502(client, orgs, session_factory, stub_llm):
    stub_llm(fail=True)
    resp = await client.post(
        f"{API}/content/generate",
        json={"client_id": str(orgs.client_a), "platform": "twitter"},
        headers=orgs.headers_a,
    )
    assert resp.status_code == 502
    assert await _used(session_factory, orgs.org_a) == 0


async def test_generate_for_other_orgs_client_is_404(client, orgs, session_factory, stub_llm):
    stub = stub_llm()
    resp = await client.post(
        f"{API}/content/generate",
        json={"client_id": str(orgs.client_b), "platform": "twitter"},
        headers=orgs.headers_a,
    )
    assert resp.status_code == 404
    assert stub.calls == []
    assert await _count(session_factory, orgs.org_a) == 0
    assert await _count(session_factory, orgs.org_b) == 0


async def test_generate_for_archived_client_is_refused(client, orgs, session_factory, stub_llm):
    async with session_factory() as s:
        c = await s.get(Client, orgs.client_a)
        assert c is not None
        c.is_active = False
        await s.commit()
    stub_llm()
    resp = await client.post(
        f"{API}/content/generate",
        json={"client_id": str(orgs.client_a), "platform": "twitter"},
        headers=orgs.headers_a,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "client_archived"


async def test_cancelled_generation_saves_and_charges_nothing(
    db, orgs, session_factory, stub_llm
):
    """Cancel = the caller went away before the model returned."""
    from fastapi import HTTPException

    stub_llm()

    async def gone() -> bool:
        return True

    with pytest.raises(HTTPException) as exc:
        await post_studio.generate_draft(
            db, org_id=orgs.org_a, client_id=orgs.client_a, platform="twitter", cancelled=gone
        )
    assert exc.value.status_code == 409
    assert await _count(session_factory, orgs.org_a) == 0
    assert await _used(session_factory, orgs.org_a) == 0


# --- regenerate --------------------------------------------------------------


async def test_regenerate_rewrites_in_place_and_stays_draft(
    client, orgs, session_factory, stub_llm
):
    cid = await create_content_row(
        session_factory, orgs.org_a, orgs.client_a, platform="twitter", body="Old tired copy"
    )
    async with session_factory() as s:
        row = await s.get(ContentPiece, cid)
        assert row is not None
        row.metadata_ = {"moderation": {"status": "passed"}, "keep": 1}
        await s.commit()

    stub = stub_llm()
    resp = await client.post(f"{API}/content/{cid}/regenerate", headers=orgs.headers_a)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == str(cid)
    assert data["status"] == "draft"
    assert data["body"] == "Friday roast is back. Come early."
    assert "moderation" not in data["metadata_"]
    assert data["metadata_"]["keep"] == 1
    assert data["metadata_"]["regenerate_count"] == 1
    assert "Old tired copy" in stub.calls[0][1].content
    assert await _used(session_factory, orgs.org_a) == 1
    assert await _count(session_factory, orgs.org_a) == 1


@pytest.mark.parametrize("state", ["approved", "scheduled", "published"])
async def test_regenerate_refuses_non_pending(client, orgs, session_factory, stub_llm, state):
    cid = await create_content_row(session_factory, orgs.org_a, orgs.client_a, status=state)
    stub = stub_llm()
    resp = await client.post(f"{API}/content/{cid}/regenerate", headers=orgs.headers_a)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "invalid_status"
    assert stub.calls == []
    row = await _row(session_factory, cid)
    assert row is not None and row.status == state and row.body == "Test body"


async def test_regenerate_other_orgs_piece_is_404(client, orgs, session_factory, stub_llm):
    foreign = await create_content_row(session_factory, orgs.org_b, orgs.client_b)
    stub = stub_llm()
    resp = await client.post(f"{API}/content/{foreign}/regenerate", headers=orgs.headers_a)
    assert resp.status_code == 404
    assert stub.calls == []
    row = await _row(session_factory, foreign)
    assert row is not None and row.body == "Test body"


# --- creative brief ----------------------------------------------------------


async def test_creative_brief_is_stored_and_status_untouched(
    client, orgs, session_factory, stub_llm
):
    cid = await create_content_row(
        session_factory, orgs.org_a, orgs.client_a, platform="instagram", status="approved"
    )
    stub_llm(BRIEF_REPLY)
    resp = await client.post(f"{API}/content/{cid}/creative-brief", headers=orgs.headers_a)
    assert resp.status_code == 200, resp.text
    brief = resp.json()["metadata_"]["creative_brief"]
    assert set(BRIEF_FIELDS) <= set(brief)
    row = await _row(session_factory, cid)
    assert row is not None and row.status == "approved"
    assert row.metadata_["creative_brief"]["visualConcept"] == "visualConcept text"
    assert await _used(session_factory, orgs.org_a) == 1


async def test_creative_brief_malformed_is_502_no_charge(client, orgs, session_factory, stub_llm):
    cid = await create_content_row(session_factory, orgs.org_a, orgs.client_a, platform="instagram")
    stub_llm(json.dumps({"visualConcept": "only one field"}))
    resp = await client.post(f"{API}/content/{cid}/creative-brief", headers=orgs.headers_a)
    assert resp.status_code == 502
    row = await _row(session_factory, cid)
    assert row is not None and "creative_brief" not in (row.metadata_ or {})
    assert await _used(session_factory, orgs.org_a) == 0


async def test_creative_brief_refuses_published_and_foreign(
    client, orgs, session_factory, stub_llm
):
    published = await create_content_row(
        session_factory, orgs.org_a, orgs.client_a, platform="instagram", status="published"
    )
    foreign = await create_content_row(
        session_factory, orgs.org_b, orgs.client_b, platform="instagram"
    )
    stub = stub_llm(BRIEF_REPLY)
    r1 = await client.post(f"{API}/content/{published}/creative-brief", headers=orgs.headers_a)
    assert r1.status_code == 409
    r2 = await client.post(f"{API}/content/{foreign}/creative-brief", headers=orgs.headers_a)
    assert r2.status_code == 404
    assert stub.calls == []
    row = await _row(session_factory, foreign)
    assert row is not None and "creative_brief" not in (row.metadata_ or {})


# --- manual post -------------------------------------------------------------


async def test_manual_post_is_pending_even_if_client_asks_for_scheduled(
    client, orgs, session_factory
):
    planned = datetime.now(UTC) + timedelta(days=1)
    resp = await client.post(
        f"{API}/content",
        json={
            "client_id": str(orgs.client_a),
            "platform": "linkedin",
            "body": "Written by hand.\nSecond line.",
            "planned_for": planned.isoformat(),
            "status": "scheduled",
        },
        headers=orgs.headers_a,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "draft"
    assert data["ai_generated"] is False
    assert data["title"] == "Written by hand."
    assert data["scheduled_at"] is not None
    assert await _used(session_factory, orgs.org_a) == 0


async def test_manual_post_over_limit_and_foreign_client(client, orgs, session_factory):
    over = await client.post(
        f"{API}/content",
        json={"client_id": str(orgs.client_a), "platform": "twitter", "body": "x" * 281},
        headers=orgs.headers_a,
    )
    assert over.status_code == 422
    foreign = await client.post(
        f"{API}/content",
        json={"client_id": str(orgs.client_b), "platform": "twitter", "body": "hi"},
        headers=orgs.headers_a,
    )
    assert foreign.status_code == 404
    assert await _count(session_factory, orgs.org_a) == 0
    assert await _count(session_factory, orgs.org_b) == 0


# --- delete ------------------------------------------------------------------


@pytest.mark.parametrize("state", ["draft", "approved", "scheduled", "failed"])
async def test_delete_unpublished(client, orgs, session_factory, state):
    cid = await create_content_row(session_factory, orgs.org_a, orgs.client_a, status=state)
    resp = await client.delete(f"{API}/content/{cid}", headers=orgs.headers_a)
    assert resp.status_code == 204
    assert await _row(session_factory, cid) is None


async def test_delete_published_is_locked(client, orgs, session_factory):
    cid = await create_content_row(session_factory, orgs.org_a, orgs.client_a, status="published")
    resp = await client.delete(f"{API}/content/{cid}", headers=orgs.headers_a)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "published_locked"
    assert await _row(session_factory, cid) is not None


async def test_delete_other_orgs_piece_is_404(client, orgs, session_factory):
    foreign = await create_content_row(session_factory, orgs.org_b, orgs.client_b)
    resp = await client.delete(f"{API}/content/{foreign}", headers=orgs.headers_a)
    assert resp.status_code == 404
    assert await _row(session_factory, foreign) is not None


async def test_delete_missing_is_404(client, orgs):
    resp = await client.delete(f"{API}/content/{uuid4()}", headers=orgs.headers_a)
    assert resp.status_code == 404


# --- channels ----------------------------------------------------------------


async def test_channels_lists_this_clients_connected_accounts_only(
    client, orgs, session_factory
):
    await create_platform_account(session_factory, orgs.org_a, orgs.client_a, platform="twitter")
    await create_platform_account(
        session_factory, orgs.org_a, orgs.client_a, platform="facebook", status="disconnected"
    )
    other_client = await create_client_row(session_factory, orgs.org_a, "Second")
    await create_platform_account(session_factory, orgs.org_a, other_client, platform="linkedin")
    # Another tenant's row carrying client A's id must never surface.
    await create_platform_account(session_factory, orgs.org_b, orgs.client_a, platform="tiktok")

    resp = await client.get(
        f"{API}/post-studio/channels?client_id={orgs.client_a}", headers=orgs.headers_a
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["connected"] == ["twitter"]
    assert "linkedin" in data["supported"]

    foreign = await client.get(
        f"{API}/post-studio/channels?client_id={orgs.client_b}", headers=orgs.headers_a
    )
    assert foreign.status_code == 404


# --- calendar filters ----------------------------------------------------------


async def test_calendar_client_filter_and_pending(client, orgs, session_factory):
    when = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)

    async def piece(org, cl, state):
        cid = await create_content_row(session_factory, org, cl, status=state)
        async with session_factory() as s:
            row = await s.get(ContentPiece, cid)
            assert row is not None
            row.scheduled_at = when
            await s.commit()
        return str(cid)

    scheduled_a = await piece(orgs.org_a, orgs.client_a, "scheduled")
    draft_a = await piece(orgs.org_a, orgs.client_a, "draft")
    other_client = await create_client_row(session_factory, orgs.org_a, "Second")
    scheduled_other = await piece(orgs.org_a, other_client, "scheduled")
    foreign = await piece(orgs.org_b, orgs.client_b, "scheduled")

    rng = "start=2026-10-01T00:00:00Z&end=2026-10-31T23:59:59Z"
    default = await client.get(f"{API}/publishing/calendar?{rng}", headers=orgs.headers_a)
    ids = {i["id"] for i in default.json()["items"]}
    assert ids == {scheduled_a, scheduled_other}

    scoped = await client.get(
        f"{API}/publishing/calendar?{rng}&client_id={orgs.client_a}&include_pending=true",
        headers=orgs.headers_a,
    )
    items = scoped.json()["items"]
    assert {i["id"] for i in items} == {scheduled_a, draft_a}
    assert foreign not in {i["id"] for i in items}
    assert all("hashtags" in i for i in items)

    # Another org's client id matches nothing — never that org's posts.
    cross = await client.get(
        f"{API}/publishing/calendar?{rng}&client_id={orgs.client_b}&include_pending=true",
        headers=orgs.headers_a,
    )
    assert cross.json()["items"] == []
