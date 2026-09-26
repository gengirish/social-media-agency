"""CF-15 — a past Amplify pack can be opened.

A history row was not clickable, so "2 generated · 2 queued" across five
platforms was everything the user could learn: there was no way to see which
platforms actually produced a draft.

What is knowable is bounded by what is stored. Atoms live only in the preview
response — `commit` writes the kept ones to `content_piece` and the rest are
never persisted — so these tests pin the three states the endpoint reports and,
importantly, that it does not claim to know more than it does.
"""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from tests.conftest import (
    auth_header_for,
    create_campaign_row,
    create_client_row,
    create_content_row,
    create_org,
    create_subscription,
    create_user_row,
)
from tests.test_amplify import API, StubLLM, _preview, atoms_reply

PACKS = "/api/v1/amplify/packs"


@pytest.fixture
def stub_llm(monkeypatch):
    def _install(reply: str):
        stub: Any = StubLLM(reply)
        monkeypatch.setattr(
            "agency.agents.amplify.get_worker_llm", lambda temperature=0.7: stub
        )
        return stub

    return _install


@pytest.fixture
async def org(session_factory):
    org_id = await create_org(session_factory, "Pack Detail Org")
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


async def _pack_with(client, org, stub_llm, platforms, *, keep: int | None = None):
    """Generate a pack, commit `keep` of its atoms (all of them by default)."""
    stub_llm(atoms_reply(list(platforms)))
    preview = (await _preview(client, org, platforms=platforms)).json()
    atoms = preview["atoms"] if keep is None else preview["atoms"][:keep]
    if atoms:
        resp = await client.post(
            f"{API}/{preview['pack_id']}/commit", json={"atoms": atoms}, headers=org.headers
        )
        assert resp.status_code == 200, resp.text
    return preview["pack_id"]


async def test_a_pack_reports_its_queued_drafts(client, org, stub_llm):
    pack_id = await _pack_with(client, org, stub_llm, ("twitter", "linkedin"))

    resp = await client.get(f"{PACKS}/{pack_id}", headers=org.headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == pack_id
    assert body["posts"], "the committed drafts must be linked back to the pack"
    # Every post carries what the UI needs to describe it without a second call.
    for post in body["posts"]:
        assert post["platform"]
        assert post["status"] == "draft"  # Amplify never approves anything
        assert post["angle"]


async def test_every_selected_platform_appears_in_the_breakdown(client, org, stub_llm):
    """The reported bug: five platforms, and no way to see which produced what."""
    platforms = ("twitter", "linkedin", "facebook")
    pack_id = await _pack_with(client, org, stub_llm, platforms)

    body = (await client.get(f"{PACKS}/{pack_id}", headers=org.headers)).json()

    assert [row["platform"] for row in body["platform_breakdown"]] == list(platforms)
    assert all(row["status"] == "queued" for row in body["platform_breakdown"])


async def test_a_platform_whose_atom_was_dropped_is_not_reported_as_queued(
    client, org, stub_llm
):
    """Dropping at review must not read as "queued" for the platforms that lost out."""
    platforms = ("twitter", "linkedin", "facebook")
    pack_id = await _pack_with(client, org, stub_llm, platforms, keep=1)

    body = (await client.get(f"{PACKS}/{pack_id}", headers=org.headers)).json()

    queued = [r["platform"] for r in body["platform_breakdown"] if r["status"] == "queued"]
    assert len(queued) == 1
    assert body["dropped_count"] > 0
    assert len(body["unqueued_platforms"]) == len(platforms) - 1
    # Nothing is invented for the platforms with no draft.
    assert all(
        r["status"] != "queued"
        for r in body["platform_breakdown"]
        if r["platform"] not in queued
    )


async def test_a_pack_with_nothing_kept_reports_no_posts(client, org, stub_llm):
    pack_id = await _pack_with(client, org, stub_llm, ("twitter",), keep=0)

    body = (await client.get(f"{PACKS}/{pack_id}", headers=org.headers)).json()

    assert body["posts"] == []
    assert body["committed_count"] == 0
    assert all(r["status"] != "queued" for r in body["platform_breakdown"])


async def test_another_orgs_pack_is_not_readable(client, org, session_factory, stub_llm):
    """TENANCY: pack_id comes from the client and must be resolved against org_id."""
    pack_id = await _pack_with(client, org, stub_llm, ("twitter",))

    other_org = await create_org(session_factory, "Other Pack Org")
    other_user = await create_user_row(session_factory, other_org)
    other_headers = auth_header_for(other_org, user_id=other_user)

    resp = await client.get(f"{PACKS}/{pack_id}", headers=other_headers)
    assert resp.status_code == 404


async def test_an_unknown_pack_is_404(client, org):
    resp = await client.get(f"{PACKS}/{uuid4()}", headers=org.headers)
    assert resp.status_code == 404
