"""POST /campaigns/suggestions — angles in code, validated briefs, charge on success only.

The LLM is a stub; SQL, tenancy filters and quota arithmetic run for real
against the SQLite test database. Nothing is saved by this endpoint, so the
side effects checked are the generation counter and the campaign table.
"""

import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select

from agency.models.tables import BrandProfile, Campaign, Subscription
from agency.services.campaign_suggestions import (
    ANGLES,
    claims_predicted_result,
    load_past_campaigns,
    normalise_channels,
    plan_angles,
    repair_dates,
    resembles_angle,
    validate_suggestions,
)
from tests.conftest import (
    _persist,
    auth_header_for,
    create_client_row,
    create_org,
    create_subscription,
    create_user_row,
)

URL = "/api/v1/campaigns/suggestions"
TODAY = datetime.now(UTC).date()
WINDOW = (TODAY, TODAY + timedelta(days=29))


def _suggestion(angle: str, name: str, **over: Any) -> dict[str, Any]:
    base = {
        "angle": angle,
        "campaign_name": name,
        "objective": "Grow demo bookings among operations leads at mid-size firms.",
        "target_audience": "Operations leads at 50-500 person companies",
        "key_messages": ["Setup takes an afternoon", "Your data stays yours"],
        "channels": ["linkedin", "twitter"],
        "start_date": WINDOW[0].isoformat(),
        "end_date": (WINDOW[0] + timedelta(days=14)).isoformat(),
        "additional_context": "Avoid naming competitors.",
        "rationale": "The brand's differentiator is speed of setup, which ops leads care about.",
    }
    base.update(over)
    return base


def _reply(*items: dict[str, Any]) -> dict[str, Any]:
    return {"suggestions": list(items)}


GOOD = _reply(
    _suggestion("launch_offer", "Afternoon Setup Week"),
    _suggestion("thought_leadership", "Ops Lessons Series"),
    _suggestion("community", "Ops Leads Roundtable"),
)


class StubLLM:
    def __init__(self, reply: Any):
        self.reply = reply if isinstance(reply, str) else json.dumps(reply)
        self.calls: list[Any] = []
        self.configs: list[Any] = []

    async def ainvoke(self, messages: Any, config: Any = None) -> SimpleNamespace:
        self.calls.append(messages)
        self.configs.append(config)
        return SimpleNamespace(content=self.reply)


class FailingLLM(StubLLM):
    async def ainvoke(self, messages: Any, config: Any = None) -> SimpleNamespace:
        self.calls.append(messages)
        raise RuntimeError("provider 503")


@pytest.fixture
def stub_llm(monkeypatch):
    def _install(reply: Any = GOOD, *, fail: bool = False) -> StubLLM:
        stub = FailingLLM(reply) if fail else StubLLM(reply)
        stub.temperatures = []  # type: ignore[attr-defined]

        def _worker(temperature: float = 0.7):
            stub.temperatures.append(temperature)  # type: ignore[attr-defined]
            return stub

        monkeypatch.setattr("agency.services.campaign_suggestions.get_worker_llm", _worker)
        return stub

    return _install


async def _brand_profile(session_factory, org_id, client_id):
    await _persist(
        session_factory,
        BrandProfile(
            client_id=client_id,
            org_id=org_id,
            voice_description="plain and direct",
            target_audience="operations leads",
            tone_attributes={},
            vocabulary_include=[],
            vocabulary_exclude=[],
            example_posts=[],
            style_rules=[],
        ),
    )


async def _campaign(session_factory, org_id, client_id, name, objective="", start=None):
    start = start or TODAY - timedelta(days=60)
    row = Campaign(
        org_id=org_id,
        client_id=client_id,
        name=name,
        objective=objective,
        channels=["linkedin"],
        start_date=start,
        end_date=start + timedelta(days=10),
        budget={},
        agent_plan={},
        status="completed",
    )
    await _persist(session_factory, row)


@pytest.fixture
async def org(session_factory):
    org_id = await create_org(session_factory, "Org S")
    await create_subscription(session_factory, org_id, plan_tier="starter")
    user_id = await create_user_row(session_factory, org_id)
    client_id = await create_client_row(session_factory, org_id, "Brand S")
    await _brand_profile(session_factory, org_id, client_id)
    return SimpleNamespace(
        org_id=org_id, client_id=client_id, headers=auth_header_for(org_id, user_id=user_id)
    )


async def _generations_used(session_factory, org_id) -> int:
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        return int(sub.generations_used or 0)


async def _campaign_count(session_factory) -> int:
    async with session_factory() as s:
        return int((await s.execute(select(func.count(Campaign.id)))).scalar_one())


async def _post(client, org, **body: Any):
    return await client.post(
        URL, json={"client_id": str(org.client_id), **body}, headers=org.headers
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
async def test_happy_path_returns_three_with_assigned_angles(
    client, org, session_factory, stub_llm
):
    stub = stub_llm()
    resp = await _post(client, org, hint="We open a Pune office in December")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["client_id"] == str(org.client_id)
    assert data["window"] == {
        "start_date": WINDOW[0].isoformat(),
        "end_date": WINDOW[1].isoformat(),
    }
    # No history → "timely" is the angle left out.
    assert [s["angle"] for s in data["suggestions"]] == [
        "launch_offer", "thought_leadership", "community",
    ]
    assert await _generations_used(session_factory, org.org_id) == 1
    assert await _campaign_count(session_factory) == 0  # saves nothing

    assert stub.temperatures == [0.7]  # worker tier
    assert len(stub.calls) == 1
    prompt = stub.calls[0][1].content
    assert "plain and direct" in prompt
    assert "We open a Pune office in December" in prompt
    assert WINDOW[0].isoformat() in prompt and WINDOW[1].isoformat() in prompt
    # trace_config was passed (it is {} when Langfuse is off).
    assert stub.configs[0] is not None


async def test_model_angles_are_overridden_with_assigned_ones(
    client, org, session_factory, stub_llm
):
    stub_llm(
        _reply(
            _suggestion("timely", "One"),
            _suggestion("timely", "Two Campaign"),
            _suggestion("bogus", "Three Campaign"),
        )
    )
    resp = await _post(client, org)
    assert resp.status_code == 200, resp.text
    assert [s["angle"] for s in resp.json()["suggestions"]] == [
        "launch_offer", "thought_leadership", "community",
    ]


async def test_malformed_json_is_502_and_not_charged(client, org, session_factory, stub_llm):
    stub_llm("this is not json at all")
    resp = await _post(client, org)
    assert resp.status_code == 502
    assert "no quota was used" in resp.json()["detail"]
    assert await _generations_used(session_factory, org.org_id) == 0


async def test_provider_failure_is_502_and_not_charged(client, org, session_factory, stub_llm):
    stub_llm(fail=True)
    resp = await _post(client, org)
    assert resp.status_code == 502
    assert "no quota was used" in resp.json()["detail"]
    assert await _generations_used(session_factory, org.org_id) == 0


async def test_only_one_valid_suggestion_is_502_and_not_charged(
    client, org, session_factory, stub_llm
):
    stub_llm(
        _reply(
            _suggestion("launch_offer", "Afternoon Setup Week"),
            _suggestion("thought_leadership", "Ops Lessons", channels=["google_ads"]),
            _suggestion("community", "x"),  # name too short
        )
    )
    resp = await _post(client, org)
    assert resp.status_code == 502
    assert "no quota was used" in resp.json()["detail"]
    assert await _generations_used(session_factory, org.org_id) == 0


async def test_two_valid_suggestions_are_returned_and_charged(
    client, org, session_factory, stub_llm
):
    stub_llm(
        _reply(
            _suggestion("launch_offer", "Afternoon Setup Week"),
            _suggestion("thought_leadership", "Ops Lessons Series"),
            _suggestion("community", "Roundtable", rationale="Expected to lift signups by 30%."),
        )
    )
    resp = await _post(client, org)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["suggestions"]) == 2
    assert await _generations_used(session_factory, org.org_id) == 1


async def test_paid_and_unknown_channels_are_stripped(client, org, stub_llm):
    stub_llm(
        _reply(
            _suggestion(
                "launch_offer",
                "Afternoon Setup Week",
                channels=["LinkedIn", "google_ads", "meta", "X", "myspace", "linkedin"],
            ),
            _suggestion("thought_leadership", "Ops Lessons Series", channels=["instagram_ads"]),
            _suggestion("community", "Ops Leads Roundtable", channels=["tiktok", "facebook"]),
        )
    )
    resp = await _post(client, org)
    assert resp.status_code == 200, resp.text
    suggestions = resp.json()["suggestions"]
    # The one with only a paid channel is dropped entirely.
    assert [s["campaign_name"] for s in suggestions] == [
        "Afternoon Setup Week", "Ops Leads Roundtable",
    ]
    assert suggestions[0]["channels"] == ["linkedin", "twitter"]
    assert suggestions[1]["channels"] == ["tiktok", "facebook"]


async def test_out_of_window_dates_are_repaired(client, org, stub_llm):
    start = TODAY + timedelta(days=5)
    end = TODAY + timedelta(days=20)
    stub_llm(
        _reply(
            _suggestion("launch_offer", "Afternoon Setup Week", start_date="2020-01-01",
                        end_date="2099-12-31"),
            _suggestion("thought_leadership", "Ops Lessons Series", start_date="garbage",
                        end_date=None),
            _suggestion("community", "Ops Leads Roundtable",
                        start_date=(end + timedelta(days=3)).isoformat(),
                        end_date=start.isoformat()),
        )
    )
    resp = await _post(client, org, start_date=start.isoformat(), end_date=end.isoformat())
    assert resp.status_code == 200, resp.text
    got = [(s["start_date"], s["end_date"]) for s in resp.json()["suggestions"]]
    s, e = start.isoformat(), end.isoformat()
    assert got == [(s, e), (s, e), (e, e)]


async def test_predicted_metric_rationale_is_dropped(client, org, stub_llm):
    stub_llm(
        _reply(
            _suggestion("launch_offer", "Afternoon Setup Week"),
            _suggestion("thought_leadership", "Ops Lessons Series",
                        rationale="This should drive a 4% CTR on LinkedIn."),
            _suggestion("community", "Ops Leads Roundtable"),
        )
    )
    resp = await _post(client, org)
    assert resp.status_code == 200, resp.text
    assert [s["angle"] for s in resp.json()["suggestions"]] == ["launch_offer", "community"]


async def test_forecast_in_key_messages_or_context_is_not_passed_on(client, org, stub_llm):
    stub_llm(
        _reply(
            _suggestion("launch_offer", "Afternoon Setup Week",
                        key_messages=["Setup in one afternoon",
                                      "Expected to boost signups by 40%"]),
            _suggestion("thought_leadership", "Ops Lessons Series",
                        additional_context="This will generate 10k impressions."),
            _suggestion("community", "Ops Leads Roundtable"),
        )
    )
    resp = await _post(client, org)
    assert resp.status_code == 200, resp.text
    suggestions = resp.json()["suggestions"]
    assert [s["angle"] for s in suggestions] == ["launch_offer", "community"]
    assert suggestions[0]["key_messages"] == ["Setup in one afternoon"]


async def test_yesterday_start_is_accepted_for_users_west_of_utc(client, org, stub_llm):
    # The form sends the user's local date; west of UTC that is the server's yesterday.
    stub_llm(
        _reply(
            _suggestion("launch_offer", "Afternoon Setup Week"),
            _suggestion("thought_leadership", "Ops Lessons Series"),
        )
    )
    resp = await _post(client, org, start_date=(TODAY - timedelta(days=1)).isoformat())
    assert resp.status_code == 200, resp.text


async def test_form_label_value_is_rejected(client, org, stub_llm):
    stub_llm(
        _reply(
            _suggestion("launch_offer", "Afternoon Setup Week"),
            _suggestion("thought_leadership", "Campaign Name *"),
            _suggestion("community", "Ops Leads Roundtable",
                        key_messages=["Key Messages", "Come share a war story"]),
        )
    )
    resp = await _post(client, org)
    assert resp.status_code == 200, resp.text
    suggestions = resp.json()["suggestions"]
    assert [s["angle"] for s in suggestions] == ["launch_offer", "community"]
    assert suggestions[1]["key_messages"] == ["Come share a war story"]


async def test_key_messages_are_trimmed_to_five(client, org, stub_llm):
    stub_llm(
        _reply(
            _suggestion("launch_offer", "Afternoon Setup Week",
                        key_messages=[f"Message {i}" for i in range(8)]),
            _suggestion("thought_leadership", "Ops Lessons Series"),
        )
    )
    resp = await _post(client, org)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["suggestions"][0]["key_messages"]) == 5


async def test_quota_exhausted_is_402_before_llm(client, session_factory, stub_llm):
    org_id = await create_org(session_factory)
    await create_subscription(session_factory, org_id, plan_tier="starter",
                              generations_used=5, generations_limit=5)
    user_id = await create_user_row(session_factory, org_id)
    client_id = await create_client_row(session_factory, org_id)
    await _brand_profile(session_factory, org_id, client_id)
    stub = stub_llm()
    resp = await client.post(
        URL, json={"client_id": str(client_id)}, headers=auth_header_for(org_id, user_id=user_id)
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["code"] == "generation_quota_exceeded"
    assert stub.calls == []


async def test_no_brand_profile_is_409(client, session_factory, stub_llm):
    org_id = await create_org(session_factory)
    await create_subscription(session_factory, org_id, plan_tier="starter")
    user_id = await create_user_row(session_factory, org_id)
    client_id = await create_client_row(session_factory, org_id)
    stub = stub_llm()
    resp = await client.post(
        URL, json={"client_id": str(client_id)}, headers=auth_header_for(org_id, user_id=user_id)
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "brand_profile_required"
    assert stub.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"start_date": (TODAY + timedelta(days=10)).isoformat(),
         "end_date": (TODAY + timedelta(days=5)).isoformat()},
        {"start_date": TODAY.isoformat(), "end_date": (TODAY + timedelta(days=92)).isoformat()},
        {"start_date": (TODAY - timedelta(days=2)).isoformat()},
        {"hint": "x" * 501},
    ],
    ids=["end_before_start", "window_over_92_days", "start_in_past", "hint_too_long"],
)
async def test_bad_window_is_422(client, org, session_factory, stub_llm, body):
    stub = stub_llm()
    resp = await _post(client, org, **body)
    assert resp.status_code == 422
    assert stub.calls == []
    assert await _generations_used(session_factory, org.org_id) == 0


async def test_92_day_window_and_defaults_are_accepted(client, org, stub_llm):
    stub_llm()
    resp = await _post(
        client, org,
        start_date=TODAY.isoformat(),
        end_date=(TODAY + timedelta(days=91)).isoformat(),
    )
    assert resp.status_code == 200, resp.text
    start = TODAY + timedelta(days=3)
    resp = await _post(client, org, start_date=start.isoformat())
    assert resp.status_code == 200, resp.text
    assert resp.json()["window"]["end_date"] == (start + timedelta(days=29)).isoformat()


async def test_disconnected_client_is_not_charged(org, session_factory, stub_llm):
    from fastapi import HTTPException

    from agency.models.schemas import CampaignSuggestionRequest
    from agency.services.campaign_suggestions import suggest_campaigns

    stub = stub_llm()

    async def gone() -> bool:
        return True

    async with session_factory() as db:
        with pytest.raises(HTTPException) as exc:
            await suggest_campaigns(
                db,
                org_id=org.org_id,
                body=CampaignSuggestionRequest(client_id=org.client_id),
                cancelled=gone,
            )
    assert exc.value.status_code == 409
    assert len(stub.calls) == 1
    assert await _generations_used(session_factory, org.org_id) == 0


async def test_requires_campaign_run_capability(client, org, session_factory, stub_llm):
    viewer = await create_user_row(session_factory, org.org_id, role="viewer")
    stub = stub_llm()
    resp = await client.post(
        URL,
        json={"client_id": str(org.client_id)},
        headers=auth_header_for(org.org_id, "viewer", user_id=viewer),
    )
    assert resp.status_code == 403
    assert stub.calls == []


async def test_past_campaigns_reach_prompt_and_shape_angles(
    client, org, session_factory, stub_llm
):
    await _campaign(session_factory, org.org_id, org.client_id, "Old Webinar Series",
                    "Educate ops leads with a monthly expert webinar",
                    start=TODAY - timedelta(days=20))
    await _campaign(session_factory, org.org_id, org.client_id, "Spring Promo",
                    "Discount launch", start=TODAY - timedelta(days=200))
    stub = stub_llm(
        _reply(
            _suggestion("launch_offer", "Afternoon Setup Week"),
            _suggestion("community", "Ops Leads Roundtable"),
            _suggestion("timely", "Year End Ops Reset"),
        )
    )
    resp = await _post(client, org)
    assert resp.status_code == 200, resp.text
    # Most recent campaign was thought leadership, so that angle is left out.
    assert [s["angle"] for s in resp.json()["suggestions"]] == [
        "launch_offer", "community", "timely",
    ]
    prompt = stub.calls[0][1].content
    assert "Old Webinar Series" in prompt and "Spring Promo" in prompt


async def test_suggestion_repeating_past_name_is_dropped(client, org, session_factory, stub_llm):
    await _campaign(session_factory, org.org_id, org.client_id, "Afternoon Setup Week")
    stub_llm()
    resp = await _post(client, org)
    assert resp.status_code == 200, resp.text
    names = [s["campaign_name"] for s in resp.json()["suggestions"]]
    assert "Afternoon Setup Week" not in names and len(names) == 2


async def test_past_campaign_query_is_org_and_client_scoped(session_factory, org):
    other_org = await create_org(session_factory, "Other")
    other_client = await create_client_row(session_factory, org.org_id, "Sibling Brand")
    foreign_client = await create_client_row(session_factory, other_org, "Foreign")
    await _campaign(session_factory, org.org_id, org.client_id, "Mine")
    # Another org's row stamped with this client's id — only the org filter stops it.
    await _campaign(session_factory, other_org, org.client_id, "Cross Tenant Leak")
    # Same org, different client — only the client filter stops it.
    await _campaign(session_factory, org.org_id, other_client, "Sibling Campaign")
    await _campaign(session_factory, other_org, foreign_client, "Foreign Campaign")

    async with session_factory() as db:
        past = await load_past_campaigns(db, org_id=org.org_id, client_id=org.client_id)
    assert [p["name"] for p in past] == ["Mine"]


async def test_past_campaigns_limited_to_ten_newest_first(session_factory, org):
    for i in range(12):
        await _campaign(session_factory, org.org_id, org.client_id, f"Campaign {i:02d}",
                        start=TODAY - timedelta(days=100 - i))
    async with session_factory() as db:
        past = await load_past_campaigns(db, org_id=org.org_id, client_id=org.client_id)
    assert len(past) == 10
    assert past[0]["name"] == "Campaign 11"


async def test_other_orgs_client_is_404(client, org, session_factory, stub_llm):
    other = await create_org(session_factory, "Other")
    await create_subscription(session_factory, other, plan_tier="starter")
    other_client = await create_client_row(session_factory, other)
    await _brand_profile(session_factory, other, other_client)
    stub = stub_llm()
    resp = await client.post(
        URL, json={"client_id": str(other_client)}, headers=org.headers
    )
    assert resp.status_code == 404
    assert stub.calls == []
    assert await _generations_used(session_factory, org.org_id) == 0
    assert await _generations_used(session_factory, other) == 0


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def test_plan_angles_returns_three_distinct_known_angles():
    for past in ([], [{"name": "Holiday push", "objective": "Christmas sale"}],
                 [{"name": "Something", "objective": "unrelated"}]):
        angles = plan_angles(past)
        assert len(angles) == 3
        assert len(set(angles)) == 3
        assert set(angles) <= set(ANGLES)


def test_plan_angles_drops_what_the_latest_campaign_resembles():
    assert "timely" not in plan_angles([])
    assert "community" not in plan_angles(
        [{"name": "Customer spotlight", "objective": "Community stories from members"}]
    )
    # Only the newest one counts.
    assert "launch_offer" not in plan_angles(
        [{"name": "Spring launch", "objective": "Discount offer"},
         {"name": "Community month", "objective": "Members"}]
    )
    assert plan_angles([{"name": "Q3", "objective": "unrelated words"}]) == [
        "launch_offer", "thought_leadership", "community",
    ]


def test_resembles_angle_whole_words_only():
    assert resembles_angle("Promotional calendar") is None  # "promo" inside a word
    assert resembles_angle("Black Friday promo") in {"launch_offer", "timely"}


@pytest.mark.parametrize(
    "text",
    [
        "Expected 30% lift in signups.",
        "This campaign will reach 10k founders.",
        "Projected to generate 200 leads.",
        "Should drive a 4% CTR.",
        "Aim for an engagement rate of 6%.",
        "A 3x ROAS is realistic here.",
        "This will double demo bookings.",
        "Likely to add $50,000 in pipeline.",
        "Could earn 1,200 new followers this month.",
    ],
)
def test_predicted_results_are_detected(text):
    assert claims_predicted_result(text)


@pytest.mark.parametrize(
    "text",
    [
        "Grow demo bookings among ops leads.",
        "Grow demo bookings by 20% this quarter.",
        "Post 3 times a week on LinkedIn for 4 weeks.",
        "Ops leads are planning 2027 budgets now, so the timing fits.",
        "The brand will run a 6-week series.",
        "",
    ],
)
def test_goals_and_plain_numbers_pass(text):
    assert not claims_predicted_result(text)


def test_normalise_channels():
    assert normalise_channels(["X", "LinkedIn", "google_ads", "linkedin", 3, "meta"]) == [
        "twitter", "linkedin",
    ]
    assert normalise_channels("linkedin") == []


def test_repair_dates():
    lo, hi = date(2030, 1, 1), date(2030, 1, 31)
    assert repair_dates("2029-12-01", "2031-01-01", (lo, hi)) == (lo, hi)
    assert repair_dates(None, None, (lo, hi)) == (lo, hi)
    assert repair_dates("2030-01-20", "2030-01-10", (lo, hi)) == (
        date(2030, 1, 20), date(2030, 1, 20),
    )


def test_validate_suggestions_clips_long_fields_and_matches_by_position():
    long_objective = "Grow demo bookings among ops leads. " * 30
    raw = [
        _suggestion("whatever", "Afternoon Setup Week", objective=long_objective,
                    rationale="Because. " * 100),
        _suggestion("whatever", "Ops Lessons Series"),
    ]
    out = validate_suggestions(raw, ["community", "timely"], WINDOW)
    assert [s["angle"] for s in out] == ["community", "timely"]
    assert len(out[0]["objective"]) <= 500
    assert len(out[0]["rationale"]) <= 400


def test_validate_suggestions_drops_duplicate_names():
    raw = _reply(
        _suggestion("launch_offer", "Same Name"),
        _suggestion("community", "same name"),
    )
    out = validate_suggestions(raw, ["launch_offer", "community"], WINDOW)
    assert len(out) == 1


def test_reply_diagnostics_names_the_model_and_why_it_stopped():
    """A usable=0 log must say which provider answered: fallbacks switch silently."""
    from agency.services.campaign_suggestions import reply_diagnostics

    response = SimpleNamespace(
        content=[{"type": "thinking", "thinking": ""}, {"type": "text", "text": "Sorry, I can't"}],
        response_metadata={"model": "gemini-x", "stop_reason": "max_tokens"},
        usage_metadata={"output_tokens": 4096},
    )
    out = reply_diagnostics(response, "Sorry, I can't" + "x" * 500, {"raw_output": "..."})
    assert out["reply_model"] == "gemini-x"
    assert out["stop_reason"] == "max_tokens"
    assert out["output_tokens"] == 4096
    assert out["content_blocks"] == ["thinking", "text"]
    assert out["parsed_shape"] == ["raw_output"]
    assert len(out["text_head"]) == 300


def test_reply_diagnostics_tolerates_a_bare_string_reply():
    from agency.services.campaign_suggestions import reply_diagnostics

    out = reply_diagnostics(SimpleNamespace(content="hi"), "hi", [])
    assert out["reply_model"] is None
    assert out["content_blocks"] == "str"
    assert out["parsed_shape"] == "list"
