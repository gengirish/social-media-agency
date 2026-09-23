"""Setup › Profile / Accounts endpoints, the no-wipe rule, and the OAuth state.

The LLM is replaced by a stub; SQL, tenancy filters and quota arithmetic run for
real against the SQLite test database. Tenancy tests assert on a cross-tenant
identifier, so each fails if its ``org_id`` filter is removed.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from agency.models.tables import BrandProfile, Client, CreativeAsset, Subscription
from agency.services.brand_context import brand_prompt_block
from agency.services.oauth_state import verify_state
from agency.services.setup_profile import (
    NORTH_STAR_KIND,
    apply_intake,
    north_star,
    with_north_star,
)
from tests.conftest import (
    _persist,
    auth_header_for,
    create_client_row,
    create_org,
    create_platform_account,
    create_subscription,
    create_user_row,
)

API = "/api/v1"


class StubLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[Any] = []

    async def ainvoke(self, messages: Any) -> SimpleNamespace:
        self.calls.append(messages)
        return SimpleNamespace(content=self.reply)


class FailingLLM:
    async def ainvoke(self, _messages: Any) -> SimpleNamespace:
        raise RuntimeError("provider 503")


@pytest.fixture
def stub_llm(monkeypatch):
    def _install(reply: Any = None, *, fail: bool = False):
        text = reply if isinstance(reply, str) else json.dumps(reply)
        stub: Any = FailingLLM() if fail else StubLLM(text)
        monkeypatch.setattr("agency.agents.setup_profile.get_worker_llm", lambda _t=0.7: stub)
        return stub

    return _install


@pytest.fixture
async def orgs(session_factory):
    org_a = await create_org(session_factory, "Org A", slug="org-a")
    org_b = await create_org(session_factory, "Org B", slug="org-b")
    await create_subscription(session_factory, org_a, plan_tier="starter")
    await create_subscription(session_factory, org_b, plan_tier="starter")
    user_a = await create_user_row(session_factory, org_a)
    user_b = await create_user_row(session_factory, org_b)
    return SimpleNamespace(
        org_a=org_a,
        org_b=org_b,
        client_a=await create_client_row(session_factory, org_a, "Brand A"),
        client_b=await create_client_row(session_factory, org_b, "Brand B"),
        headers_a=auth_header_for(org_a, user_id=user_a),
        headers_b=auth_header_for(org_b, user_id=user_b),
    )


INTAKE = {
    "url": "brand-a.example",
    "audience": "Independent roasters with one shop",
    "differentiator": "Roast-to-door in 48 hours",
    "tone": "Bold & punchy",
}

VOICE = {
    "voiceDescription": "Short, warm sentences.",
    "vocabularyDos": ["fresh", "roasted today", "fresh"],
    "vocabularyDonts": ["synergy"],
    "exampleSentence": "Roasted Monday, in your cup Wednesday.",
}

LENS = {
    "lenses": [
        {"framework": f, "origin": o, "critique": "c", "suggestion": "s"}
        for f, o in [
            ("Jobs-to-be-Done", "Christensen"),
            ("Category Design", "Dunford"),
            ("Blue Ocean", "Kim & Mauborgne"),
            ("Distinctive Assets", "Sharp"),
        ]
    ],
    "tension": "Speed vs memorability.",
    "synthesis": "Name the 48-hour promise.",
}


async def _profile(session_factory, client_id) -> BrandProfile | None:
    async with session_factory() as s:
        return (
            await s.execute(select(BrandProfile).where(BrandProfile.client_id == client_id))
        ).scalar_one_or_none()


async def _generations_used(session_factory, org_id) -> int:
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        return int(sub.generations_used or 0)


async def _seed_full_profile(session_factory, org_id, client_id) -> None:
    """A profile carrying everything the intake must NOT touch."""
    await _persist(
        session_factory,
        BrandProfile(
            client_id=client_id,
            org_id=org_id,
            voice_description="Existing voice",
            tone_attributes={"formality": 0.2, "register": "Friendly & casual"},
            vocabulary_include=["keep-me"],
            vocabulary_exclude=["never-me"],
            example_posts=[{"body": "An old example"}],
            style_rules=["No ALL CAPS"],
            emoji_policy="none",
            competitor_differentiation="old diff",
            target_audience="old audience",
        ),
    )
    async with session_factory() as s:
        client = (await s.execute(select(Client).where(Client.id == client_id))).scalar_one()
        client.settings = {"campaign_focus": {"description": "Early testers"}}  # type: ignore[assignment]
        await s.commit()


# ---------------------------------------------------------------------------
# Pure logic — ports of Cadence's updateProfileAnswers / brandVoiceLine tests
# ---------------------------------------------------------------------------
def test_apply_intake_merges_tone_and_keeps_unspecified_answers():
    bp = BrandProfile(
        tone_attributes={"formality": 0.3, "register": "Calm & authoritative"},
        target_audience="old audience",
        competitor_differentiation="old diff",
    )
    apply_intake(bp, audience="new audience", differentiator=None, tone="Blunt & technical")
    assert bp.target_audience == "new audience"
    assert bp.competitor_differentiation == "old diff"  # preserved, not wiped
    assert bp.tone_attributes == {"formality": 0.3, "register": "Blunt & technical"}


def test_north_star_replaces_only_its_own_entry():
    posts = [{"body": "keep"}, {"kind": NORTH_STAR_KIND, "text": "old"}]
    updated = with_north_star(posts, "new")
    assert north_star(updated) == "new"
    assert {"body": "keep"} in updated
    assert north_star(with_north_star(updated, "  ")) == ""
    assert {"body": "keep"} in with_north_star(updated, "")


def test_brand_prompt_block_reads_register_and_differentiator():
    block = brand_prompt_block(
        {
            "brand_name": "A",
            "tone_attributes": {"register": "Bold & punchy"},
            "competitor_differentiation": "48-hour delivery",
        }
    )
    assert "Tone register: Bold & punchy" in block
    assert "Differentiator: 48-hour delivery" in block


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
async def test_approve_creates_profile_and_sets_website(client, orgs, session_factory):
    resp = await client.put(
        f"{API}/setup/{orgs.client_a}/profile", json=INTAKE, headers=orgs.headers_a
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["approved"] is True
    assert body["answers"] == {
        "audience": INTAKE["audience"],
        "differentiator": INTAKE["differentiator"],
        "tone": "Bold & punchy",
    }
    assert body["website_url"] == "brand-a.example"
    assert body["brand_voice"] is None

    got = await client.get(f"{API}/setup/{orgs.client_a}/profile", headers=orgs.headers_a)
    assert got.json()["answers"]["tone"] == "Bold & punchy"


async def test_approve_never_wipes_unrelated_fields(client, orgs, session_factory):
    """Cadence's shipped-three-times bug: an answers edit destroyed the voice guide and campaign."""
    await _seed_full_profile(session_factory, orgs.org_a, orgs.client_a)

    resp = await client.put(
        f"{API}/setup/{orgs.client_a}/profile", json=INTAKE, headers=orgs.headers_a
    )
    assert resp.status_code == 200, resp.text

    bp = await _profile(session_factory, orgs.client_a)
    assert bp is not None
    assert bp.target_audience == INTAKE["audience"]
    assert bp.voice_description == "Existing voice"
    assert bp.vocabulary_include == ["keep-me"]
    assert bp.vocabulary_exclude == ["never-me"]
    assert bp.example_posts == [{"body": "An old example"}]
    assert bp.style_rules == ["No ALL CAPS"]
    assert bp.emoji_policy == "none"
    assert bp.tone_attributes == {"formality": 0.2, "register": "Bold & punchy"}
    assert resp.json()["campaign_focus"] == "Early testers"


async def test_approve_rejects_unknown_tone(client, orgs):
    resp = await client.put(
        f"{API}/setup/{orgs.client_a}/profile",
        json={**INTAKE, "tone": "Whatever the AI thinks"},
        headers=orgs.headers_a,
    )
    assert resp.status_code == 422


async def test_profile_endpoints_reject_other_orgs_client(client, orgs, session_factory):
    got = await client.get(f"{API}/setup/{orgs.client_b}/profile", headers=orgs.headers_a)
    assert got.status_code == 404

    put = await client.put(
        f"{API}/setup/{orgs.client_b}/profile", json=INTAKE, headers=orgs.headers_a
    )
    assert put.status_code == 404
    assert await _profile(session_factory, orgs.client_b) is None


# ---------------------------------------------------------------------------
# Push-back coaching
# ---------------------------------------------------------------------------
async def test_evaluate_answer_returns_coaching_without_charging(
    client, orgs, session_factory, stub_llm
):
    stub_llm({"isThin": True, "coachingNote": "Name who, exactly."})
    resp = await client.post(
        f"{API}/setup/{orgs.client_a}/profile/evaluate-answer",
        json={"question_id": "audience", "answer": "everyone"},
        headers=orgs.headers_a,
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "available": True,
        "is_thin": True,
        "coaching_note": "Name who, exactly.",
    }
    assert await _generations_used(session_factory, orgs.org_a) == 0


async def test_evaluate_answer_fails_open(client, orgs, stub_llm):
    stub_llm(fail=True)
    resp = await client.post(
        f"{API}/setup/{orgs.client_a}/profile/evaluate-answer",
        json={"question_id": "differentiator", "answer": "better UX"},
        headers=orgs.headers_a,
    )
    assert resp.status_code == 200
    assert resp.json()["available"] is False
    assert resp.json()["is_thin"] is False


async def test_evaluate_answer_rejects_tone_and_other_orgs_client(client, orgs, stub_llm):
    stub = stub_llm({"isThin": False, "coachingNote": ""})
    tone = await client.post(
        f"{API}/setup/{orgs.client_a}/profile/evaluate-answer",
        json={"question_id": "tone", "answer": "Bold & punchy"},
        headers=orgs.headers_a,
    )
    assert tone.status_code == 422
    other = await client.post(
        f"{API}/setup/{orgs.client_b}/profile/evaluate-answer",
        json={"question_id": "audience", "answer": "devs"},
        headers=orgs.headers_a,
    )
    assert other.status_code == 404
    assert stub.calls == []


# ---------------------------------------------------------------------------
# Brand Voice
# ---------------------------------------------------------------------------
async def test_brand_voice_requires_an_approved_profile(client, orgs, stub_llm):
    stub = stub_llm(VOICE)
    resp = await client.post(
        f"{API}/setup/{orgs.client_a}/brand-voice/generate", headers=orgs.headers_a
    )
    assert resp.status_code == 409
    assert stub.calls == []


async def test_brand_voice_draft_charges_once_and_saves_nothing(
    client, orgs, session_factory, stub_llm
):
    await _seed_full_profile(session_factory, orgs.org_a, orgs.client_a)
    stub_llm(VOICE)
    resp = await client.post(
        f"{API}/setup/{orgs.client_a}/brand-voice/generate", headers=orgs.headers_a
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "voice_description": "Short, warm sentences.",
        "vocabulary_include": ["fresh", "roasted today"],
        "vocabulary_exclude": ["synergy"],
        "example_sentence": "Roasted Monday, in your cup Wednesday.",
    }
    assert await _generations_used(session_factory, orgs.org_a) == 1
    bp = await _profile(session_factory, orgs.client_a)
    assert bp is not None and bp.voice_description == "Existing voice"  # draft is not saved


async def test_brand_voice_malformed_is_502_and_free(client, orgs, session_factory, stub_llm):
    await _seed_full_profile(session_factory, orgs.org_a, orgs.client_a)
    stub_llm({"voiceDescription": "only this"})
    resp = await client.post(
        f"{API}/setup/{orgs.client_a}/brand-voice/generate", headers=orgs.headers_a
    )
    assert resp.status_code == 502
    assert "no quota was used" in resp.json()["detail"]
    assert await _generations_used(session_factory, orgs.org_a) == 0


async def test_brand_voice_quota_exhausted(client, session_factory, stub_llm):
    org = await create_org(session_factory, "Broke Org")
    await create_subscription(session_factory, org, generations_used=5, generations_limit=5)
    client_id = await create_client_row(session_factory, org, "Brand")
    await _seed_full_profile(session_factory, org, client_id)
    stub = stub_llm(VOICE)
    resp = await client.post(
        f"{API}/setup/{client_id}/brand-voice/generate", headers=auth_header_for(org)
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["code"] == "generation_quota_exceeded"
    assert stub.calls == []


async def test_brand_voice_approve_writes_voice_fields_only(client, orgs, session_factory):
    await _seed_full_profile(session_factory, orgs.org_a, orgs.client_a)
    resp = await client.put(
        f"{API}/setup/{orgs.client_a}/brand-voice",
        json={
            "voice_description": "Approved voice",
            "vocabulary_include": ["fresh", " fresh ", ""],
            "vocabulary_exclude": ["synergy"],
            "example_sentence": "North star.",
        },
        headers=orgs.headers_a,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["brand_voice"]["example_sentence"] == "North star."

    bp = await _profile(session_factory, orgs.client_a)
    assert bp is not None
    assert bp.voice_description == "Approved voice"
    assert bp.vocabulary_include == ["fresh"]
    assert bp.vocabulary_exclude == ["synergy"]
    assert {"body": "An old example"} in bp.example_posts
    assert north_star(bp.example_posts) == "North star."
    # Intake answers and everything else untouched.
    assert bp.target_audience == "old audience"
    assert bp.competitor_differentiation == "old diff"
    assert bp.style_rules == ["No ALL CAPS"]
    assert bp.tone_attributes == {"formality": 0.2, "register": "Friendly & casual"}


async def test_brand_voice_endpoints_reject_other_orgs_client(
    client, orgs, session_factory, stub_llm
):
    await _seed_full_profile(session_factory, orgs.org_b, orgs.client_b)
    stub = stub_llm(VOICE)
    gen = await client.post(
        f"{API}/setup/{orgs.client_b}/brand-voice/generate", headers=orgs.headers_a
    )
    assert gen.status_code == 404
    put = await client.put(
        f"{API}/setup/{orgs.client_b}/brand-voice",
        json={"voice_description": "hijacked"},
        headers=orgs.headers_a,
    )
    assert put.status_code == 404
    bp = await _profile(session_factory, orgs.client_b)
    assert bp is not None and bp.voice_description == "Existing voice"
    assert stub.calls == []


# ---------------------------------------------------------------------------
# Strategy Lens Panel
# ---------------------------------------------------------------------------
async def test_strategy_lens_saves_asset_and_charges(client, orgs, session_factory, stub_llm):
    await _seed_full_profile(session_factory, orgs.org_a, orgs.client_a)
    stub_llm(LENS)
    resp = await client.post(f"{API}/setup/{orgs.client_a}/strategy-lens", headers=orgs.headers_a)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "strategy_lens"
    assert len(body["payload"]["lenses"]) == 4
    assert body["payload"]["synthesis"] == "Name the 48-hour promise."
    assert await _generations_used(session_factory, orgs.org_a) == 1

    listed = await client.get(
        f"{API}/assets",
        params={"client_id": str(orgs.client_a), "kind": "strategy_lens"},
        headers=orgs.headers_a,
    )
    assert listed.json()["total"] == 1


async def test_strategy_lens_incomplete_is_502_and_saves_nothing(
    client, orgs, session_factory, stub_llm
):
    await _seed_full_profile(session_factory, orgs.org_a, orgs.client_a)
    stub_llm({**LENS, "lenses": LENS["lenses"][:3]})
    resp = await client.post(f"{API}/setup/{orgs.client_a}/strategy-lens", headers=orgs.headers_a)
    assert resp.status_code == 502
    assert await _generations_used(session_factory, orgs.org_a) == 0
    async with session_factory() as s:
        assert (await s.execute(select(CreativeAsset))).scalars().all() == []


async def test_strategy_lens_rejects_other_orgs_client(client, orgs, session_factory, stub_llm):
    await _seed_full_profile(session_factory, orgs.org_b, orgs.client_b)
    stub = stub_llm(LENS)
    resp = await client.post(f"{API}/setup/{orgs.client_b}/strategy-lens", headers=orgs.headers_a)
    assert resp.status_code == 404
    assert stub.calls == []
    async with session_factory() as s:
        assert (await s.execute(select(CreativeAsset))).scalars().all() == []


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
async def test_accounts_lists_only_this_orgs_connected_rows(client, orgs, session_factory):
    mine = await create_platform_account(
        session_factory, orgs.org_a, orgs.client_a, platform="linkedin", account_handle="mine"
    )
    await create_platform_account(
        session_factory, orgs.org_a, orgs.client_a, platform="twitter", status="disconnected"
    )
    # The pre-T1.7 attack shape: another org's row carrying our client id.
    await create_platform_account(
        session_factory, orgs.org_b, orgs.client_a, platform="facebook", account_handle="theirs"
    )
    resp = await client.get(f"{API}/setup/{orgs.client_a}/accounts", headers=orgs.headers_a)
    assert resp.status_code == 200
    body = resp.json()
    assert [a["id"] for a in body["accounts"]] == [str(mine)]
    assert set(body["oauth"]) == {"twitter", "linkedin", "facebook"}
    assert "w_member_social" in body["oauth"]["linkedin"]["scopes"]


async def test_accounts_rejects_other_orgs_client(client, orgs):
    resp = await client.get(f"{API}/setup/{orgs.client_b}/accounts", headers=orgs.headers_a)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# OAuth: client-scoped, signed state, PKCE
# ---------------------------------------------------------------------------
@pytest.fixture
def oauth_configured(monkeypatch):
    from agency.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "twitter_client_id", "tw-id", raising=False)
    monkeypatch.setattr(settings, "linkedin_client_id", "li-id", raising=False)


async def test_authorize_rejects_other_orgs_client(client, orgs, oauth_configured):
    resp = await client.get(
        f"{API}/oauth/linkedin/authorize",
        params={"client_id": str(orgs.client_b)},
        headers=orgs.headers_a,
    )
    assert resp.status_code == 404


async def test_authorize_twitter_requires_pkce(client, orgs, oauth_configured):
    resp = await client.get(
        f"{API}/oauth/twitter/authorize",
        params={"client_id": str(orgs.client_a)},
        headers=orgs.headers_a,
    )
    assert resp.status_code == 400
    ok = await client.get(
        f"{API}/oauth/twitter/authorize",
        params={"client_id": str(orgs.client_a), "code_challenge": "abc123"},
        headers=orgs.headers_a,
    )
    assert ok.status_code == 200
    query = parse_qs(urlparse(ok.json()["authorize_url"]).query)
    assert query["code_challenge"] == ["abc123"]
    assert query["code_challenge_method"] == ["S256"]
    # The signed state names *our* client, not the OAuth app's client id.
    assert query["client_id"] == ["tw-id"]
    assert verify_state(query["state"][0], org_id=orgs.org_a, platform="twitter") == orgs.client_a


async def test_callback_rejects_state_for_another_client_or_org(
    client, orgs, session_factory, oauth_configured
):
    other_client = await create_client_row(session_factory, orgs.org_a, "Brand A2")
    auth = await client.get(
        f"{API}/oauth/linkedin/authorize",
        params={"client_id": str(orgs.client_a)},
        headers=orgs.headers_a,
    )
    state = parse_qs(urlparse(auth.json()["authorize_url"]).query)["state"][0]

    swapped = await client.post(
        f"{API}/oauth/linkedin/callback",
        json={"code": "abc", "client_id": str(other_client), "state": state},
        headers=orgs.headers_a,
    )
    assert swapped.status_code == 400

    # Org B replaying org A's state for its own client.
    replayed = await client.post(
        f"{API}/oauth/linkedin/callback",
        json={"code": "abc", "client_id": str(orgs.client_b), "state": state},
        headers=orgs.headers_b,
    )
    assert replayed.status_code == 400

    forged = await client.post(
        f"{API}/oauth/linkedin/callback",
        json={"code": "abc", "client_id": str(orgs.client_a), "state": state + "x"},
        headers=orgs.headers_a,
    )
    assert forged.status_code == 400


async def test_callback_twitter_requires_verifier(client, orgs):
    resp = await client.post(
        f"{API}/oauth/twitter/callback",
        json={"code": "abc", "client_id": str(orgs.client_a)},
        headers=orgs.headers_a,
    )
    assert resp.status_code == 400


def test_oauth_state_key_is_not_the_login_secret():
    """A state signed with the bare JWT secret (i.e. shaped like a login token) must not verify."""
    import time
    from uuid import uuid4

    import pytest
    from jose import JWTError, jwt

    from agency.config import get_settings
    from agency.services.oauth_state import InvalidOAuthStateError, sign_state, verify_state

    org = uuid4()
    now = int(time.time())
    forged = jwt.encode(
        {"typ": "oauth_state", "org": str(org), "plt": "twitter", "iat": now, "exp": now + 60},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(InvalidOAuthStateError):
        verify_state(forged, org_id=org, platform="twitter")
    # And a real state does not decode with the login secret.
    real = sign_state(org_id=org, client_id=None, platform="twitter")
    with pytest.raises(JWTError):
        jwt.decode(real, get_settings().jwt_secret, algorithms=["HS256"])
