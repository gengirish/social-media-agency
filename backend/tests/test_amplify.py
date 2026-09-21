"""Amplify endpoints — preview / commit / packs, quota, and the Pending guarantee.

The LLM is replaced by a stub; everything else (SQL, tenancy filters, quota
arithmetic) runs for real against the SQLite test database.
"""

import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select

from agency.models.tables import (
    BrandProfile,
    ContentPiece,
    ProductEvent,
    RepurposePack,
    Subscription,
)
from agency.services.repurpose import MAX_ATOMS, REPURPOSE_ANGLES, plan_atoms
from tests.conftest import (
    _persist,
    auth_header_for,
    create_campaign_row,
    create_client_row,
    create_content_row,
    create_org,
    create_subscription,
    create_user_row,
)

API = "/api/v1/amplify"


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


# Deliberately unrelated wording per angle, so the duplicate check stays quiet
# unless a test sets it off on purpose.
BODIES = {
    "hook": "Most roasters guess. We weigh every single batch before it ships.",
    "how-to": "Grind finer than you think, then pour slowly in three stages.",
    "contrarian": "Dark roast is not stronger; caffeine drops as beans roast longer.",
    "story": "Maria's first shift ended with a burnt tray and a new rule.",
    "data-point": "Twelve kilos leave the drum each Friday morning.",
    "question": "Which origin should come back next month, Kenya or Peru?",
    "behind-the-scenes": "Cupping notes live on a whiteboard nobody may erase.",
    "listicle": "1. Water temp 2. Ratio 3. Freshness. Fix these first.",
}


def atoms_reply(platforms: list[str], n: int = MAX_ATOMS) -> str:
    """What a well-behaved model returns for the pack plan_atoms will request."""
    return json.dumps(
        {
            "atoms": [
                {
                    "platform": r["platform"],
                    "angle": r["angle"],
                    "title": f"{r['angle']} title",
                    "body": BODIES[r["angle"]],
                    "hashtags": ["coffee"],
                }
                for r in plan_atoms(platforms, n)
            ]
        }
    )


@pytest.fixture
def stub_llm(monkeypatch):
    """Install a stub for the worker tier; records the temperature requested."""
    seen: dict[str, Any] = {}

    def _install(reply: str | None = None, *, fail: bool = False):
        stub: Any = FailingLLM() if fail else StubLLM(reply or "")

        def _get_worker_llm(temperature: float = 0.7):
            seen["temperature"] = temperature
            return stub

        def _no_lite(*_a, **_k):  # pragma: no cover - fails the test if reached
            raise AssertionError("Amplify must not use the lite tier")

        monkeypatch.setattr("agency.agents.amplify.get_worker_llm", _get_worker_llm)
        monkeypatch.setattr("agency.services.llm_provider.get_lite_llm", _no_lite)
        stub.seen = seen
        return stub

    return _install


@pytest.fixture
async def org(session_factory):
    org_id = await create_org(session_factory, "Amplify Org")
    await create_subscription(session_factory, org_id, plan_tier="starter")
    user_id = await create_user_row(session_factory, org_id)
    client_id = await create_client_row(session_factory, org_id, "Sunrise Coffee")
    campaign_id = await create_campaign_row(session_factory, org_id, client_id, "Autumn")
    source_id = await create_content_row(session_factory, org_id, client_id, campaign_id)
    return SimpleNamespace(
        org_id=org_id,
        user_id=user_id,
        client_id=client_id,
        campaign_id=campaign_id,
        source_id=source_id,
        headers=auth_header_for(org_id, user_id=user_id),
    )


async def _content_rows(session_factory, org_id) -> list[ContentPiece]:
    async with session_factory() as s:
        rows = await s.execute(select(ContentPiece).where(ContentPiece.org_id == org_id))
        return list(rows.scalars().all())


async def _sub(session_factory, org_id) -> Subscription:
    async with session_factory() as s:
        return (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()


async def _preview(client, org, platforms=("twitter", "linkedin"), **extra):
    body = {
        "client_id": str(org.client_id),
        "source_content_id": str(org.source_id),
        "platforms": list(platforms),
        **extra,
    }
    return await client.post(f"{API}/preview", json=body, headers=org.headers)


# --- preview ------------------------------------------------------------------


async def test_preview_happy_path(client, org, session_factory, stub_llm):
    stub = stub_llm(atoms_reply(["twitter", "linkedin"]))
    before = await _content_rows(session_factory, org.org_id)

    resp = await _preview(client, org)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert len(data["atoms"]) == MAX_ATOMS
    assert [a["angle"] for a in data["atoms"]] == list(REPURPOSE_ANGLES)
    first = data["atoms"][0]
    assert set(first) >= {"platform", "angle", "title", "body", "hashtags", "duplicate_warning"}
    assert first["char_limit"] == 280 and first["char_count"] <= 280
    assert stub.seen["temperature"] == 0.8
    assert len(stub.calls) == 1

    # Nothing written to content_piece at preview.
    assert len(await _content_rows(session_factory, org.org_id)) == len(before)

    # One pack row, one generation charged.
    async with session_factory() as s:
        pack = await s.get(RepurposePack, UUID(data["pack_id"]))
        assert pack is not None
        assert pack.atom_count == MAX_ATOMS and pack.committed_count == 0
        assert pack.source_content_id == org.source_id
        assert pack.created_by == org.user_id
        events = (await s.execute(select(ProductEvent.name))).scalars().all()
        assert "amplify_pack_generated" in events
    assert (await _sub(session_factory, org.org_id)).generations_used == 1


async def test_preview_prompt_reads_brand_profile_and_campaign(
    client, org, session_factory, stub_llm
):
    await _persist(
        session_factory,
        BrandProfile(
            client_id=org.client_id,
            org_id=org.org_id,
            voice_description="warm and neighbourly",
            vocabulary_exclude=["synergy"],
            example_posts=[{"body": "Fresh roast Friday is back."}],
            tone_attributes={},
            vocabulary_include=[],
            style_rules=[],
        ),
    )
    stub = stub_llm(atoms_reply(["twitter"], 2))
    resp = await _preview(client, org, platforms=["twitter"], max_atoms=2)
    assert resp.status_code == 200, resp.text

    prompt = stub.calls[0][1].content
    assert "warm and neighbourly" in prompt
    assert "synergy" in prompt
    assert "Fresh roast Friday is back." in prompt
    assert "Campaign: Autumn" in prompt


async def test_preview_pasted_text_and_duplicate_warning(client, org, session_factory, stub_llm):
    # An existing post that the model's "hook" atom will reword.
    body = "Most roasters just guess; we weigh every single batch before it ships!"
    async with session_factory() as s:
        s.add(
            ContentPiece(
                org_id=org.org_id,
                client_id=org.client_id,
                platform="twitter",
                body=body,
                status="published",
            )
        )
        await s.commit()

    stub_llm(atoms_reply(["twitter"], 3))
    resp = await client.post(
        f"{API}/preview",
        json={
            "client_id": str(org.client_id),
            "source_text": "Pasted launch notes.",
            "platforms": ["twitter"],
            "max_atoms": 3,
        },
        headers=org.headers,
    )
    assert resp.status_code == 200, resp.text
    atoms = resp.json()["atoms"]
    assert atoms[0]["duplicate_warning"] is True
    assert atoms[1]["duplicate_warning"] is False


async def test_preview_drops_off_plan_and_over_limit_atoms(client, org, stub_llm):
    reply = json.loads(atoms_reply(["twitter"], 3))
    reply["atoms"][1]["body"] = "z" * 400  # over the twitter limit
    reply["atoms"].append(dict(reply["atoms"][0]))  # repeated angle
    stub_llm(json.dumps(reply))

    resp = await _preview(client, org, platforms=["twitter"], max_atoms=3)
    assert resp.status_code == 200, resp.text
    assert [a["angle"] for a in resp.json()["atoms"]] == ["hook", "contrarian"]
    assert resp.json()["dropped"] == 2


async def test_preview_quota_exhausted_402(client, session_factory, stub_llm):
    org_id = await create_org(session_factory)
    await create_subscription(session_factory, org_id, generations_used=10, generations_limit=10)
    client_id = await create_client_row(session_factory, org_id)
    stub = stub_llm(atoms_reply(["twitter"]))

    resp = await client.post(
        f"{API}/preview",
        json={"client_id": str(client_id), "source_text": "hi", "platforms": ["twitter"]},
        headers=auth_header_for(org_id),
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["code"] == "generation_quota_exceeded"
    assert stub.calls == []  # never reached the model
    assert (await _sub(session_factory, org_id)).generations_used == 10


async def test_preview_null_limit_falls_back_to_tier(client, session_factory, stub_llm):
    """A pre-migration row with NULL generations_limit is not treated as unlimited."""
    org_id = await create_org(session_factory)
    await create_subscription(session_factory, org_id, plan_tier="free", generations_used=10)
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        sub.generations_limit = None
        await s.commit()
    client_id = await create_client_row(session_factory, org_id)
    stub_llm(atoms_reply(["twitter"]))

    resp = await client.post(
        f"{API}/preview",
        json={"client_id": str(client_id), "source_text": "hi", "platforms": ["twitter"]},
        headers=auth_header_for(org_id),
    )
    assert resp.status_code == 402


async def test_preview_llm_failure_charges_nothing(client, org, session_factory, stub_llm):
    stub_llm(fail=True)
    resp = await _preview(client, org)
    assert resp.status_code == 502
    assert (await _sub(session_factory, org.org_id)).generations_used == 0
    async with session_factory() as s:
        assert (await s.execute(select(RepurposePack))).scalars().all() == []


async def test_preview_unusable_reply_charges_nothing(client, org, session_factory, stub_llm):
    stub_llm("I cannot help with that.")
    resp = await _preview(client, org)
    assert resp.status_code == 502
    assert (await _sub(session_factory, org.org_id)).generations_used == 0


async def test_preview_validation(client, org, stub_llm):
    stub_llm(atoms_reply(["twitter"]))
    both = await _preview(client, org, source_text="also text")
    assert both.status_code == 422
    bad_platform = await _preview(client, org, platforms=["myspace"])
    assert bad_platform.status_code == 422
    too_many = await _preview(client, org, max_atoms=9)
    assert too_many.status_code == 422


# --- commit -------------------------------------------------------------------


async def _generated_pack(client, org, stub_llm, platforms=("twitter", "linkedin")):
    stub_llm(atoms_reply(list(platforms)))
    resp = await _preview(client, org, platforms=platforms)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_commit_lands_every_atom_as_pending_draft(client, org, session_factory, stub_llm):
    """CRITICAL regression guard: Amplify never approves or schedules anything.

    A pack is eight posts at once, so a status bypass here is eight times worse
    than the single-post version. Even a request that tries to smuggle a status
    in must land as ``draft`` with no schedule.
    """
    pack = await _generated_pack(client, org, stub_llm)
    atoms = [
        {**a, "status": "approved", "scheduled_at": "2030-01-01T00:00:00Z"}
        for a in pack["atoms"]
    ]

    resp = await client.post(
        f"{API}/{pack['pack_id']}/commit", json={"atoms": atoms}, headers=org.headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == MAX_ATOMS

    created_ids = set(resp.json()["created"])
    rows = [r for r in await _content_rows(session_factory, org.org_id) if str(r.id) in created_ids]
    assert len(rows) == MAX_ATOMS
    for row in rows:
        assert row.status == "draft"
        assert row.scheduled_at is None
        assert row.published_at is None
        assert row.client_id == org.client_id
        assert row.campaign_id == org.campaign_id  # same campaign as the source
        assert row.metadata_["amplify_pack_id"] == pack["pack_id"]
        assert row.metadata_["source_id"] == str(org.source_id)
        assert row.metadata_["angle"] in REPURPOSE_ANGLES
    assert {r.metadata_["angle"] for r in rows} == set(REPURPOSE_ANGLES)

    async with session_factory() as s:
        saved = await s.get(RepurposePack, UUID(pack["pack_id"]))
        assert saved.committed_count == MAX_ATOMS


async def test_commit_subset_after_dropping(client, org, session_factory, stub_llm):
    pack = await _generated_pack(client, org, stub_llm)
    kept = pack["atoms"][:3]
    resp = await client.post(
        f"{API}/{pack['pack_id']}/commit", json={"atoms": kept}, headers=org.headers
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 3


async def test_commit_caps_at_eight(client, org, stub_llm):
    pack = await _generated_pack(client, org, stub_llm)
    nine = pack["atoms"] + [pack["atoms"][0]]
    resp = await client.post(
        f"{API}/{pack['pack_id']}/commit", json={"atoms": nine}, headers=org.headers
    )
    assert resp.status_code == 422


async def test_commit_rejects_invalid_atoms(client, org, session_factory, stub_llm):
    pack = await _generated_pack(client, org, stub_llm)
    before = len(await _content_rows(session_factory, org.org_id))
    bad = [dict(pack["atoms"][0]), dict(pack["atoms"][0])]  # duplicate angle
    resp = await client.post(
        f"{API}/{pack['pack_id']}/commit", json={"atoms": bad}, headers=org.headers
    )
    assert resp.status_code == 422
    assert len(await _content_rows(session_factory, org.org_id)) == before


async def test_commit_twice_conflicts(client, org, stub_llm):
    pack = await _generated_pack(client, org, stub_llm)
    url = f"{API}/{pack['pack_id']}/commit"
    first = await client.post(url, json={"atoms": pack["atoms"][:1]}, headers=org.headers)
    assert first.status_code == 200
    again = await client.post(url, json={"atoms": pack["atoms"][:1]}, headers=org.headers)
    assert again.status_code == 409


# --- packs --------------------------------------------------------------------


async def test_packs_list_newest_first_with_filter(client, org, session_factory, stub_llm):
    await _generated_pack(client, org, stub_llm)
    other_client = await create_client_row(session_factory, org.org_id, "Other")
    stub_llm(atoms_reply(["twitter"], 2))
    resp = await client.post(
        f"{API}/preview",
        json={
            "client_id": str(other_client),
            "source_text": "Pasted text\nsecond line",
            "platforms": ["twitter"],
            "max_atoms": 2,
        },
        headers=org.headers,
    )
    assert resp.status_code == 200

    all_packs = (await client.get(f"{API}/packs", headers=org.headers)).json()["items"]
    assert len(all_packs) == 2
    filtered = (
        await client.get(f"{API}/packs?client_id={org.client_id}", headers=org.headers)
    ).json()["items"]
    assert len(filtered) == 1
    assert filtered[0]["source_title"] == "Test piece"
    assert filtered[0]["client_name"] == "Sunrise Coffee"
    text_pack = next(p for p in all_packs if p["source_content_id"] is None)
    assert text_pack["source_excerpt"] == "Pasted text second line"


# --- billing wiring -----------------------------------------------------------


async def test_subscription_endpoint_reports_generations(client, org, session_factory, stub_llm):
    await _generated_pack(client, org, stub_llm)
    data = (await client.get("/api/v1/billing/subscription", headers=org.headers)).json()
    assert data["generations_used"] == 1
    assert data["generations_limit"] == 50  # starter


async def test_invoice_paid_resets_generations(db, session_factory):
    from agency.services.billing import billing

    org_id = await create_org(session_factory)
    await create_subscription(
        session_factory, org_id, generations_used=7, stripe_customer_id="cus_amp"
    )
    result = await billing.handle_webhook(
        db, {"type": "invoice.paid", "data": {"object": {"customer": "cus_amp"}}}
    )
    assert result["status"] == "usage_reset"
    assert (await _sub(session_factory, org_id)).generations_used == 0


def test_every_tier_has_a_generation_limit():
    from agency.services.billing import PLAN_CONFIG

    limits = [PLAN_CONFIG[t]["generations_limit"] for t in ("free", "starter", "growth", "agency")]
    assert limits == sorted(limits) and all(isinstance(v, int) and v > 0 for v in limits)
