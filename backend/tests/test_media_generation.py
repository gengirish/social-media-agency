"""Image generation as a proper generator — Phase 2 of the media plan.

Every assertion here is about money or about a gate, which is why they are
written to fail if the step they cover is removed:

- the quota is required **before** the provider is called, so a cap cannot be
  discovered after fal has already been paid;
- a repeat generate returns the existing asset and charges nothing (the largest
  real cost saving in this feature, because users re-click);
- a bad provider response is a 502 that saves nothing;
- a cancelled generate saves nothing and charges nothing, matching Post Studio;
- the piece stays ``draft`` — no media path writes ``approved``/``scheduled``;
- the ``media_asset`` row and the ``media_urls`` projection are both written;
- a ``content_id`` from another org 404s. There is no RLS in this database.

``media_credits`` and ``media_moderation`` are other agents' modules and still
raise ``NotImplementedError``, so they are mocked here per their frozen
signatures. fal.ai and storage are mocked too; nothing touches a real provider.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from agency.models.tables import BrandProfile, ContentPiece, MediaAsset
from agency.services import media_generation
from agency.services.media_generation import build_image_prompt, generate_image_for_piece
from agency.services.media_moderation import MediaModerationResult
from agency.services.media_storage import MediaStorageError, StoredMedia
from tests.conftest import (
    create_client_row,
    create_content_row,
    create_org,
    create_subscription,
    create_user_row,
)

BRIEF = {
    "visualConcept": "A lone kayaker on a glass-flat lake at dawn",
    "composition": "Wide shot, subject lower-left third",
    "style": "Editorial photography, natural light",
    "colorDirection": "Cool blues with one warm highlight",
    "textOverlay": "No text overlay",
    "aspectRatio": "4:5",
    "altText": "A kayaker paddling across still water at sunrise",
}

STORED = StoredMedia(
    storage_key="org/client/content/asset.png",
    url="https://cdn.example.test/org/client/content/asset.png",
    thumb_url="https://cdn.example.test/org/client/content/asset.thumb.webp",
    mime="image/png",
    bytes=4096,
    width=1024,
    height=768,
)


class Recorder:
    """Installs the whole seam and records the order every step ran in.

    The order list is the point: "quota before the provider" is only testable if
    both calls land in one sequence.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[str] = []
        self.charged: list[str] = []
        self.provider: dict[str, Any] = {
            "status": "generated",
            "image_url": "https://fal.test/out.png",
            "platform": "linkedin",
        }
        self.prompts: list[str] = []
        self.quota_error: HTTPException | None = None
        self.storage_error: MediaStorageError | None = None
        self.verdict = MediaModerationResult(status="passed", vision_checked=True)
        self.stored = STORED

        async def require(db: Any, org_id: UUID, kind: str) -> Any:
            self.calls.append(f"require:{kind}")
            if self.quota_error is not None:
                raise self.quota_error
            return SimpleNamespace(org_id=org_id)

        async def charge(db: Any, org_id: UUID, kind: str) -> int:
            self.calls.append(f"charge:{kind}")
            self.charged.append(kind)
            return 1

        async def generate(prompt: str, platform: str = "twitter", style: str = "x") -> Any:
            self.calls.append("provider")
            self.prompts.append(prompt)
            return dict(self.provider)

        async def persist(source_url: str, **kwargs: Any) -> StoredMedia:
            self.calls.append("persist")
            if self.storage_error is not None:
                raise self.storage_error
            return self.stored

        async def moderate(**kwargs: Any) -> MediaModerationResult:
            self.calls.append("moderate")
            return self.verdict

        monkeypatch.setattr(media_generation, "require_media_credits", require)
        monkeypatch.setattr(media_generation, "charge_media_credits", charge)
        monkeypatch.setattr(media_generation, "generate_social_image", generate)
        monkeypatch.setattr(media_generation, "persist_from_url", persist)
        monkeypatch.setattr(media_generation, "moderate_media", moderate)


@pytest.fixture
def seam(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    return Recorder(monkeypatch)


@pytest.fixture
async def tenant(session_factory: Any) -> SimpleNamespace:
    org_id = await create_org(session_factory, "Media Org")
    await create_subscription(session_factory, org_id, plan_tier="growth")
    client_id = await create_client_row(session_factory, org_id, "Media Brand")
    user_id = await create_user_row(session_factory, org_id)
    content_id = await create_content_row(
        session_factory,
        org_id,
        client_id,
        platform="linkedin",
        body="Dawn is the only hour the lake is still. Here is what that taught us about launches.",
        metadata={"creative_brief": BRIEF},
    )
    async with session_factory() as s:
        s.add(
            BrandProfile(
                id=uuid4(),
                org_id=org_id,
                client_id=client_id,
                voice_description="Calm, concrete, never breathless",
                tone_attributes={"register": "measured"},
                vocabulary_include=["craft"],
                vocabulary_exclude=["synergy"],
                example_posts=[],
                style_rules=["No stock-photo handshakes"],
                emoji_policy="none",
                target_audience="Founders who post themselves",
                competitor_differentiation="A human approves every post",
            )
        )
        await s.commit()
    return SimpleNamespace(
        org_id=org_id, client_id=client_id, user_id=user_id, content_id=content_id
    )


async def _assets(db: Any, org_id: UUID) -> list[Any]:
    rows = await db.execute(select(MediaAsset).where(MediaAsset.org_id == org_id))
    return list(rows.scalars().all())


async def _piece(db: Any, content_id: UUID) -> Any:
    db.expire_all()
    return (
        await db.execute(select(ContentPiece).where(ContentPiece.id == content_id))
    ).scalar_one()


# --------------------------------------------------------------------------- #
# build_image_prompt — assembled in code, no second LLM call (§1F)
# --------------------------------------------------------------------------- #


def test_prompt_composes_the_brief_brand_block_and_post() -> None:
    prompt = build_image_prompt(
        creative_brief=BRIEF,
        brand_context={"brand_name": "Still Water", "vocabulary_exclude": ["synergy"]},
        platform="instagram",
        body="Dawn  is\nthe only hour.",
        title="The quiet hour",
    )
    assert prompt.startswith("Visual concept: A lone kayaker")
    for fragment in (
        "Composition: Wide shot",
        "Art direction: Editorial photography",
        "Colour direction: Cool blues",
        "Text overlay: No text overlay",
        "Intended ratio: 4:5",
        # The platform's ratio comes last and wins over the brief's.
        "Render for instagram at aspect ratio square.",
        "Brand context:",
        "Brand: Still Water",
        "Never use: synergy",
        "The post this image accompanies:",
        "The quiet hour",
        "Dawn is the only hour.",
    ):
        assert fragment in prompt, fragment
    # The screen-reader field is not an instruction to the image model.
    assert BRIEF["altText"] not in prompt


def test_prompt_without_a_brief_falls_back_to_brand_and_body() -> None:
    prompt = build_image_prompt(
        creative_brief=None,
        brand_context={"brand_name": "Still Water", "industry": "saas"},
        platform="unknown-platform",
        body="q" * (media_generation.BODY_PROMPT_CHARS + 50),
    )
    assert "Visual concept" not in prompt
    assert "Brand: Still Water" in prompt
    assert "Render for unknown-platform at aspect ratio landscape_16_9." in prompt
    # Truncated, so a long caption cannot become the subject of the picture.
    assert prompt.count("q") == media_generation.BODY_PROMPT_CHARS


def test_prompt_is_deterministic() -> None:
    kwargs: dict[str, Any] = {
        "creative_brief": BRIEF,
        "brand_context": {"brand_name": "Still Water"},
        "platform": "linkedin",
        "body": "Same body",
        "title": "Same title",
    }
    assert build_image_prompt(**kwargs) == build_image_prompt(**kwargs)


# --------------------------------------------------------------------------- #
# generate_image_for_piece
# --------------------------------------------------------------------------- #


async def test_quota_is_required_before_the_provider_is_called(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    """A 402 must land before fal is paid, not after."""
    seam.quota_error = HTTPException(402, {"code": "media_credit_quota_exceeded"})

    with pytest.raises(HTTPException) as exc:
        await generate_image_for_piece(db, org_id=tenant.org_id, content_id=tenant.content_id)

    assert exc.value.status_code == 402
    # The provider never ran, so the order is unambiguous.
    assert seam.calls == ["require:image"]
    assert seam.charged == []
    assert await _assets(db, tenant.org_id) == []
    assert list((await _piece(db, tenant.content_id)).media_urls or []) == []


async def test_quota_precedes_the_provider_on_the_happy_path(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    await generate_image_for_piece(db, org_id=tenant.org_id, content_id=tenant.content_id)
    assert seam.calls == ["require:image", "provider", "persist", "moderate", "charge:image"]


async def test_asset_row_and_media_urls_are_both_written(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    asset, deduped = await generate_image_for_piece(
        db, org_id=tenant.org_id, content_id=tenant.content_id, user_id=str(tenant.user_id)
    )

    # A real generation, and the router must be able to say so.
    assert deduped is False
    assert asset.kind == "image"
    assert asset.storage_key == STORED.storage_key
    assert asset.url == STORED.url
    assert asset.thumb_url == STORED.thumb_url
    assert (asset.width, asset.height, asset.bytes) == (1024, 768, 4096)
    assert asset.credits_charged == 1
    assert asset.created_by == tenant.user_id
    assert asset.content_id == tenant.content_id
    assert asset.client_id == tenant.client_id
    # Screened at generation time; an empty dict is what the approve path reads
    # as "not yet screened".
    assert asset.moderation["status"] == "passed"
    assert asset.prompt_hash and asset.prompt.startswith("Visual concept:")
    # The brand reached the one output where it is most visible.
    assert "Never use: synergy" in asset.prompt

    rows = await _assets(db, tenant.org_id)
    assert [r.id for r in rows] == [asset.id]
    # media_urls is the publish-facing projection; same transaction.
    assert list((await _piece(db, tenant.content_id)).media_urls) == [STORED.url]


async def test_dedupe_returns_the_existing_asset_and_charges_nothing(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    first, first_deduped = await generate_image_for_piece(
        db, org_id=tenant.org_id, content_id=tenant.content_id
    )
    assert first_deduped is False
    seam.calls.clear()

    second, deduped = await generate_image_for_piece(
        db, org_id=tenant.org_id, content_id=tenant.content_id
    )

    assert second.id == first.id
    # The flag is the only honest way for the UI to say "reused — no credits
    # were used": a deduped row carries the original generation's
    # ``credits_charged``, so nothing on it distinguishes the two cases.
    assert deduped is True
    # Neither the provider nor the quota was touched on the repeat.
    assert seam.calls == []
    assert seam.charged == ["image"]
    assert len(await _assets(db, tenant.org_id)) == 1
    # And the projection did not grow a duplicate entry.
    assert list((await _piece(db, tenant.content_id)).media_urls) == [STORED.url]


async def test_a_different_style_is_not_a_dedupe_hit(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    """Style and platform change the picture without changing the prompt text."""
    await generate_image_for_piece(db, org_id=tenant.org_id, content_id=tenant.content_id)
    seam.stored = StoredMedia(
        storage_key="org/client/content/second.png",
        url="https://cdn.example.test/second.png",
        thumb_url="",
        mime="image/png",
        bytes=10,
    )
    _, deduped = await generate_image_for_piece(
        db, org_id=tenant.org_id, content_id=tenant.content_id, style="illustrated"
    )
    assert deduped is False
    assert len(await _assets(db, tenant.org_id)) == 2
    assert seam.charged == ["image", "image"]


@pytest.mark.parametrize(
    "response",
    [
        {"status": "error", "message": "fal.ai returned 500", "image_url": None},
        {"status": "generated", "image_url": ""},
        {"status": "generated"},
        {},
    ],
    ids=["provider_error", "empty_url", "missing_url", "empty_body"],
)
async def test_a_malformed_provider_response_is_a_502_that_saves_nothing(
    db: Any, tenant: SimpleNamespace, seam: Recorder, response: dict[str, Any]
) -> None:
    seam.provider = response

    with pytest.raises(HTTPException) as exc:
        await generate_image_for_piece(db, org_id=tenant.org_id, content_id=tenant.content_id)

    assert exc.value.status_code == 502
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "media_generation_failed"
    assert "No media credits were used" in detail["message"]
    assert seam.charged == []
    assert await _assets(db, tenant.org_id) == []
    assert list((await _piece(db, tenant.content_id)).media_urls or []) == []


async def test_a_storage_failure_is_a_502_that_saves_nothing(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    seam.storage_error = MediaStorageError("Refusing to store media of type 'text/html'")

    with pytest.raises(HTTPException) as exc:
        await generate_image_for_piece(db, org_id=tenant.org_id, content_id=tenant.content_id)

    assert exc.value.status_code == 502
    assert seam.charged == []
    assert await _assets(db, tenant.org_id) == []
    assert list((await _piece(db, tenant.content_id)).media_urls or []) == []


async def test_a_blank_fal_key_is_a_503_not_a_charge(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    """``skipped`` means the feature is off — a retry cannot help."""
    seam.provider = {
        "status": "skipped",
        "message": "Image generation not configured. Set FAL_API_KEY.",
        "image_url": None,
    }

    with pytest.raises(HTTPException) as exc:
        await generate_image_for_piece(db, org_id=tenant.org_id, content_id=tenant.content_id)

    assert exc.value.status_code == 503
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "media_generation_not_configured"
    assert seam.charged == []
    assert await _assets(db, tenant.org_id) == []


async def test_cancel_saves_nothing_and_charges_nothing(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    """Post Studio's semantics: checked after the provider returned."""

    async def gone() -> bool:
        return True

    with pytest.raises(HTTPException) as exc:
        await generate_image_for_piece(
            db,
            org_id=tenant.org_id,
            content_id=tenant.content_id,
            is_disconnected=gone,
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "cancelled"
    # After the provider returned — the cost is sunk by then — but before the
    # storage write, so no paid-for bytes are left with no row pointing at them.
    assert seam.calls == ["require:image", "provider"]
    assert seam.charged == []
    assert await _assets(db, tenant.org_id) == []
    assert list((await _piece(db, tenant.content_id)).media_urls or []) == []


async def test_a_still_connected_caller_is_not_cancelled(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    async def here() -> bool:
        return False

    asset, deduped = await generate_image_for_piece(
        db, org_id=tenant.org_id, content_id=tenant.content_id, is_disconnected=here
    )
    assert asset.url == STORED.url
    assert deduped is False
    assert seam.charged == ["image"]


async def test_the_piece_is_still_draft_afterwards(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    """No media path writes ``approved`` or ``scheduled`` (product rule 3)."""
    await generate_image_for_piece(db, org_id=tenant.org_id, content_id=tenant.content_id)
    assert (await _piece(db, tenant.content_id)).status == "draft"


async def test_a_published_piece_is_refused_and_nothing_is_written(
    db: Any, tenant: SimpleNamespace, seam: Recorder, session_factory: Any
) -> None:
    """An image appended to a live post is not in that post."""
    published = await create_content_row(
        session_factory,
        tenant.org_id,
        tenant.client_id,
        status="published",
        metadata={"creative_brief": BRIEF},
    )

    with pytest.raises(HTTPException) as exc:
        await generate_image_for_piece(db, org_id=tenant.org_id, content_id=published)

    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "published_locked"
    # Refused before the quota, let alone the provider.
    assert seam.calls == []
    assert seam.charged == []
    assert await _assets(db, tenant.org_id) == []
    row = await _piece(db, published)
    assert row.status == "published"
    assert list(row.media_urls or []) == []


@pytest.mark.parametrize("was", ["approved", "scheduled"])
async def test_attaching_media_reopens_an_approved_piece(
    db: Any, tenant: SimpleNamespace, seam: Recorder, session_factory: Any, was: str
) -> None:
    """A media_urls edit is new outgoing content, so it goes back for review."""
    piece_id = await create_content_row(
        session_factory,
        tenant.org_id,
        tenant.client_id,
        status=was,
        metadata={"creative_brief": BRIEF},
    )

    asset, deduped = await generate_image_for_piece(db, org_id=tenant.org_id, content_id=piece_id)
    assert deduped is False
    assert asset.content_id == piece_id

    row = await _piece(db, piece_id)
    assert row.status == "draft"
    # The reset is in the same transaction as the attach, not instead of it.
    assert list(row.media_urls) == [STORED.url]


async def test_a_dedupe_hit_that_changes_nothing_does_not_reopen_a_piece(
    db: Any, tenant: SimpleNamespace, seam: Recorder, session_factory: Any
) -> None:
    """Re-clicking on an image the piece already carries is not an edit."""
    piece_id = await create_content_row(
        session_factory,
        tenant.org_id,
        tenant.client_id,
        status="draft",
        metadata={"creative_brief": BRIEF},
    )
    await generate_image_for_piece(db, org_id=tenant.org_id, content_id=piece_id)
    # Approve it by hand, as the approve endpoint would.
    row = await _piece(db, piece_id)
    row.status = "approved"
    await db.commit()

    await generate_image_for_piece(db, org_id=tenant.org_id, content_id=piece_id)

    assert (await _piece(db, piece_id)).status == "approved"
    assert seam.charged == ["image"]


async def test_a_prompt_override_still_carries_the_brand(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    asset, _ = await generate_image_for_piece(
        db,
        org_id=tenant.org_id,
        content_id=tenant.content_id,
        prompt_override="A single espresso cup on concrete",
    )
    assert "A single espresso cup on concrete" in asset.prompt
    assert "Never use: synergy" in asset.prompt
    # The brief's concept was replaced, not merged.
    assert "kayaker" not in asset.prompt


async def test_content_from_another_org_is_404(
    db: Any, tenant: SimpleNamespace, seam: Recorder, session_factory: Any
) -> None:
    """There is no row-level security: this filter *is* the isolation boundary."""
    other_org = await create_org(session_factory, "Other Org")
    other_client = await create_client_row(session_factory, other_org, "Other Brand")
    other_content = await create_content_row(session_factory, other_org, other_client)

    with pytest.raises(HTTPException) as exc:
        await generate_image_for_piece(db, org_id=tenant.org_id, content_id=other_content)

    assert exc.value.status_code == 404
    assert seam.calls == []
    assert seam.charged == []
    assert await _assets(db, other_org) == []


async def test_a_missing_piece_is_404(
    db: Any, tenant: SimpleNamespace, seam: Recorder
) -> None:
    with pytest.raises(HTTPException) as exc:
        await generate_image_for_piece(db, org_id=tenant.org_id, content_id=uuid4())
    assert exc.value.status_code == 404
    assert seam.calls == []
