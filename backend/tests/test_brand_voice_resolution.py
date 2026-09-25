"""CF-08 — one answer to "what is this client's voice?".

Three stores can hold a voice and each screen read a different one, so the same
client showed "Friendly & casual" on Setup › Profile, "Not set" in the Queue
sidebar, "Not configured" on its detail page and nothing in Settings.
"""

from uuid import UUID

import pytest
from sqlalchemy import select

from agency.models.tables import BrandProfile, Client
from agency.services.brand_context import resolve_voice
from tests.conftest import (
    auth_header_for,
    create_client_row,
    create_org,
    create_user_row,
)

API = "/api/v1"
GUIDE = "Plain, technical, no hype. Short sentences."


class TestResolveVoice:
    def test_a_written_guide_wins(self):
        # Someone composed it; a four-option preset must not override it.
        voice, source = resolve_voice(
            GUIDE, {"register": "Bold & punchy"}, {"voice_register": "Calm & authoritative"}
        )
        assert voice == GUIDE
        assert source == "guide"

    def test_the_settings_register_is_next(self):
        voice, source = resolve_voice(
            "", {"register": "Bold & punchy"}, {"voice_register": "Friendly & casual"}
        )
        assert voice == "Friendly & casual"
        assert source == "register"

    def test_the_legacy_tone_register_is_the_last_resort(self):
        voice, source = resolve_voice("", {"register": "Bold & punchy"}, {})
        assert voice == "Bold & punchy"
        assert source == "tone_register"

    def test_nothing_set_returns_no_voice_and_no_source(self):
        # Never a made-up default — the caller renders its own empty state.
        assert resolve_voice("", {}, {}) == ("", None)
        assert resolve_voice(None, None, None) == ("", None)

    def test_whitespace_is_not_a_voice(self):
        assert resolve_voice("   ", {"register": "  "}, {"voice_register": "   "}) == ("", None)

    def test_non_string_stores_are_ignored_rather_than_rendered(self):
        # tone_attributes is otherwise a dict of numbers, so a stray value here
        # would otherwise reach the UI as "5".
        assert resolve_voice("", {"register": 5}, {"voice_register": None}) == ("", None)


@pytest.fixture
async def tenant(session_factory):
    from types import SimpleNamespace

    org_id = await create_org(session_factory, "Voice Org")
    client_id = await create_client_row(session_factory, org_id, "Voice Brand")
    user_id = await create_user_row(session_factory, org_id)
    return SimpleNamespace(
        org_id=org_id,
        client_id=client_id,
        headers=auth_header_for(org_id, user_id=user_id),
    )


async def _set_profile(session_factory, tenant, **fields):
    async with session_factory() as db:
        bp = (
            await db.execute(
                select(BrandProfile).where(BrandProfile.client_id == tenant.client_id)
            )
        ).scalar_one_or_none()
        if bp is None:
            bp = BrandProfile(client_id=tenant.client_id, org_id=tenant.org_id)
            db.add(bp)
        for key, value in fields.items():
            setattr(bp, key, value)
        await db.commit()


async def test_brand_profile_endpoint_returns_the_resolved_voice(
    client, session_factory, tenant
):
    await _set_profile(session_factory, tenant, voice_description=GUIDE)

    resp = await client.get(
        f"{API}/clients/{tenant.client_id}/brand-profile", headers=tenant.headers
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["effective_voice"] == GUIDE
    assert body["voice_source"] == "guide"


async def test_the_register_surfaces_when_no_guide_is_written(
    client, session_factory, tenant
):
    """The case behind "Not set": a register was picked but no guide written."""
    await _set_profile(session_factory, tenant, voice_description="")
    async with session_factory() as db:
        row = await db.get(Client, tenant.client_id)
        row.settings = {"posting_prefs": {"voice_register": "Friendly & casual"}}
        await db.commit()

    resp = await client.get(
        f"{API}/clients/{tenant.client_id}/brand-profile", headers=tenant.headers
    )

    assert resp.json()["effective_voice"] == "Friendly & casual"
    assert resp.json()["voice_source"] == "register"


async def test_saving_the_register_mirrors_it_into_the_legacy_store(
    client, session_factory, tenant
):
    """Otherwise the two coarse stores drift and show different registers."""
    await _set_profile(session_factory, tenant, tone_attributes={"register": "Bold & punchy"})

    resp = await client.put(
        f"{API}/workspace/posting-prefs?client_id={tenant.client_id}",
        headers=tenant.headers,
        json={"voice_register": "Calm & authoritative"},
    )
    assert resp.status_code == 200, resp.text

    async with session_factory() as db:
        bp = (
            await db.execute(
                select(BrandProfile).where(BrandProfile.client_id == tenant.client_id)
            )
        ).scalar_one()
    assert bp.tone_attributes["register"] == "Calm & authoritative"


async def test_saving_the_register_never_overwrites_a_written_guide(
    client, session_factory, tenant
):
    """The guide is prose someone composed — a preset must not destroy it."""
    await _set_profile(session_factory, tenant, voice_description=GUIDE)

    await client.put(
        f"{API}/workspace/posting-prefs?client_id={tenant.client_id}",
        headers=tenant.headers,
        json={"voice_register": "Bold & punchy"},
    )

    async with session_factory() as db:
        bp = (
            await db.execute(
                select(BrandProfile).where(BrandProfile.client_id == tenant.client_id)
            )
        ).scalar_one()
    assert bp.voice_description == GUIDE

    resp = await client.get(
        f"{API}/clients/{tenant.client_id}/brand-profile", headers=tenant.headers
    )
    # And the guide still wins, so every screen keeps showing it.
    assert resp.json()["effective_voice"] == GUIDE


async def test_a_client_in_another_org_is_not_readable(client, session_factory, tenant):
    other_org = await create_org(session_factory, "Other Voice Org")
    other_client: UUID = await create_client_row(session_factory, other_org, "Other Brand")

    resp = await client.get(
        f"{API}/clients/{other_client}/brand-profile", headers=tenant.headers
    )
    assert resp.status_code == 404
