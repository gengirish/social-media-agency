"""Insights + Settings (Cadence parity): summary, recommendations, quality signal,
advocacy, activity log, export, posting prefs.

Two properties matter most and each has a test that fails without it:

- **Tenancy** — every new endpoint 404s on another org's client.
- **No invented numbers** — ratios and recommendations report
  ``insufficient_data`` below their minimum sample, and the advocacy agent's
  output is rejected (502, no quota used) if it cites a number the server did
  not give it.

The LLM is a stub; everything else runs against the SQLite test database.
"""

import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import null, select

from agency.agents.advocacy import AdvocacyError, invented_numbers, validate_advocacy
from agency.models.tables import (
    AnalyticsSnapshot,
    ContentPiece,
    CreativeAsset,
    ProductEvent,
    Subscription,
)
from agency.services import product_analytics as pa
from agency.services.brand_context import brand_prompt_block
from agency.services.insights import (
    InsightStats,
    gated_rate,
    outcome_of,
    recommendations_for,
    summarize_content_signal,
    tally_content_signal,
)
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


# ---------------------------------------------------------------------------
# Pure logic — ported from the prototype's tests/logic.test.js
# ---------------------------------------------------------------------------


def test_summarize_content_signal_hides_platforms_below_three_outcomes():
    assert (
        summarize_content_signal({"x": {"kept": 1, "edited": 1, "discarded": 0, "regenerated": 0}})
        == []
    )


def test_summarize_content_signal_includes_platform_at_three():
    rows = summarize_content_signal(
        {"x": {"kept": 2, "edited": 1, "discarded": 0, "regenerated": 0}}
    )
    assert len(rows) == 1 and rows[0]["platform"] == "x"


def test_summarize_content_signal_percentages():
    rows = summarize_content_signal(
        {"x": {"kept": 3, "edited": 1, "discarded": 0, "regenerated": 2}}
    )
    assert rows[0]["kept_pct"] == 75
    assert rows[0]["edited_pct"] == 25
    assert rows[0]["discarded_pct"] == 0
    assert rows[0]["regenerated"] == 2


def test_summarize_content_signal_sorts_most_active_first():
    rows = summarize_content_signal(
        {
            "x": {"kept": 3, "edited": 0, "discarded": 0, "regenerated": 0},
            "linkedin": {"kept": 8, "edited": 2, "discarded": 1, "regenerated": 0},
        }
    )
    assert [r["platform"] for r in rows] == ["linkedin", "x"]


def test_summarize_content_signal_empty():
    assert summarize_content_signal({}) == []
    assert summarize_content_signal(None) == []


def test_outcome_of_maps_statuses():
    assert outcome_of("draft", {}) is None
    assert outcome_of("approved", {}) == "kept"
    assert outcome_of("published", {"edited_before_approval": True}) == "edited"
    assert outcome_of("rejected", {}) == "discarded"


def test_tally_counts_per_platform():
    tallies = tally_content_signal(
        [("x", "approved", {}), ("x", "rejected", {}), ("linkedin", "draft", {})]
    )
    assert tallies == {"x": {"kept": 1, "edited": 0, "discarded": 1, "regenerated": 0}}


def test_gated_rate_withholds_value_below_minimum():
    assert gated_rate(1, 2) == {
        "status": "insufficient_data",
        "value": None,
        "count": 1,
        "n": 2,
        "needed": 3,
    }
    assert gated_rate(2, 3)["value"] == 67


def _stats(**kw: Any) -> InsightStats:
    base: dict[str, Any] = {
        "by_platform": {},
        "pending": 0,
        "published": 0,
        "failed": 0,
        "moderation_checks": 0,
        "moderation_flags": 0,
        "engagement_by_platform": {},
    }
    base.update(kw)
    return InsightStats(**base)


def test_no_recommendation_fires_below_any_threshold():
    """Two bad data points must not produce a conclusion (n<3)."""
    recs, rules = recommendations_for(
        _stats(
            by_platform={"x": 2, "linkedin": 0},
            pending=4,
            published=0,
            failed=2,
            moderation_checks=2,
            moderation_flags=2,
            engagement_by_platform={"x": {"posts": 2, "avg_engagement": 50}},
        )
    )
    assert recs == []
    assert {r["id"]: r["status"] for r in rules} == {
        "neglected-platform": "insufficient_data",
        "pending-backlog": "insufficient_data",
        "publish-failures": "insufficient_data",
        "moderation-flags": "insufficient_data",
        "engagement-leader": "insufficient_data",
    }


def test_recommendations_fire_at_thresholds_with_real_numbers():
    recs, _ = recommendations_for(
        _stats(
            by_platform={"x": 3, "linkedin": 0},
            pending=5,
            published=1,
            failed=2,
            moderation_checks=3,
            moderation_flags=2,
            engagement_by_platform={
                "x": {"posts": 3, "avg_engagement": 40},
                "linkedin": {"posts": 4, "avg_engagement": 10},
            },
        )
    )
    by_id = {r["id"]: r for r in recs}
    assert set(by_id) == {
        "neglected-platform",
        "pending-backlog",
        "publish-failures",
        "moderation-flags",
        "engagement-leader",
    }
    assert by_id["neglected-platform"]["platform"] == "linkedin"
    assert "33%" in by_id["publish-failures"]["text"]
    assert "67%" in by_id["moderation-flags"]["text"]
    assert "40" in by_id["engagement-leader"]["text"] and "10" in by_id["engagement-leader"]["text"]


def test_backlog_needs_more_pending_than_published():
    recs, _ = recommendations_for(_stats(pending=6, published=6))
    assert recs == []


# ---------------------------------------------------------------------------
# Advocacy validation
# ---------------------------------------------------------------------------

FACTS = {
    "posts_published": 12,
    "posts_created": 30,
    "moderation_checks": 14,
    "connected_platforms": 2,
}


def test_invented_numbers_flags_only_unreal_figures():
    assert invented_numbers("12 posts published across 2 platforms", FACTS) == []
    assert invented_numbers("We grew 300% with 12 posts", FACTS) == ["300"]
    assert invented_numbers("Launched in 2026", FACTS, brand_text="Q3 2026 launch") == []


def test_validate_advocacy_rejects_invented_number():
    with pytest.raises(AdvocacyError):
        validate_advocacy(
            {
                "reviewRequestMessage": "Loved by 5,000 users!",
                "caseStudyOutline": ["Problem"],
                "socialProofSnippet": "12 posts",
            },
            FACTS,
        )


def test_validate_advocacy_rejects_missing_fields():
    with pytest.raises(AdvocacyError):
        validate_advocacy({"reviewRequestMessage": "hi"}, FACTS)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@pytest.fixture
async def orgs(session_factory):
    org_a = await create_org(session_factory, "Insights A")
    org_b = await create_org(session_factory, "Insights B")
    await create_subscription(session_factory, org_a, plan_tier="starter")
    await create_subscription(session_factory, org_b, plan_tier="starter")
    user_a = await create_user_row(session_factory, org_a)
    client_a = await create_client_row(session_factory, org_a, "Sunrise Coffee")
    client_b = await create_client_row(session_factory, org_b, "Other Brand")
    return SimpleNamespace(
        org_a=org_a,
        org_b=org_b,
        client_a=client_a,
        client_b=client_b,
        headers=auth_header_for(org_a, user_id=user_a),
    )


async def _set_meta(session_factory, content_id: UUID, meta: dict[str, Any], **cols: Any) -> None:
    async with session_factory() as s:
        row = (
            await s.execute(select(ContentPiece).where(ContentPiece.id == content_id))
        ).scalar_one()
        row.metadata_ = meta
        for k, v in cols.items():
            setattr(row, k, v)
        await s.commit()


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/insights/summary?client_id={cid}"),
        ("get", "/workspace/activity?client_id={cid}"),
        ("get", "/workspace/export?client_id={cid}"),
        ("get", "/workspace/posting-prefs?client_id={cid}"),
    ],
)
async def test_read_endpoints_reject_other_orgs_client(client, orgs, method, path):
    resp = await getattr(client, method)(API + path.format(cid=orgs.client_b), headers=orgs.headers)
    assert resp.status_code == 404


async def test_posting_prefs_put_rejects_other_orgs_client(client, orgs, session_factory):
    resp = await client.put(
        f"{API}/workspace/posting-prefs?client_id={orgs.client_b}",
        json={"cadence_per_week": 5},
        headers=orgs.headers,
    )
    assert resp.status_code == 404


async def test_advocacy_rejects_other_orgs_client(client, orgs, session_factory, monkeypatch):
    monkeypatch.setattr(
        "agency.agents.advocacy.get_worker_llm",
        lambda *_a, **_k: pytest.fail("LLM must not be called for a foreign client"),
    )
    resp = await client.post(
        f"{API}/insights/advocacy", json={"client_id": str(orgs.client_b)}, headers=orgs.headers
    )
    assert resp.status_code == 404


async def test_summary_empty_client_reports_insufficient_data(client, orgs):
    resp = await client.get(
        f"{API}/insights/summary?client_id={orgs.client_a}", headers=orgs.headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_posts"] == 0
    assert data["recommendations"] == []
    assert data["publish"]["success"]["status"] == "insufficient_data"
    assert data["publish"]["success"]["value"] is None
    assert data["moderation"]["clean"]["value"] is None
    assert data["quality_signal"]["rows"] == []
    for rate in data["quality_signal"]["rates"].values():
        assert rate["status"] == "insufficient_data" and rate["value"] is None
    assert data["engagement"]["status"] == "unavailable"
    assert all(r["status"] == "insufficient_data" for r in data["thresholds"])


async def test_summary_counts_real_rows_only_for_this_client(client, orgs, session_factory):
    a, b = orgs.client_a, orgs.client_b
    await create_platform_account(session_factory, orgs.org_a, a, platform="twitter")
    await create_platform_account(session_factory, orgs.org_a, a, platform="linkedin")
    # Twitter: 3 reviewed outcomes (kept, edited, discarded) + 1 pending.
    k = await create_content_row(
        session_factory, orgs.org_a, a, platform="twitter", status="published"
    )
    await _set_meta(
        session_factory, k, {"moderation": {"status": "passed", "at": "2026-09-01T00:00:00+00:00"}}
    )
    e = await create_content_row(
        session_factory, orgs.org_a, a, platform="twitter", status="approved"
    )
    await _set_meta(
        session_factory,
        e,
        {
            "edited_before_approval": True,
            "moderation": {"status": "overridden", "at": "2026-09-02T00:00:00+00:00"},
        },
    )
    await create_content_row(session_factory, orgs.org_a, a, platform="twitter", status="rejected")
    await create_content_row(session_factory, orgs.org_a, a, platform="twitter", status="draft")
    await create_content_row(session_factory, orgs.org_a, a, platform="twitter", status="failed")
    # Noise in the other org must not leak in.
    for _ in range(4):
        await create_content_row(
            session_factory, orgs.org_b, b, platform="linkedin", status="published"
        )

    resp = await client.get(f"{API}/insights/summary?client_id={a}", headers=orgs.headers)
    data = resp.json()
    assert data["total_posts"] == 5
    assert data["funnel"] == {
        "pending": 1,
        "approved": 1,
        "scheduled": 0,
        "published": 1,
        "failed": 1,
        "rejected": 1,
    }
    assert data["connected_platforms"] == ["linkedin", "twitter"]
    assert data["moderation"]["checks"] == 2 and data["moderation"]["flagged"] == 1
    rows = data["quality_signal"]["rows"]
    # kept: published + failed (both approved, unedited); edited: 1; discarded: 1
    assert rows == [
        {
            "platform": "twitter",
            "total": 4,
            "kept": 2,
            "edited": 1,
            "discarded": 1,
            "kept_pct": 50,
            "edited_pct": 25,
            "discarded_pct": 25,
            "regenerated": 0,
        }
    ]
    assert data["quality_signal"]["rates"]["approved_without_edit"]["value"] == 67
    # Neglected LinkedIn: 5 posts on connected platforms, twitter has ≥2, linkedin 0.
    assert "neglected-platform" in {r["id"] for r in data["recommendations"]}


async def test_summary_engagement_uses_latest_snapshot_and_skips_unmeasured(
    client, orgs, session_factory
):
    acct = await create_platform_account(
        session_factory, orgs.org_a, orgs.client_a, platform="linkedin"
    )
    post = await create_content_row(
        session_factory, orgs.org_a, orgs.client_a, platform="linkedin", status="published"
    )
    unmeasured = await create_content_row(
        session_factory, orgs.org_a, orgs.client_a, platform="linkedin", status="published"
    )
    today = date.today()
    eng: Any
    for d, eng, cid in [
        (today - timedelta(days=1), 5, post),
        (today, 9, post),
        # Unmeasured is stored as SQL NULL (analytics_fetcher writes null()).
        (today, null(), unmeasured),
    ]:
        await _persist(
            session_factory,
            AnalyticsSnapshot(
                id=uuid4(), platform_account_id=acct, content_id=cid, date=d, engagement=eng
            ),
        )
    data = (
        await client.get(f"{API}/insights/summary?client_id={orgs.client_a}", headers=orgs.headers)
    ).json()
    assert data["engagement"]["posts_measured"] == 1
    assert data["engagement"]["by_platform"] == [
        {"platform": "linkedin", "posts": 1, "avg_engagement": 9, "total_engagement": 9}
    ]


# --- Advocacy --------------------------------------------------------------


class StubLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[Any] = []

    async def ainvoke(self, messages: Any) -> SimpleNamespace:
        self.calls.append(messages)
        return SimpleNamespace(content=self.reply)


def _install(monkeypatch, reply: dict[str, Any] | str) -> StubLLM:
    stub = StubLLM(reply if isinstance(reply, str) else json.dumps(reply))
    monkeypatch.setattr("agency.agents.advocacy.get_worker_llm", lambda *_a, **_k: stub)
    return stub


async def _generations_used(session_factory, org_id) -> int:
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        return int(sub.generations_used or 0)


async def test_advocacy_cites_real_numbers_saves_asset_and_charges(
    client, orgs, session_factory, monkeypatch
):
    for _ in range(2):
        await create_content_row(session_factory, orgs.org_a, orgs.client_a, status="published")
    stub = _install(
        monkeypatch,
        {
            "reviewRequestMessage": "Now that 2 posts are live, would you leave us a review on G2?",
            "caseStudyOutline": [
                "Problem: no time",
                "Solution: a reviewed queue",
                "Result: 2 posts published",
            ],
            "socialProofSnippet": "2 posts published, every one human-approved.",
        },
    )
    resp = await client.post(
        f"{API}/insights/advocacy", json={"client_id": str(orgs.client_a)}, headers=orgs.headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "advocacy"
    assert body["payload"]["facts"]["posts_published"] == 2
    # The real numbers were handed to the model.
    prompt = stub.calls[0][1].content
    assert "2 posts published to live accounts" in prompt
    assert await _generations_used(session_factory, orgs.org_a) == 1
    async with session_factory() as s:
        assets = (
            (await s.execute(select(CreativeAsset).where(CreativeAsset.org_id == orgs.org_a)))
            .scalars()
            .all()
        )
    assert [a.kind for a in assets] == ["advocacy"]


async def test_advocacy_with_invented_number_is_502_and_free(
    client, orgs, session_factory, monkeypatch
):
    _install(
        monkeypatch,
        {
            "reviewRequestMessage": "Join 10,000 happy customers!",
            "caseStudyOutline": ["Problem", "Solution", "Result: 3x growth"],
            "socialProofSnippet": "Trusted by thousands.",
        },
    )
    resp = await client.post(
        f"{API}/insights/advocacy", json={"client_id": str(orgs.client_a)}, headers=orgs.headers
    )
    assert resp.status_code == 502
    assert "no quota" in resp.json()["detail"]
    assert await _generations_used(session_factory, orgs.org_a) == 0
    async with session_factory() as s:
        assert (await s.execute(select(CreativeAsset))).scalars().first() is None


async def test_advocacy_blocked_at_quota(client, session_factory, monkeypatch):
    org = await create_org(session_factory, "Quota Org")
    await create_subscription(session_factory, org, plan_tier="free", generations_used=10)
    cid = await create_client_row(session_factory, org, "Q")
    monkeypatch.setattr(
        "agency.agents.advocacy.get_worker_llm",
        lambda *_a, **_k: pytest.fail("LLM must not be called over quota"),
    )
    resp = await client.post(
        f"{API}/insights/advocacy", json={"client_id": str(cid)}, headers=auth_header_for(org)
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["code"] == "generation_quota_exceeded"


# --- Activity / export / prefs ---------------------------------------------


async def test_activity_log_derives_real_events_for_this_client_only(client, orgs, session_factory):
    await create_platform_account(session_factory, orgs.org_a, orgs.client_a, platform="twitter")
    pub = await create_content_row(
        session_factory, orgs.org_a, orgs.client_a, platform="twitter", status="published"
    )
    await _set_meta(session_factory, pub, {}, published_at=datetime.now(UTC))
    await _persist(
        session_factory,
        ProductEvent(
            id=uuid4(),
            org_id=orgs.org_a,
            name=pa.MODERATION_FLAGGED,
            category="feature",
            properties={"client_id": str(orgs.client_a), "platform": "twitter", "issue_count": 2},
            occurred_at=datetime.now(UTC),
        ),
    )
    # Another client's flag event in the same org, and another org's post.
    other = await create_client_row(session_factory, orgs.org_a, "Sibling")
    await _persist(
        session_factory,
        ProductEvent(
            id=uuid4(),
            org_id=orgs.org_a,
            name=pa.MODERATION_FLAGGED,
            category="feature",
            properties={"client_id": str(other), "platform": "x"},
            occurred_at=datetime.now(UTC),
        ),
    )
    await create_content_row(session_factory, orgs.org_b, orgs.client_b, status="published")

    resp = await client.get(
        f"{API}/workspace/activity?client_id={orgs.client_a}", headers=orgs.headers
    )
    assert resp.status_code == 200
    actions = [i["action"] for i in resp.json()["items"]]
    assert actions.count("moderation.flagged") == 1
    assert "post.published" in actions
    assert "account.connected" in actions
    assert "post.created" in actions
    assert len(actions) == 4
    times = [i["at"] for i in resp.json()["items"]]
    assert times == sorted(times, reverse=True)


async def test_export_contains_client_data_and_no_tokens(client, orgs, session_factory):
    await create_platform_account(session_factory, orgs.org_a, orgs.client_a, platform="linkedin")
    await create_content_row(session_factory, orgs.org_a, orgs.client_a, body="Our post")
    await create_content_row(session_factory, orgs.org_b, orgs.client_b, body="Foreign post")
    resp = await client.get(
        f"{API}/workspace/export?client_id={orgs.client_a}", headers=orgs.headers
    )
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    assert "enc-token" not in resp.text
    data = resp.json()
    assert data["client"]["brand_name"] == "Sunrise Coffee"
    assert [p["body"] for p in data["posts"]] == ["Our post"]
    assert data["counts"]["connected_accounts"] == 1
    assert "access_token_enc" not in data["connected_accounts"][0]


async def test_posting_prefs_round_trip_and_feed_brand_prompt(client, orgs, session_factory):
    url = f"{API}/workspace/posting-prefs?client_id={orgs.client_a}"
    resp = await client.put(
        url, json={"voice_register": "Bold & punchy", "cadence_per_week": 7}, headers=orgs.headers
    )
    assert resp.status_code == 200
    got = (await client.get(url, headers=orgs.headers)).json()["posting_prefs"]
    assert got["voice_register"] == "Bold & punchy" and got["cadence_per_week"] == 7

    bad = await client.put(url, json={"cadence_per_week": 4}, headers=orgs.headers)
    assert bad.status_code == 422

    block = brand_prompt_block({"brand_name": "X", "setup": {"posting_prefs": got}})
    assert "Voice register: Bold & punchy" in block
    assert "7 posts a week" in block


# --- Signals written by the gate -------------------------------------------


async def test_pre_approval_edit_is_recorded(client, orgs, session_factory):
    cid = await create_content_row(session_factory, orgs.org_a, orgs.client_a, body="v1")
    resp = await client.patch(f"{API}/content/{cid}", json={"body": "v2"}, headers=orgs.headers)
    assert resp.status_code == 200
    async with session_factory() as s:
        row = (await s.execute(select(ContentPiece).where(ContentPiece.id == cid))).scalar_one()
    assert row.metadata_.get("edited_before_approval") is True


async def test_moderation_refusal_is_recorded_without_touching_the_piece(
    client, orgs, session_factory, monkeypatch
):
    flagged = SimpleNamespace(
        content='{"issues": [{"severity": "high", "message": "Guarantees results."}]}'
    )

    class Brain:
        async def ainvoke(self, _p: Any) -> SimpleNamespace:
            return flagged

    monkeypatch.setattr("agency.services.llm_provider.get_brain_llm", lambda *a, **k: Brain())
    cid = await create_content_row(session_factory, orgs.org_a, orgs.client_a)
    resp = await client.post(f"{API}/content/{cid}/approve", headers=orgs.headers)
    assert resp.status_code == 409
    async with session_factory() as s:
        row = (await s.execute(select(ContentPiece).where(ContentPiece.id == cid))).scalar_one()
        events = (
            (
                await s.execute(
                    select(ProductEvent).where(ProductEvent.name == pa.MODERATION_FLAGGED)
                )
            )
            .scalars()
            .all()
        )
    assert row.status == "draft" and "moderation" not in (row.metadata_ or {})
    assert len(events) == 1 and events[0].properties["client_id"] == str(orgs.client_a)

    data = (
        await client.get(f"{API}/insights/summary?client_id={orgs.client_a}", headers=orgs.headers)
    ).json()
    assert data["moderation"] == {
        "checks": 1,
        "flagged": 1,
        "clean": {"status": "insufficient_data", "value": None, "count": 0, "n": 1, "needed": 3},
    }
