"""Create › Email and Create › Launch — generate → validate → save → charge.

The LLM is a stub; SQL, tenancy filters and quota arithmetic run for real
against the SQLite test database. Each tenancy test uses a cross-tenant id that
would succeed if its ``org_id`` filter were removed (the other org's client has
a brand profile and quota), so the test fails when the filter goes.
"""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from agency.agents.launch_pr import build_launch_kit_prompt
from agency.models.tables import BrandProfile, Client, CreativeAsset, Subscription
from agency.services.create_kits import (
    EMAIL_CAMPAIGN_TYPES,
    ShapeError,
    asset_title,
    validate_community_kit,
    validate_email_campaign,
    validate_launch_kit,
    validate_outreach_pitch,
    validate_prfaq,
)
from tests.conftest import (
    _persist,
    auth_header_for,
    create_client_row,
    create_org,
    create_subscription,
    create_user_row,
)

EMAIL = "/api/v1/create/email"
LAUNCH = "/api/v1/create/launch"
FOCUS = "Recruiting 20 beta testers this month"

EMAIL_REPLY = {
    "subjectLine": "Your first roast ships Friday",
    "subjectLineB": "What happens after you sign up",
    "previewText": "One step to get your first bag on its way",
    "segmentNote": "Everyone who signed up in the last 24 hours",
    "sendTimeNote": "Immediately after signup",
    "body": "Welcome aboard.\n\nPick your grind and we'll handle the rest.",
}
PRFAQ_REPLY = {
    "pressReleaseHeadline": "Sunrise Coffee makes fresh roast a Friday habit",
    "pressReleaseBody": "Today Sunrise Coffee...",
    "customerFAQ": [{"question": "Why pay more?", "answer": "Roasted within 48 hours."}],
    "internalFAQ": [{"question": "Is this defensible?", "answer": "Only with local ops."}],
    "weakestClaim": "Fresher than the rest",
    "sharperVersionNote": "Say roasted-on date and delivery window",
}
LAUNCH_REPLY = {
    "tagline": "Fresh roast, every Friday",
    "phDescription": "A coffee subscription for home brewers.",
    "makerComment": "We built this because...",
    "launchTimingNote": "12:01am PST, Tuesday",
    "whyNowHook": "Roasters are cutting freshness to cut costs",
    "pressPitchSubject": "A roaster that prints the roast date on the box",
    "pressPitchBody": "Hi — ...",
}
COMMUNITY_REPLY = {
    "channelStructure": ["#welcome — start here", "#brew-log — share your cup"],
    "welcomeMessage": "Post your grinder in #brew-log",
    "engagementPrompts": ["What did you brew this week?", "Worst coffee mistake?"],
    "eventAnnouncementTemplate": "AMA with our roaster on {date}",
    "moderationNote": "Reply to every first post within a day.",
}
OUTREACH_REPLY = {
    "targetType": "Micro-influencer",
    "subject": "A roast named after your channel?",
    "pitchBody": "Hi — ...",
    "specificAsk": "Can we send you two bags next week?",
    "economicsNote": "Product access plus revenue share is typical at this stage.",
}


class StubLLM:
    def __init__(self, reply: Any):
        self.reply = reply if isinstance(reply, str) else json.dumps(reply)
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
    """Replace every tier getter the two agents use; records which tier ran."""

    def _install(reply: Any = None, *, fail: bool = False):
        stub: Any = FailingLLM() if fail else StubLLM(reply)
        stub.tiers = []

        def _worker(temperature: float = 0.7):
            stub.tiers.append("worker")
            return stub

        def _brain():
            stub.tiers.append("brain")
            return stub

        monkeypatch.setattr("agency.agents.lifecycle_email.get_worker_llm", _worker)
        monkeypatch.setattr("agency.agents.launch_pr.get_worker_llm", _worker)
        monkeypatch.setattr("agency.agents.launch_pr.get_brain_llm", _brain)
        return stub

    return _install


async def _brand_profile(session_factory, org_id, client_id):
    await _persist(
        session_factory,
        BrandProfile(
            client_id=client_id,
            org_id=org_id,
            voice_description="warm and neighbourly",
            target_audience="home brewers",
            tone_attributes={},
            vocabulary_include=[],
            vocabulary_exclude=["synergy"],
            example_posts=[],
            style_rules=[],
        ),
    )


async def _set_settings(session_factory, client_id, settings):
    async with session_factory() as s:
        row = await s.get(Client, client_id)
        row.settings = settings
        await s.commit()


@pytest.fixture
async def orgs(session_factory):
    out = {}
    for key in ("a", "b"):
        org_id = await create_org(session_factory, f"Org {key}")
        await create_subscription(session_factory, org_id, plan_tier="starter")
        user_id = await create_user_row(session_factory, org_id)
        client_id = await create_client_row(session_factory, org_id, f"Brand {key}")
        await _brand_profile(session_factory, org_id, client_id)
        out[key] = SimpleNamespace(
            org_id=org_id,
            client_id=client_id,
            headers=auth_header_for(org_id, user_id=user_id),
        )
    return SimpleNamespace(**out)


async def _generations_used(session_factory, org_id) -> int:
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        return int(sub.generations_used or 0)


async def _assets(session_factory, org_id=None) -> list[CreativeAsset]:
    async with session_factory() as s:
        q = select(CreativeAsset)
        if org_id is not None:
            q = q.where(CreativeAsset.org_id == org_id)
        return list((await s.execute(q)).scalars().all())


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
async def test_email_generate_saves_asset_and_charges_once(client, orgs, session_factory, stub_llm):
    await _set_settings(
        session_factory, orgs.a.client_id, {"campaign_focus": {"description": FOCUS}}
    )
    stub = stub_llm(EMAIL_REPLY)
    resp = await client.post(
        f"{EMAIL}/generate",
        json={"client_id": str(orgs.a.client_id), "campaign_type": "welcome"},
        headers=orgs.a.headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["kind"] == "email_campaign"
    assert data["title"] == EMAIL_REPLY["subjectLine"]
    assert data["payload"]["campaign_type"] == "welcome"
    assert data["payload"]["subject_line_b"] == EMAIL_REPLY["subjectLineB"]
    assert await _generations_used(session_factory, orgs.a.org_id) == 1
    assert stub.tiers == ["worker"]

    prompt = stub.calls[0][1].content
    assert EMAIL_CAMPAIGN_TYPES["welcome"] in prompt
    assert "warm and neighbourly" in prompt and "synergy" in prompt
    assert FOCUS in prompt  # email reads the campaign focus


async def test_email_rejects_unknown_campaign_type(client, orgs, stub_llm):
    stub_llm(EMAIL_REPLY)
    resp = await client.post(
        f"{EMAIL}/generate",
        json={"client_id": str(orgs.a.client_id), "campaign_type": "blast"},
        headers=orgs.a.headers,
    )
    assert resp.status_code == 422


async def test_email_other_orgs_client_is_404(client, orgs, session_factory, stub_llm):
    stub = stub_llm(EMAIL_REPLY)
    resp = await client.post(
        f"{EMAIL}/generate",
        json={"client_id": str(orgs.b.client_id), "campaign_type": "welcome"},
        headers=orgs.a.headers,
    )
    assert resp.status_code == 404
    assert stub.calls == []
    assert await _assets(session_factory) == []
    assert await _generations_used(session_factory, orgs.a.org_id) == 0
    assert await _generations_used(session_factory, orgs.b.org_id) == 0


async def test_email_requires_brand_profile(client, session_factory, stub_llm):
    org_id = await create_org(session_factory)
    await create_subscription(session_factory, org_id, plan_tier="starter")
    client_id = await create_client_row(session_factory, org_id)
    stub = stub_llm(EMAIL_REPLY)
    resp = await client.post(
        f"{EMAIL}/generate",
        json={"client_id": str(client_id), "campaign_type": "welcome"},
        headers=auth_header_for(org_id),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "brand_profile_required"
    assert stub.calls == []


async def test_brand_profile_gate_ignores_other_orgs_profile(client, session_factory, stub_llm):
    """A profile row stamped with another org does not unlock this client."""
    org_id = await create_org(session_factory, "Mine")
    other = await create_org(session_factory, "Theirs")
    await create_subscription(session_factory, org_id, plan_tier="starter")
    client_id = await create_client_row(session_factory, org_id)
    await _brand_profile(session_factory, other, client_id)
    stub_llm(EMAIL_REPLY)
    resp = await client.post(
        f"{EMAIL}/generate",
        json={"client_id": str(client_id), "campaign_type": "welcome"},
        headers=auth_header_for(org_id),
    )
    assert resp.status_code == 409


async def test_email_quota_exhausted_never_calls_model(client, session_factory, stub_llm):
    org_id = await create_org(session_factory)
    await create_subscription(session_factory, org_id, generations_used=10, generations_limit=10)
    client_id = await create_client_row(session_factory, org_id)
    await _brand_profile(session_factory, org_id, client_id)
    stub = stub_llm(EMAIL_REPLY)
    resp = await client.post(
        f"{EMAIL}/generate",
        json={"client_id": str(client_id), "campaign_type": "update"},
        headers=auth_header_for(org_id),
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["code"] == "generation_quota_exceeded"
    assert stub.calls == []
    assert await _generations_used(session_factory, org_id) == 10


@pytest.mark.parametrize("reply", ["I cannot help with that.", {**EMAIL_REPLY, "body": ""}])
async def test_email_malformed_reply_is_502_and_free(
    client, orgs, session_factory, stub_llm, reply
):
    stub_llm(reply)
    resp = await client.post(
        f"{EMAIL}/generate",
        json={"client_id": str(orgs.a.client_id), "campaign_type": "milestone"},
        headers=orgs.a.headers,
    )
    assert resp.status_code == 502
    assert "no quota was used" in resp.json()["detail"]
    assert await _assets(session_factory) == []
    assert await _generations_used(session_factory, orgs.a.org_id) == 0


async def test_email_llm_failure_is_502_and_free(client, orgs, session_factory, stub_llm):
    stub_llm(fail=True)
    resp = await client.post(
        f"{EMAIL}/generate",
        json={"client_id": str(orgs.a.client_id), "campaign_type": "onboarding"},
        headers=orgs.a.headers,
    )
    assert resp.status_code == 502
    assert await _generations_used(session_factory, orgs.a.org_id) == 0


# ---------------------------------------------------------------------------
# Launch — kits
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("mode", "reply", "title"),
    [
        ("launch_kit", LAUNCH_REPLY, LAUNCH_REPLY["tagline"]),
        ("community_kit", COMMUNITY_REPLY, COMMUNITY_REPLY["channelStructure"][0]),
        ("outreach_pitch", OUTREACH_REPLY, OUTREACH_REPLY["subject"]),
    ],
)
async def test_launch_generate_each_mode(
    client, orgs, session_factory, stub_llm, mode, reply, title
):
    await _set_settings(
        session_factory, orgs.a.client_id, {"campaign_focus": {"description": FOCUS}}
    )
    stub = stub_llm(reply)
    resp = await client.post(
        f"{LAUNCH}/generate",
        json={"client_id": str(orgs.a.client_id), "mode": mode},
        headers=orgs.a.headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["kind"] == mode
    assert data["title"] == title
    assert stub.tiers == ["worker"]
    assert FOCUS in stub.calls[0][1].content  # kits read the campaign focus
    assert await _generations_used(session_factory, orgs.a.org_id) == 1
    assert len(await _assets(session_factory, orgs.a.org_id)) == 1


async def test_launch_kit_addresses_stored_prfaq(client, orgs, session_factory, stub_llm):
    prfaq = validate_prfaq(PRFAQ_REPLY)
    await _set_settings(session_factory, orgs.a.client_id, {"prfaq": prfaq})
    stub = stub_llm(LAUNCH_REPLY)
    resp = await client.post(
        f"{LAUNCH}/generate",
        json={"client_id": str(orgs.a.client_id), "mode": "launch_kit"},
        headers=orgs.a.headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["payload"]["prfaq_addressed"] is True
    prompt = stub.calls[0][1].content
    assert PRFAQ_REPLY["weakestClaim"] in prompt and PRFAQ_REPLY["sharperVersionNote"] in prompt


def test_launch_kit_prompt_without_prfaq_has_no_stress_test_block():
    assert "PRFAQ" not in build_launch_kit_prompt({"brand_name": "X"}, None)


async def test_launch_generate_other_orgs_client_is_404(client, orgs, session_factory, stub_llm):
    stub = stub_llm(LAUNCH_REPLY)
    resp = await client.post(
        f"{LAUNCH}/generate",
        json={"client_id": str(orgs.b.client_id), "mode": "launch_kit"},
        headers=orgs.a.headers,
    )
    assert resp.status_code == 404
    assert stub.calls == []
    assert await _assets(session_factory) == []


async def test_launch_generate_rejects_unknown_mode(client, orgs, stub_llm):
    stub_llm(LAUNCH_REPLY)
    resp = await client.post(
        f"{LAUNCH}/generate",
        json={"client_id": str(orgs.a.client_id), "mode": "press_blast"},
        headers=orgs.a.headers,
    )
    assert resp.status_code == 422


async def test_launch_malformed_kit_is_502_and_free(client, orgs, session_factory, stub_llm):
    stub_llm({**COMMUNITY_REPLY, "channelStructure": []})
    resp = await client.post(
        f"{LAUNCH}/generate",
        json={"client_id": str(orgs.a.client_id), "mode": "community_kit"},
        headers=orgs.a.headers,
    )
    assert resp.status_code == 502
    assert await _assets(session_factory) == []
    assert await _generations_used(session_factory, orgs.a.org_id) == 0


# ---------------------------------------------------------------------------
# Launch — PRFAQ stress-test
# ---------------------------------------------------------------------------
async def test_prfaq_run_stores_on_client_and_ignores_campaign_focus(
    client, orgs, session_factory, stub_llm
):
    await _set_settings(
        session_factory, orgs.a.client_id, {"campaign_focus": {"description": FOCUS}}
    )
    stub = stub_llm(PRFAQ_REPLY)
    resp = await client.post(
        f"{LAUNCH}/prfaq", json={"client_id": str(orgs.a.client_id)}, headers=orgs.a.headers
    )
    assert resp.status_code == 200, resp.text
    prfaq = resp.json()["prfaq"]
    assert prfaq["weakest_claim"] == PRFAQ_REPLY["weakestClaim"]
    assert prfaq["generated_at"]
    assert stub.tiers == ["brain"]

    # The stress-test judges positioning on its own — never the campaign focus.
    prompt = stub.calls[0][1].content
    assert FOCUS not in prompt
    assert "warm and neighbourly" in prompt

    # Stored beside the focus without clobbering it; readable via GET.
    async with session_factory() as s:
        row = await s.get(Client, orgs.a.client_id)
        assert row.settings["campaign_focus"]["description"] == FOCUS
        assert (
            row.settings["prfaq"]["press_release_headline"] == PRFAQ_REPLY["pressReleaseHeadline"]
        )
    got = await client.get(
        f"{LAUNCH}/prfaq", params={"client_id": str(orgs.a.client_id)}, headers=orgs.a.headers
    )
    assert got.json()["prfaq"]["sharper_version_note"] == PRFAQ_REPLY["sharperVersionNote"]
    assert await _generations_used(session_factory, orgs.a.org_id) == 1
    assert await _assets(session_factory) == []  # not a list item


async def test_prfaq_get_empty_when_never_run(client, orgs):
    resp = await client.get(
        f"{LAUNCH}/prfaq", params={"client_id": str(orgs.a.client_id)}, headers=orgs.a.headers
    )
    assert resp.status_code == 200
    assert resp.json() == {"prfaq": None}


async def test_prfaq_get_other_orgs_client_is_404(client, orgs, session_factory):
    await _set_settings(session_factory, orgs.b.client_id, {"prfaq": validate_prfaq(PRFAQ_REPLY)})
    resp = await client.get(
        f"{LAUNCH}/prfaq", params={"client_id": str(orgs.b.client_id)}, headers=orgs.a.headers
    )
    assert resp.status_code == 404
    assert PRFAQ_REPLY["weakestClaim"] not in resp.text


async def test_prfaq_run_other_orgs_client_is_404(client, orgs, session_factory, stub_llm):
    stub = stub_llm(PRFAQ_REPLY)
    resp = await client.post(
        f"{LAUNCH}/prfaq", json={"client_id": str(orgs.b.client_id)}, headers=orgs.a.headers
    )
    assert resp.status_code == 404
    assert stub.calls == []
    async with session_factory() as s:
        assert "prfaq" not in ((await s.get(Client, orgs.b.client_id)).settings or {})


async def test_prfaq_malformed_is_502_free_and_keeps_previous(
    client, orgs, session_factory, stub_llm
):
    previous = validate_prfaq(PRFAQ_REPLY)
    await _set_settings(session_factory, orgs.a.client_id, {"prfaq": previous})
    stub_llm({**PRFAQ_REPLY, "customerFAQ": []})
    resp = await client.post(
        f"{LAUNCH}/prfaq", json={"client_id": str(orgs.a.client_id)}, headers=orgs.a.headers
    )
    assert resp.status_code == 502
    assert await _generations_used(session_factory, orgs.a.org_id) == 0
    async with session_factory() as s:
        assert (await s.get(Client, orgs.a.client_id)).settings["prfaq"] == previous


# ---------------------------------------------------------------------------
# Pure shape validation
# ---------------------------------------------------------------------------
def test_validators_accept_snake_case_and_normalise():
    snake = {
        "subject_line": " A ",
        "subject_line_b": "B",
        "preview_text": "p",
        "segment_note": "s",
        "send_time_note": "t",
        "body": "b",
    }
    out = validate_email_campaign(snake, "update")
    assert out["subject_line"] == "A" and out["campaign_type"] == "update"


@pytest.mark.parametrize(
    ("validator", "reply", "missing"),
    [
        (validate_launch_kit, LAUNCH_REPLY, "makerComment"),
        (validate_community_kit, COMMUNITY_REPLY, "engagementPrompts"),
        (validate_outreach_pitch, OUTREACH_REPLY, "specificAsk"),
        (validate_prfaq, PRFAQ_REPLY, "internalFAQ"),
    ],
)
def test_validators_reject_missing_fields(validator, reply, missing):
    validator(reply)  # the full reply passes
    with pytest.raises(ShapeError):
        validator({k: v for k, v in reply.items() if k != missing})


def test_validators_reject_non_objects():
    for bad in ([], "text", None):
        with pytest.raises(ShapeError):
            validate_launch_kit(bad)


def test_list_fields_drop_blank_entries():
    out = validate_community_kit({**COMMUNITY_REPLY, "engagementPrompts": ["one", "  ", 3]})
    assert out["engagement_prompts"] == ["one"]


def test_asset_title_per_kind():
    assert asset_title("community_kit", {"channel_structure": []}) == "Community kit"
    assert asset_title("outreach_pitch", {"subject": "Hi"}) == "Hi"
