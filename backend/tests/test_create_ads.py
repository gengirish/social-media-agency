"""Create › Ads endpoints — generate / spec, quota, fail-open moderation, tenancy.

The LLM tiers are replaced by stubs; SQL, tenancy filters and quota arithmetic
run for real against the SQLite test database. Each tenancy test asserts on a
cross-tenant identifier so it fails if its ``org_id`` filter is removed.
"""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from agency.agents.ads import CREATIVE_BRIEF_DISCLOSURE
from agency.models.tables import CreativeAsset, Subscription
from agency.services.ad_guardrails import META_CTA_OPTIONS
from tests.conftest import (
    auth_header_for,
    create_client_row,
    create_org,
    create_subscription,
    create_user_row,
)

API = "/api/v1/create/ads"

GOOGLE_REPLY = {
    "headlines": ["Plan Your Week in Minutes", "A Faster Buffer Alternative"]
    + [f"Headline number {i}" for i in range(13)],
    "descriptions": ["Plan, build and launch without the busywork that slows teams."] * 4,
    "paths": ["plan", "week"],
    "sitelinks": [{"text": "Pricing", "desc1": "See every plan", "desc2": "No card needed"}],
    "callouts": ["Free trial"],
    "keyword_themes": [{"intent": "Competitor", "keywords": ["hootsuite alternative"], "note": ""}],
    "negative_keywords": ["free download"],
    "structure_note": "One ad group per theme.",
}

META_REPLY = {
    "primary_texts": ["Are you a broke founder drowning in support tickets?"],
    "headlines": ["Ship faster"],
    "descriptions": ["Plan it once"],
    "cta": "Get Yours Now",
    "cta_reason": "Direct",
    "creative_direction": "A calm desk at 9am.",
    "audience_angle": "Small teams",
    "special_ad_category_note": "Does not appear to apply.",
}


class StubLLM:
    def __init__(self, reply: str | Exception):
        self.reply = reply
        self.calls: list[Any] = []

    async def ainvoke(self, messages: Any) -> SimpleNamespace:
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(content=self.reply)


@pytest.fixture
def llms(monkeypatch):
    """Install stubs for the ad-copy tier (generation) and brain tier (moderation)."""

    def _install(gen: Any, moderation: Any = None):
        gen_stub = StubLLM(gen if isinstance(gen, (str, Exception)) else json.dumps(gen))
        mod_reply = moderation if moderation is not None else {"flagged": False, "issues": []}
        mod_stub = StubLLM(
            mod_reply if isinstance(mod_reply, (str, Exception)) else json.dumps(mod_reply)
        )
        monkeypatch.setattr("agency.services.llm_provider.get_ad_copy_llm", lambda: gen_stub)
        monkeypatch.setattr("agency.services.llm_provider.get_brain_llm", lambda: mod_stub)

        def _no_other(*_a, **_k):  # pragma: no cover - fails the test if reached
            raise AssertionError("Ads must use the ad_copy and brain tiers only")

        monkeypatch.setattr("agency.services.llm_provider.get_worker_llm", _no_other)
        monkeypatch.setattr("agency.services.llm_provider.get_lite_llm", _no_other)
        return SimpleNamespace(gen=gen_stub, mod=mod_stub)

    return _install


@pytest.fixture
async def orgs(session_factory):
    org_a = await create_org(session_factory, "Org A", slug="ads-a")
    org_b = await create_org(session_factory, "Org B", slug="ads-b")
    await create_subscription(session_factory, org_a, plan_tier="starter")
    await create_subscription(session_factory, org_b, plan_tier="starter")
    client_a = await create_client_row(session_factory, org_a, "Brand A")
    client_a2 = await create_client_row(session_factory, org_a, "Brand A2")
    client_b = await create_client_row(session_factory, org_b, "Brand B")
    user_a = await create_user_row(session_factory, org_a)
    user_b = await create_user_row(session_factory, org_b)
    return SimpleNamespace(
        org_a=org_a,
        org_b=org_b,
        client_a=client_a,
        client_a2=client_a2,
        client_b=client_b,
        headers_a=auth_header_for(org_a, user_id=user_a),
        headers_b=auth_header_for(org_b, user_id=user_b),
    )


async def _asset(session_factory, org_id, client_id, kind, payload):
    from agency.services.creative_assets import save_asset

    async with session_factory() as s:
        await save_asset(
            s, org_id=org_id, client_id=client_id, kind=kind, title=kind, payload=payload
        )
        await s.commit()


async def _used(session_factory, org_id) -> int:
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        return int(sub.generations_used or 0)


async def _ad_sets(session_factory, org_id=None) -> list[CreativeAsset]:
    async with session_factory() as s:
        q = select(CreativeAsset).where(CreativeAsset.kind == "ad_set")
        if org_id is not None:
            q = q.where(CreativeAsset.org_id == org_id)
        return list((await s.execute(q)).scalars())


async def _generate(client, orgs, network="google", client_id=None, headers=None):
    return await client.post(
        f"{API}/generate",
        json={"client_id": str(client_id or orgs.client_a), "network": network},
        headers=headers or orgs.headers_a,
    )


# --- happy paths --------------------------------------------------------------


async def test_google_generate_saves_ad_set_and_charges_once(client, orgs, session_factory, llms):
    await _asset(
        session_factory, orgs.org_a, orgs.client_a, "comparison_page", {"competitor_name": "Buffer"}
    )
    await _asset(
        session_factory,
        orgs.org_a,
        orgs.client_a,
        "niche_scan",
        {"competitor_names": ["Hootsuite"]},
    )
    stubs = llms(GOOGLE_REPLY)

    resp = await _generate(client, orgs)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["kind"] == "ad_set"
    assert data["title"] == "Google RSA · Plan Your Week in Minutes"
    p = data["payload"]
    assert p["network"] == "google"
    assert len(p["headlines"]) == 15
    # Competitor in copy is flagged; the one in keyword_themes is not (bidding is allowed).
    assert p["trademark_risks"] == ["buffer"]
    assert p["limit_warnings"] == []
    assert p["moderation"] == {"status": "ok", "flagged": False, "issues": []}
    assert "personal_attribute_risks" not in p
    # No invented performance numbers anywhere in what we store.
    assert not {"ctr", "cpc", "roas", "predicted_ctr"} & set(p)

    assert await _used(session_factory, orgs.org_a) == 1
    assert len(await _ad_sets(session_factory, orgs.org_a)) == 1
    assert len(stubs.gen.calls) == 1 and len(stubs.mod.calls) == 1
    # Moderation sees ad copy, not keyword themes.
    assert "hootsuite alternative" not in stubs.mod.calls[0]


async def test_meta_generate_runs_meta_guardrails(client, orgs, session_factory, llms):
    llms(META_REPLY)
    resp = await _generate(client, orgs, network="meta")
    assert resp.status_code == 200, resp.text
    p = resp.json()["payload"]
    assert p["network"] == "meta"
    assert p["personal_attribute_risks"][0]["term"] == "broke"
    assert any('CTA "Get Yours Now"' in w for w in p["limit_warnings"])
    assert p["creative_direction"].endswith(CREATIVE_BRIEF_DISCLOSURE)
    assert resp.json()["title"] == "Meta ads · Ship faster"


async def test_prompt_reads_brand_and_campaign_focus(client, orgs, session_factory, llms):
    from agency.models.tables import Client

    async with session_factory() as s:
        row = await s.get(Client, orgs.client_a)
        row.settings = {"campaign_focus": {"description": "early testers this month"}}
        await s.commit()
    stubs = llms(GOOGLE_REPLY)
    assert (await _generate(client, orgs)).status_code == 200
    prompt = stubs.gen.calls[0][1].content
    assert "Brand A" in prompt
    assert "early testers this month" in prompt


async def test_spec_lists_limits_and_seven_ctas(client, orgs):
    resp = await client.get(f"{API}/spec", headers=orgs.headers_a)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta_cta_options"] == list(META_CTA_OPTIONS)
    assert body["limits"]["google"]["headlines"]["max"] == 30
    assert body["limits"]["meta"]["headlines"]["preferred"] == 27


# --- moderation fails open ------------------------------------------------------


@pytest.mark.parametrize(
    "moderation",
    [RuntimeError("provider 503"), "not json at all", {"issues": ["no flagged key"]}],
)
async def test_moderation_failure_never_discards_generation(
    client, orgs, session_factory, llms, moderation
):
    llms(GOOGLE_REPLY, moderation=moderation)
    resp = await _generate(client, orgs)
    assert resp.status_code == 200, resp.text
    assert resp.json()["payload"]["moderation"] == {
        "status": "unavailable",
        "flagged": False,
        "issues": [],
    }
    assert await _used(session_factory, orgs.org_a) == 1
    assert len(await _ad_sets(session_factory, orgs.org_a)) == 1


async def test_moderation_flags_are_advisory(client, orgs, session_factory, llms):
    llms(GOOGLE_REPLY, moderation={"flagged": True, "issues": ["'#1' is unsupported"]})
    resp = await _generate(client, orgs)
    assert resp.status_code == 200
    assert resp.json()["payload"]["moderation"] == {
        "status": "ok",
        "flagged": True,
        "issues": ["'#1' is unsupported"],
    }
    assert len(await _ad_sets(session_factory, orgs.org_a)) == 1


# --- quota only on success ----------------------------------------------------


@pytest.mark.parametrize(
    "gen",
    [
        RuntimeError("provider 503"),
        "I'm sorry, I can't help with that.",
        {"headlines": ["Only headlines"], "descriptions": []},
    ],
)
async def test_failed_or_malformed_generation_is_502_and_free(
    client, orgs, session_factory, llms, gen
):
    llms(gen)
    resp = await _generate(client, orgs)
    assert resp.status_code == 502
    assert "no quota was used" in resp.json()["detail"]
    assert await _used(session_factory, orgs.org_a) == 0
    assert await _ad_sets(session_factory) == []


async def test_quota_exhausted_is_402_without_calling_the_model(client, session_factory, llms):
    org_id = await create_org(session_factory)
    await create_subscription(session_factory, org_id, generations_used=10, generations_limit=10)
    client_id = await create_client_row(session_factory, org_id)
    stubs = llms(GOOGLE_REPLY)
    resp = await client.post(
        f"{API}/generate",
        json={"client_id": str(client_id), "network": "google"},
        headers=auth_header_for(org_id),
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["code"] == "generation_quota_exceeded"
    assert stubs.gen.calls == []


async def test_unknown_network_is_422(client, orgs, llms):
    llms(GOOGLE_REPLY)
    resp = await _generate(client, orgs, network="tiktok")
    assert resp.status_code == 422


# --- tenancy ------------------------------------------------------------------


async def test_generate_rejects_other_orgs_client(client, orgs, session_factory, llms):
    stubs = llms(GOOGLE_REPLY)
    resp = await _generate(client, orgs, client_id=orgs.client_b)
    assert resp.status_code == 404
    assert stubs.gen.calls == []
    assert await _ad_sets(session_factory) == []
    assert await _used(session_factory, orgs.org_a) == 0
    assert await _used(session_factory, orgs.org_b) == 0


async def test_competitor_names_come_only_from_this_org_and_client(
    client, orgs, session_factory, llms
):
    # A row planted under another org but pointing at our client id, and a row
    # on a sibling client in our own org: neither may feed the trademark check.
    await _asset(
        session_factory, orgs.org_b, orgs.client_a, "comparison_page", {"competitor_name": "Buffer"}
    )
    await _asset(
        session_factory,
        orgs.org_a,
        orgs.client_a2,
        "comparison_page",
        {"competitor_name": "Buffer"},
    )
    llms(GOOGLE_REPLY)
    resp = await _generate(client, orgs)
    assert resp.status_code == 200, resp.text
    assert resp.json()["payload"]["trademark_risks"] == []


async def test_saved_ad_set_is_invisible_to_other_org(client, orgs, llms):
    llms(GOOGLE_REPLY)
    asset_id = (await _generate(client, orgs)).json()["id"]
    resp = await client.get(f"/api/v1/assets/{asset_id}", headers=orgs.headers_b)
    assert resp.status_code == 404
    listed = await client.get(
        "/api/v1/assets",
        params={"client_id": str(orgs.client_a), "kind": "ad_set"},
        headers=orgs.headers_a,
    )
    assert [a["id"] for a in listed.json()["items"]] == [asset_id]
