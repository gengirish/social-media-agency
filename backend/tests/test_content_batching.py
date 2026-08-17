"""The repurpose and variants endpoints must batch, not loop.

Both endpoints used to call the model once per output item. That cost N times
as much for no gain, and in the variants case actively hurt quality: independent
calls cannot see each other, so they converge on near-duplicates and defeat the
A/B test they exist to serve.

These tests pin the batching itself — a regression to a per-item loop is a
silent cost multiplier that nothing else in the suite would catch.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agency.models.tables import ContentPiece
from tests.conftest import (
    auth_header_for,
    create_client_row,
    create_content_row,
    create_org,
)


class RecordingLLM:
    """Stands in for the chat model and counts how often it is invoked."""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    async def ainvoke(self, _prompt: Any) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(content=self.reply)


@pytest.fixture
def patch_lite(monkeypatch):
    """Swap the lite tier for a recording stub; return the stub."""

    def _install(reply: str) -> RecordingLLM:
        stub = RecordingLLM(reply)
        monkeypatch.setattr(
            "agency.services.llm_provider.get_lite_llm",
            lambda *a, **k: stub,
        )
        return stub

    return _install


async def _seed(session_factory: async_sessionmaker[AsyncSession]):
    org_id = await create_org(session_factory)
    client_id = await create_client_row(session_factory, org_id)
    content_id = await create_content_row(
        session_factory, org_id, client_id, platform="linkedin"
    )
    return org_id, content_id


async def _drafts_for(
    session_factory: async_sessionmaker[AsyncSession], org_id
) -> list[ContentPiece]:
    async with session_factory() as s:
        rows = await s.execute(
            select(ContentPiece).where(ContentPiece.org_id == org_id)
        )
        return list(rows.scalars().all())


async def test_repurpose_uses_one_call_for_many_platforms(
    client, session_factory, patch_lite
):
    org_id, content_id = await _seed(session_factory)
    stub = patch_lite(
        '[{"platform":"twitter","title":"T","body":"tw body","hashtags":["a"]},'
        '{"platform":"facebook","title":"F","body":"fb body","hashtags":[]},'
        '{"platform":"tiktok","title":"K","body":"tt body","hashtags":[]}]'
    )

    resp = await client.post(
        f"/api/v1/content/{content_id}/repurpose",
        json={"target_platforms": ["twitter", "facebook", "tiktok"]},
        headers=auth_header_for(org_id),
    )

    assert resp.status_code == 200, resp.text
    assert stub.calls == 1, "three platforms must cost one call, not three"
    assert sorted(resp.json()["platforms"]) == ["facebook", "tiktok", "twitter"]


async def test_repurpose_skips_platforms_the_model_omitted(
    client, session_factory, patch_lite
):
    """A missing platform is reported, never written as an empty draft."""
    org_id, content_id = await _seed(session_factory)
    patch_lite('[{"platform":"twitter","title":"T","body":"tw body","hashtags":[]}]')

    resp = await client.post(
        f"/api/v1/content/{content_id}/repurpose",
        json={"target_platforms": ["twitter", "facebook"]},
        headers=auth_header_for(org_id),
    )

    body = resp.json()
    assert body["platforms"] == ["twitter"]
    assert body["skipped"] == ["facebook"]
    bodies = [p.body for p in await _drafts_for(session_factory, org_id)]
    assert "" not in bodies, "an omitted platform must not become a blank draft"


async def test_repurpose_ignores_the_source_platform(
    client, session_factory, patch_lite
):
    org_id, content_id = await _seed(session_factory)  # source is linkedin
    stub = patch_lite("[]")

    resp = await client.post(
        f"/api/v1/content/{content_id}/repurpose",
        json={"target_platforms": ["linkedin"]},
        headers=auth_header_for(org_id),
    )

    assert resp.json()["count"] == 0
    assert stub.calls == 0, "nothing to repurpose means no model call at all"


async def test_variants_use_one_call_for_many_variants(
    client, session_factory, patch_lite
):
    org_id, content_id = await _seed(session_factory)
    stub = patch_lite(
        '[{"label":"B","title":"b","body":"body b","hashtags":[]},'
        '{"label":"C","title":"c","body":"body c","hashtags":[]},'
        '{"label":"D","title":"d","body":"body d","hashtags":[]}]'
    )

    resp = await client.post(
        f"/api/v1/content/{content_id}/variants",
        json={"count": 3},
        headers=auth_header_for(org_id),
    )

    assert resp.status_code == 200, resp.text
    assert stub.calls == 1, "three variants must cost one call, not three"
    assert resp.json()["variants"] == ["B", "C", "D"]


async def test_variants_report_labels_the_model_dropped(
    client, session_factory, patch_lite
):
    org_id, content_id = await _seed(session_factory)
    patch_lite('[{"label":"B","title":"b","body":"body b","hashtags":[]}]')

    resp = await client.post(
        f"/api/v1/content/{content_id}/variants",
        json={"count": 3},
        headers=auth_header_for(org_id),
    )

    body = resp.json()
    assert body["variants"] == ["B"]
    assert body["missing"] == ["C", "D"]
