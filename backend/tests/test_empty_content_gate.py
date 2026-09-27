"""CF-05 — an item with nothing in it cannot be approved.

Hiding the Approve button was not enough: the gate has to hold against a direct
call, because publishing here is real and an approved empty post is a post that
goes to a client's live account saying nothing.

Written the way ``test_approval_gate.py`` is: every refusal asserts the structured
error *and* that the row did not move, so deleting the gate fails the test.
"""

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select

from agency.models.tables import ContentPiece
from agency.services.content_approval import empty_content_reason
from tests.conftest import (
    auth_header_for,
    create_client_row,
    create_content_row,
    create_org,
    create_subscription,
    create_user_row,
)

API = "/api/v1"
CLEAN = '{"issues": []}'


class StubLLM:
    def __init__(self, reply: str = CLEAN):
        self.reply = reply
        self.prompts: list[Any] = []

    async def ainvoke(self, prompt: Any) -> SimpleNamespace:
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.reply)


@pytest.fixture
def brain(monkeypatch):
    def _install(reply: str = CLEAN) -> StubLLM:
        stub = StubLLM(reply)
        monkeypatch.setattr("agency.services.llm_provider.get_brain_llm", lambda *a, **k: stub)
        return stub

    return _install


@pytest.fixture
async def tenant(session_factory):
    org_id = await create_org(session_factory, "Empty Gate Org")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org_id, "Empty Gate Brand")
    user_id = await create_user_row(session_factory, org_id)
    return SimpleNamespace(
        org_id=org_id,
        client_id=client_id,
        user_id=user_id,
        headers=auth_header_for(org_id, user_id=user_id),
    )


async def _piece(session_factory, content_id: UUID) -> ContentPiece:
    async with session_factory() as db:
        return (
            await db.execute(select(ContentPiece).where(ContentPiece.id == content_id))
        ).scalar_one()


async def _new(session_factory, tenant, **kwargs):
    return await create_content_row(session_factory, tenant.org_id, tenant.client_id, **kwargs)


# ---------------------------------------------------------------------------
# empty_content_reason — the predicate the gate and the UI agree on
# ---------------------------------------------------------------------------
class TestEmptyContentReason:
    def _row(self, **kwargs):
        base = {"body": "Real copy", "metadata_": {}, "media_urls": []}
        base.update(kwargs)
        return SimpleNamespace(**base)

    def test_real_copy_is_not_empty(self):
        assert empty_content_reason(self._row()) is None

    @pytest.mark.parametrize("body", ["", "   ", "[]", "{}", '""'])
    def test_the_old_stringified_ad_bodies_count_as_empty(self, body):
        # "[]" is exactly what the pre-CF-03 pipeline wrote for a Meta or LinkedIn
        # ad. It passes any length check but says nothing.
        assert empty_content_reason(self._row(body=body)) == "This item has no content."

    def test_an_image_only_post_is_not_empty(self):
        assert empty_content_reason(self._row(body="", media_urls=["https://x/y.png"])) is None

    def test_a_variant_marked_failed_at_generation_reports_its_reason(self):
        row = self._row(
            body="",
            metadata_={"generation": {"status": "failed", "reason": "No usable copy."}},
        )
        assert empty_content_reason(row) == "No usable copy."

    def test_an_ad_with_no_populated_fields_is_empty(self):
        row = self._row(body="", metadata_={"ad": {"fields": {"headline": "", "primary_text": ""}}})
        assert empty_content_reason(row) is not None

    def test_an_ad_with_copy_is_not_empty_even_though_its_body_mirrors_it(self):
        # A structured ad carries its copy in `fields`; `body` is only a flattened
        # mirror, so judging an ad by its body would reject good variants.
        row = self._row(
            body="", metadata_={"ad": {"fields": {"primary_text": "Stop losing gigs."}}}
        )
        assert empty_content_reason(row) is None


# ---------------------------------------------------------------------------
# POST /content/{id}/approve
# ---------------------------------------------------------------------------
async def test_approve_refuses_an_empty_body(client, session_factory, tenant, brain):
    stub = brain()
    content_id = await _new(session_factory, tenant, body="")

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=tenant.headers)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "empty_content"
    # The gate runs before moderation — there is nothing to moderate.
    assert stub.prompts == []
    assert (await _piece(session_factory, content_id)).status == "draft"


async def test_approve_refuses_a_legacy_stringified_ad_body(
    client, session_factory, tenant, brain
):
    """The rows CF-03 left behind: drafts whose entire body is "[]"."""
    content_id = await _new(
        session_factory, tenant, body="[]", content_type="meta_ad", platform="meta"
    )

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=tenant.headers)

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "empty_content"
    assert (await _piece(session_factory, content_id)).status == "draft"


async def test_approve_refuses_a_variant_flagged_failed_at_generation(
    client, session_factory, tenant, brain
):
    content_id = await _new(
        session_factory,
        tenant,
        body="",
        content_type="google_ad",
        platform="google",
        metadata={
            "generation": {"status": "failed", "reason": "The ad copy agent returned nothing."}
        },
    )

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=tenant.headers)

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "empty_content"
    assert detail["message"] == "The ad copy agent returned nothing."
    assert (await _piece(session_factory, content_id)).status == "draft"


async def test_approve_still_allows_a_structured_ad_variant(
    client, session_factory, tenant, brain
):
    """The gate must not catch good ads — their copy lives in metadata, not body."""
    brain()
    content_id = await _new(
        session_factory,
        tenant,
        body="Primary text: Stop losing gigs.",
        content_type="meta_ad",
        platform="meta",
        metadata={"ad": {"fields": {"primary_text": "Stop losing gigs.", "headline": "Apply"}}},
    )

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=tenant.headers)

    assert resp.status_code == 200, resp.text
    assert (await _piece(session_factory, content_id)).status == "approved"
