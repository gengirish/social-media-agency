"""The approval gate — product rule 3: moderation runs before approval, and schedule /
publish accept only approved content.

Publishing here is real (X, LinkedIn, Facebook post to live client accounts), so every
gate below is written to fail if the gate itself is deleted: each refusal test asserts
both the structured error *and* that the database row did not move (a 409 that still
changed the status would be worthless).

The brain-tier LLM is replaced by a recording stub; no test touches a real provider.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from structlog.testing import capture_logs

from agency.models.tables import BrandProfile, ContentPiece
from agency.services import moderation
from tests.conftest import (
    auth_header_for,
    create_client_row,
    create_content_row,
    create_org,
    create_subscription,
    create_user_row,
    create_white_label,
)

API = "/api/v1"
CLEAN = '{"issues": []}'
FLAGGED = (
    '{"issues": [{"severity": "high", "message": "Guarantees a 3x ROI with no evidence."}]}'
)


class StubLLM:
    """Stands in for the brain-tier model; records prompts, optionally fails."""

    def __init__(self, reply: str = CLEAN, *, error: Exception | None = None, delay: float = 0):
        self.reply = reply
        self.error = error
        self.delay = delay
        self.prompts: list[Any] = []

    async def ainvoke(self, prompt: Any) -> SimpleNamespace:
        self.prompts.append(prompt)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.reply)


@pytest.fixture
def brain(monkeypatch):
    """Install a brain-tier stub; returns the installer."""

    def _install(reply: str = CLEAN, **kwargs: Any) -> StubLLM:
        stub = StubLLM(reply, **kwargs)
        monkeypatch.setattr(
            "agency.services.llm_provider.get_brain_llm", lambda *a, **k: stub
        )
        return stub

    return _install


@pytest.fixture
async def tenant(session_factory):
    org_id = await create_org(session_factory, "Gate Org")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org_id, "Gate Brand")
    user_id = await create_user_row(session_factory, org_id)
    return SimpleNamespace(
        org_id=org_id,
        client_id=client_id,
        user_id=user_id,
        headers=auth_header_for(org_id, user_id=user_id),
    )


async def _piece(session_factory, content_id: UUID) -> ContentPiece:
    async with session_factory() as s:
        row = (
            await s.execute(select(ContentPiece).where(ContentPiece.id == content_id))
        ).scalar_one()
        return row


async def _new(session_factory, tenant, **kwargs: Any) -> UUID:
    return await create_content_row(session_factory, tenant.org_id, tenant.client_id, **kwargs)


# ---------------------------------------------------------------------------
# POST /content/{id}/approve
# ---------------------------------------------------------------------------
async def test_approve_passes_moderation(client, session_factory, tenant, brain):
    stub = brain(CLEAN)
    content_id = await _new(session_factory, tenant)

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=tenant.headers)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "id": str(content_id),
        "status": "approved",
        "moderation": {"status": "passed", "issues": []},
    }
    assert len(stub.prompts) == 1  # moderation actually ran
    piece = await _piece(session_factory, content_id)
    assert piece.status == "approved"
    assert piece.metadata_["moderation"]["status"] == "passed"


async def test_approve_flagged_is_409_and_status_unchanged(
    client, session_factory, tenant, brain
):
    brain(FLAGGED)
    content_id = await _new(session_factory, tenant)

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=tenant.headers)

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "moderation_flagged"
    assert detail["issues"] == [
        {"severity": "high", "message": "Guarantees a 3x ROI with no evidence."}
    ]
    piece = await _piece(session_factory, content_id)
    assert piece.status == "draft"
    assert "moderation" not in (piece.metadata_ or {})


async def test_approve_override_records_who_and_when(client, session_factory, tenant, brain):
    brain(FLAGGED)
    content_id = await _new(session_factory, tenant)

    resp = await client.post(
        f"{API}/content/{content_id}/approve?override=true", headers=tenant.headers
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["moderation"]["status"] == "overridden"
    assert body["moderation"]["issues"][0]["severity"] == "high"

    piece = await _piece(session_factory, content_id)
    record = piece.metadata_["moderation"]
    assert piece.status == "approved"
    assert record["status"] == "overridden"
    assert record["override_by"] == str(tenant.user_id)
    assert datetime.fromisoformat(record["at"])
    assert record["issues"] == body["moderation"]["issues"]


@pytest.mark.parametrize("failure", ["error", "timeout", "unparseable"])
async def test_approve_fails_open_when_llm_unavailable(
    client, session_factory, tenant, brain, monkeypatch, failure
):
    if failure == "error":
        brain(error=RuntimeError("503 from gateway"))
    elif failure == "timeout":
        monkeypatch.setattr(moderation, "MODERATION_TIMEOUT_SECONDS", 0.01)
        brain(CLEAN, delay=1)
    else:
        brain("I think this post is lovely!")
    content_id = await _new(session_factory, tenant)

    with capture_logs() as logs:
        resp = await client.post(
            f"{API}/content/{content_id}/approve", headers=tenant.headers
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["moderation"] == {"status": "unavailable", "issues": []}
    piece = await _piece(session_factory, content_id)
    assert piece.status == "approved"
    assert piece.metadata_["moderation"]["status"] == "unavailable"
    # Never silent.
    assert any(e["event"] == "moderation_unavailable" for e in logs)


async def test_approve_fails_open_when_no_provider_configured(
    client, session_factory, tenant, monkeypatch
):
    def _no_provider(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("No LLM provider configured")

    monkeypatch.setattr("agency.services.llm_provider.get_brain_llm", _no_provider)
    content_id = await _new(session_factory, tenant)

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=tenant.headers)
    assert resp.status_code == 200
    assert resp.json()["moderation"]["status"] == "unavailable"


@pytest.mark.parametrize("current", ["approved", "scheduled", "published", "failed"])
async def test_approve_rejects_invalid_status(
    client, session_factory, tenant, brain, current
):
    stub = brain(CLEAN)
    content_id = await _new(session_factory, tenant, status=current)

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=tenant.headers)

    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "invalid_status", "status": current}
    assert stub.prompts == []
    assert (await _piece(session_factory, content_id)).status == current


async def test_rejected_piece_can_be_approved(client, session_factory, tenant, brain):
    brain(CLEAN)
    content_id = await _new(session_factory, tenant, status="rejected")
    resp = await client.post(f"{API}/content/{content_id}/approve", headers=tenant.headers)
    assert resp.status_code == 200
    assert (await _piece(session_factory, content_id)).status == "approved"


async def test_approve_other_orgs_piece_is_404(client, session_factory, tenant, brain):
    stub = brain(CLEAN)
    org_b = await create_org(session_factory, "Other Org")
    client_b = await create_client_row(session_factory, org_b)
    content_b = await create_content_row(session_factory, org_b, client_b)

    resp = await client.post(f"{API}/content/{content_b}/approve", headers=tenant.headers)

    assert resp.status_code == 404
    assert stub.prompts == []
    assert (await _piece(session_factory, content_b)).status == "draft"


async def test_approve_uses_brand_profile_and_excluded_vocabulary(
    client, session_factory, tenant, brain
):
    async with session_factory() as s:
        s.add(
            BrandProfile(
                id=uuid4(),
                client_id=tenant.client_id,
                org_id=tenant.org_id,
                voice_description="Calm and plain-spoken",
                vocabulary_exclude=["synergy"],
                style_rules=[],
                tone_attributes={},
                example_posts=[],
            )
        )
        await s.commit()
    stub = brain(CLEAN)  # the model finds nothing; the code-level check still does
    content_id = await _new(
        session_factory, tenant, body="Unlock real Synergy across your team."
    )

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=tenant.headers)

    assert resp.status_code == 409
    issues = resp.json()["detail"]["issues"]
    assert any("synergy" in i["message"] for i in issues)
    # Brand context reached the model.
    assert "Calm and plain-spoken" in stub.prompts[0]
    assert "Gate Brand" in stub.prompts[0]


async def test_brand_context_is_org_scoped(session_factory, tenant):
    org_b = await create_org(session_factory, "Other Org")
    async with session_factory() as s:
        # Another tenant's client id resolves to nothing for this org.
        assert await moderation.load_brand_context(s, tenant.client_id, org_b) is None
        own = await moderation.load_brand_context(s, tenant.client_id, tenant.org_id)
        assert own is not None and own["brand_name"] == "Gate Brand"


# ---------------------------------------------------------------------------
# Character limit — code-level, independent of the LLM
# ---------------------------------------------------------------------------
def test_char_limit_twitter():
    assert moderation.check_char_limit("x" * 280, "twitter") is None
    issue = moderation.check_char_limit("x" * 281, "twitter")
    assert issue is not None and issue["severity"] == "high"
    assert "281" in issue["message"] and "280" in issue["message"]


def test_char_limit_counts_published_hashtags():
    # 270 + "\n\n" + "#abcdefgh" (9) = 281 — the publisher appends hashtags on X.
    assert moderation.check_char_limit("x" * 270, "twitter", ["abcdefgh"]) is not None
    # Facebook's publisher does not append hashtags, so they do not count there.
    assert moderation.check_char_limit("x" * 100, "facebook", ["a" * 70000]) is None


def test_char_limit_linkedin_and_unknown_platform():
    assert moderation.check_char_limit("x" * 3000, "linkedin") is None
    assert moderation.check_char_limit("x" * 3001, "linkedin") is not None
    assert moderation.check_char_limit("x" * 100000, "newsletter") is None


async def test_over_limit_flags_even_when_llm_is_down(client, session_factory, tenant, brain):
    brain(error=RuntimeError("down"))
    content_id = await _new(session_factory, tenant, platform="twitter", body="y" * 300)

    resp = await client.post(f"{API}/content/{content_id}/approve", headers=tenant.headers)

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "moderation_flagged"
    assert (await _piece(session_factory, content_id)).status == "draft"


# ---------------------------------------------------------------------------
# Schedule / publish accept only approved (or scheduled) content
# ---------------------------------------------------------------------------
@pytest.fixture
def no_real_publish(monkeypatch):
    """Fail the test outright if anything reaches a real platform publisher."""
    from agency.services.publishing import publisher

    async def _boom(*_a: Any, **_k: Any) -> dict:
        raise AssertionError("publisher reached for unapproved content")

    monkeypatch.setattr(publisher, "publish", _boom)


@pytest.mark.parametrize("current", ["draft", "rejected", "failed", "published"])
async def test_publish_rejects_unapproved(
    client, session_factory, tenant, no_real_publish, current
):
    content_id = await _new(session_factory, tenant, status=current)

    resp = await client.post(f"{API}/publishing/{content_id}/publish", headers=tenant.headers)

    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "not_approved", "status": current}
    assert (await _piece(session_factory, content_id)).status == current


@pytest.mark.parametrize("current", ["approved", "scheduled"])
async def test_publish_passes_gate_when_approved(client, session_factory, tenant, current):
    # Past the gate the next check is the connected account (none here → 400).
    content_id = await _new(session_factory, tenant, status=current)
    resp = await client.post(f"{API}/publishing/{content_id}/publish", headers=tenant.headers)
    assert resp.status_code == 400
    assert "no connected platform account" in resp.json()["detail"].lower()


@pytest.mark.parametrize("current", ["draft", "rejected", "failed", "published"])
async def test_schedule_rejects_unapproved(client, session_factory, tenant, current):
    content_id = await _new(session_factory, tenant, status=current)
    when = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    resp = await client.post(
        f"{API}/publishing/{content_id}/schedule",
        json={"scheduled_at": when},
        headers=tenant.headers,
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "not_approved", "status": current}
    piece = await _piece(session_factory, content_id)
    assert piece.status == current
    assert piece.scheduled_at is None


@pytest.mark.parametrize("current", ["approved", "scheduled"])
async def test_schedule_accepts_approved_and_reschedule(
    client, session_factory, tenant, current
):
    content_id = await _new(session_factory, tenant, status=current)
    when = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    resp = await client.post(
        f"{API}/publishing/{content_id}/schedule",
        json={"scheduled_at": when},
        headers=tenant.headers,
    )

    assert resp.status_code == 200, resp.text
    assert (await _piece(session_factory, content_id)).status == "scheduled"


# ---------------------------------------------------------------------------
# PATCH /content/{id}
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("target", ["approved", "scheduled", "published"])
async def test_patch_cannot_set_gated_status(client, session_factory, tenant, target):
    content_id = await _new(session_factory, tenant)

    resp = await client.patch(
        f"{API}/content/{content_id}", json={"status": target}, headers=tenant.headers
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "status_via_dedicated_endpoint"
    assert (await _piece(session_factory, content_id)).status == "draft"


async def test_patch_rejects_unknown_status(client, session_factory, tenant):
    content_id = await _new(session_factory, tenant)
    resp = await client.patch(
        f"{API}/content/{content_id}", json={"status": "whatever"}, headers=tenant.headers
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unsupported_status"


@pytest.mark.parametrize(("start", "target"), [("draft", "rejected"), ("rejected", "draft")])
async def test_patch_may_set_draft_or_rejected(client, session_factory, tenant, start, target):
    content_id = await _new(session_factory, tenant, status=start)
    resp = await client.patch(
        f"{API}/content/{content_id}", json={"status": target}, headers=tenant.headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == target


@pytest.mark.parametrize("current", ["approved", "scheduled"])
@pytest.mark.parametrize("edit", [{"body": "Edited body"}, {"hashtags": ["new"]}])
async def test_editing_approved_content_resets_to_draft(
    client, session_factory, tenant, current, edit
):
    content_id = await _new(session_factory, tenant, status=current)
    async with session_factory() as s:
        row = (
            await s.execute(select(ContentPiece).where(ContentPiece.id == content_id))
        ).scalar_one()
        row.scheduled_at = datetime.now(UTC) + timedelta(days=1)
        row.metadata_ = {"moderation": {"status": "passed"}}
        await s.commit()

    resp = await client.patch(f"{API}/content/{content_id}", json=edit, headers=tenant.headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "draft"
    piece = await _piece(session_factory, content_id)
    assert piece.status == "draft"
    assert piece.scheduled_at is None
    assert "moderation" not in piece.metadata_


async def test_title_only_edit_keeps_approval(client, session_factory, tenant):
    content_id = await _new(session_factory, tenant, status="approved")
    resp = await client.patch(
        f"{API}/content/{content_id}", json={"title": "New title"}, headers=tenant.headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


async def test_unchanged_body_does_not_reset(client, session_factory, tenant):
    content_id = await _new(session_factory, tenant, status="approved", body="Same")
    resp = await client.patch(
        f"{API}/content/{content_id}", json={"body": "Same"}, headers=tenant.headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


# ---------------------------------------------------------------------------
# Portal approve — same moderation, no override
# ---------------------------------------------------------------------------
@pytest.fixture
async def portal(session_factory):
    org_id = await create_org(session_factory, "Portal Org", slug="gate-portal")
    await create_white_label(session_factory, org_id)
    client_id = await create_client_row(session_factory, org_id)
    return SimpleNamespace(org_id=org_id, client_id=client_id)


@pytest.mark.parametrize("query", ["", "?override=true"])
async def test_portal_approve_flagged_is_409(client, session_factory, portal, brain, query):
    brain(FLAGGED)
    content_id = await create_content_row(session_factory, portal.org_id, portal.client_id)

    resp = await client.patch(
        f"{API}/portal/gate-portal/content/{content_id}{query}",
        json={"decision": "approve", "override": True},
    )

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "moderation_flagged"
    assert detail["issues"][0]["severity"] == "high"
    assert (await _piece(session_factory, content_id)).status == "draft"


async def test_portal_approve_clean_approves(client, session_factory, portal, brain):
    stub = brain(CLEAN)
    content_id = await create_content_row(session_factory, portal.org_id, portal.client_id)

    resp = await client.patch(
        f"{API}/portal/gate-portal/content/{content_id}", json={"decision": "approve"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["moderation"]["status"] == "passed"
    assert len(stub.prompts) == 1
    assert (await _piece(session_factory, content_id)).status == "approved"


async def test_portal_reject_still_works(client, session_factory, portal, brain):
    stub = brain(CLEAN)
    content_id = await create_content_row(session_factory, portal.org_id, portal.client_id)
    resp = await client.patch(
        f"{API}/portal/gate-portal/content/{content_id}", json={"decision": "reject"}
    )
    assert resp.status_code == 200
    assert stub.prompts == []
    assert (await _piece(session_factory, content_id)).status == "rejected"
