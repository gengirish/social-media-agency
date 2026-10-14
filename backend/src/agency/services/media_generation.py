"""Generates an image for a content piece, as a proper Create-screen generator.

STAGE 1 CONTRACT — signatures and semantics are frozen; bodies are Phase 2.
Fill these in place. Do not edit `routers/content.py`, `billing.py`,
`config.py`, `tables.py`, `media_credits.py` or `media_moderation.py` — other
agents own those, and `media_storage.py` is already finished. Report anything
that looks like it needs a shared-file change.

What this replaces: ``POST /content/{id}/generate-image`` called
``image_generation.generate_social_image`` directly and appended the provider's
expiring CDN URL to ``media_urls``. No quota, no cancel check, no stored asset,
no moderation, and a prompt built from ``piece.title`` or the first 100 chars of
the body — so brand voice, vocabulary and the client's campaign focus were all
absent from the one output where they are most visible.

Order of operations, which is the whole contract (copied from Amplify):

1. ``get_org_piece`` → ``get_org_client``  (404 across orgs)
2. ``build_image_prompt``                  (no model call — see below)
3. dedupe on ``prompt_hash``               (return the existing asset with
   ``deduped=True``, charge nothing)
4. ``require_media_credits(db, org_id, "image")``
5. generate
6. ``request.is_disconnected()`` → save nothing, charge nothing
   (ahead of ``media_storage.persist_from_url``, which then stores it: the
   provider cost is already sunk, but a cancelled generate must not write
   paid-for bytes no row points at)
7. ``moderate_media`` → onto the new ``MediaAsset.moderation``
8. write ``MediaAsset`` **and** append to ``content_piece.media_urls``, one transaction
9. ``charge_media_credits`` → commit

A malformed or empty provider response is a ``502`` saying no credits were used,
and nothing is saved.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.config import get_settings
from agency.models.tables import MediaAsset
from agency.services.brand_context import brand_prompt_block, get_org_client, load_brand_context
from agency.services.image_generation import PLATFORM_ASPECT_RATIOS, generate_social_image
from agency.services.media_credits import charge_media_credits, require_media_credits
from agency.services.media_moderation import moderate_media
from agency.services.media_storage import MediaStorageError, persist_from_url, prompt_hash
from agency.services.post_studio import get_org_piece

logger = structlog.get_logger()

#: The brief's fields, in the order they go into the prompt, with the label the
#: image model sees. Ordered and closed on purpose: the prompt string is the
#: dedupe key, so dict iteration order must never be able to change it.
#: ``altText`` is deliberately absent — it describes the image for a screen
#: reader, which is not an instruction to the generator.
BRIEF_PROMPT_FIELDS: tuple[tuple[str, str], ...] = (
    ("visualConcept", "Visual concept"),
    ("composition", "Composition"),
    ("style", "Art direction"),
    ("colorDirection", "Colour direction"),
    ("textOverlay", "Text overlay"),
)

#: How much of the post the prompt carries. Enough for the model to know what
#: the image sits next to, short enough that the caption does not become the
#: subject of the picture.
BODY_PROMPT_CHARS = 600

#: Fallback when a piece has no platform. ``PLATFORM_ASPECT_RATIOS`` already
#: defaults unknown platforms to 16:9; this only picks the label.
DEFAULT_PLATFORM = "twitter"


def _provider_failed(message: str, **log: Any) -> HTTPException:
    """502, and say plainly that the user was not billed for it."""
    logger.error("media_generation_failed", error=message, **log)
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        {
            "code": "media_generation_failed",
            "message": f"{message} No media credits were used, and nothing was saved.",
        },
    )


def _not_configured(message: str) -> HTTPException:
    """503 — the feature is off, which is not the provider misbehaving.

    Kept distinct from :func:`_provider_failed` for the same reason
    ``video_not_in_plan`` is distinct from a quota error: the UI should tell an
    operator to set a key, not offer a retry that cannot work.
    """
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        {
            "code": "media_generation_not_configured",
            "message": f"{message} No media credits were used.",
        },
    )


def _cancelled() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "code": "cancelled",
            "message": "Cancelled — nothing was saved and no media credits were used.",
        },
    )


#: Attaching media re-opens the piece for review, exactly as editing its body
#: does: ``media_urls`` is what the publishers send, so a new image is new
#: outgoing content and product rule 3 applies to it.
#:
#: Enforced here because this is the only site that writes ``media_urls`` today.
#: Stage 3 consolidates the rule into ``content_approval.py`` when ``PATCH
#: /content/{id}`` grows the same behaviour — the duplication is deliberate
#: until then, and this should defer to it once it exists.
RE_REVIEW_STATUSES = frozenset({"approved", "scheduled"})


def _attach_media_url(piece: Any, url: str) -> bool:
    """Append one URL to the publish-facing projection. True when it changed.

    An unchanged piece is not re-opened: a dedupe hit on an image the piece
    already carries has not altered what would be published.
    """
    media = list(piece.media_urls or [])
    if not url or url in media:
        return False
    media.append(url)
    piece.media_urls = media
    if piece.status in RE_REVIEW_STATUSES:
        logger.info("media_attach_reset_to_draft", was=str(piece.status), piece_id=str(piece.id))
        # Never the other direction: no media path writes `approved`/`scheduled`.
        piece.status = "draft"
    return True


def _as_uuid(value: Any) -> UUID | None:
    """``created_by`` tolerantly: the caller's id arrives as a str or a UUID."""
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value:
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def build_image_prompt(
    *,
    creative_brief: dict[str, Any] | None,
    brand_context: dict[str, Any] | None,
    platform: str,
    body: str,
    title: str = "",
) -> str:
    """Assemble the prompt in code. **No second LLM call.**

    ``metadata.creative_brief`` already exists from a worker-tier call
    (``post_studio.attach_creative_brief``), so deriving the prompt from it
    costs zero extra tokens. Generating a fresh prompt per image would pay a
    model call per image forever, plus the latency.

    Deterministic assembly is also the same discipline as ``plan_atoms``
    assigning Amplify angles in code rather than letting the model choose.

    With no brief, fall back to ``brand_prompt_block`` plus the post body — a
    worse prompt, not an error, because the brief is optional in the UI.
    """
    brief = creative_brief if isinstance(creative_brief, dict) else {}
    brand = brand_context if isinstance(brand_context, dict) else {}
    key = (platform or DEFAULT_PLATFORM).lower()
    aspect = PLATFORM_ASPECT_RATIOS.get(key, PLATFORM_ASPECT_RATIOS[DEFAULT_PLATFORM])

    lines: list[str] = []
    for field, label in BRIEF_PROMPT_FIELDS:
        value = str(brief.get(field) or "").strip()
        if value:
            lines.append(f"{label}: {value}")

    # The brief may name its own ratio; the platform's is what the image is
    # actually rendered at, so it goes last and wins.
    brief_aspect = str(brief.get("aspectRatio") or "").strip()
    if brief_aspect:
        lines.append(f"Intended ratio: {brief_aspect}")
    lines.append(f"Render for {key} at aspect ratio {aspect}.")

    block = brand_prompt_block(brand).strip() if brand else ""
    if block:
        lines.extend(["", "Brand context:", block])

    heading = str(title or "").strip()
    excerpt = " ".join(str(body or "").split())[:BODY_PROMPT_CHARS].strip()
    if heading or excerpt:
        lines.extend(["", "The post this image accompanies:"])
        if heading:
            lines.append(heading)
        if excerpt:
            lines.append(excerpt)

    return "\n".join(lines).strip()


async def generate_image_for_piece(
    db: AsyncSession,
    *,
    org_id: UUID,
    content_id: UUID,
    user_id: Any = None,
    style: str = "professional",
    prompt_override: str | None = None,
    is_disconnected: Any = None,
) -> tuple[MediaAsset, bool]:
    """Run the full flow above. Returns ``(asset, deduped)``.

    ``deduped`` is True when step 3 hit and this asset was generated earlier.
    The router reports it as ``deduped`` on the response so the UI can say
    "reused an existing image — no credits were used". It cannot be inferred
    from the row: a deduped asset carries the ``credits_charged`` of its
    original generation, so nothing on it distinguishes the two cases, and
    guessing would mean implying a charge that did not happen.

    ``is_disconnected`` is the request's ``is_disconnected`` callable, checked
    **after** the provider returns but **before** anything is stored: a user who
    navigated away gets nothing saved and nothing charged, matching Post Studio.
    The other generators only stop the browser waiting, and say so.

    A ``published`` piece is refused (``published_locked``); an ``approved`` or
    ``scheduled`` one goes back to ``draft`` in the same transaction as the
    ``media_urls`` append, because a new image is new outgoing content.

    ``prompt_override`` is for an explicit user-written prompt. It still goes
    through the brand block, because an override of the subject is not an
    override of the brand.
    """
    # 1. Both ids resolved against org_id before anything is joined on or
    #    written to them. There is no row-level security in this database.
    piece: Any = await get_org_piece(db, content_id, org_id)
    if piece.status == "published":
        # An image appended to a live post is not in that post, so there is
        # nothing truthful we could do with it. Same shape as
        # ``post_studio.attach_creative_brief``.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "published_locked", "status": str(piece.status)},
        )
    # Legacy Column-typed models read as ``Column[...]`` without the mypy plugin;
    # ``Any`` here is the same dodge ``post_studio.Row`` uses.
    client: Any = await get_org_client(db, piece.client_id, org_id)
    platform = str(piece.platform or "").lower() or DEFAULT_PLATFORM
    brand = await load_brand_context(db, client, org_id)

    # 2. Assembled in code. An override replaces the brief's subject, not the
    #    brand block: the brand is not the user's to override here.
    meta = piece.metadata_ if isinstance(piece.metadata_, dict) else {}
    override = (prompt_override or "").strip()
    brief: dict[str, Any] | None
    if override:
        brief = {"visualConcept": override}
    else:
        raw_brief = meta.get("creative_brief")
        brief = raw_brief if isinstance(raw_brief, dict) else None
    prompt = build_image_prompt(
        creative_brief=brief,
        brand_context=brand,
        platform=platform,
        body="" if override else str(piece.body or ""),
        title="" if override else str(piece.title or ""),
    )

    model = get_settings().fal_image_model
    # Platform and style change the picture without changing the prompt text, so
    # they belong in the hash — otherwise a square re-render would dedupe onto a
    # landscape image.
    phash = prompt_hash(prompt=prompt, model=model, params={"platform": platform, "style": style})

    # 3. Dedupe before charging — the largest real saving in this feature,
    #    because users re-click. Scoped to (org_id, prompt_hash), which is also
    #    the unique index.
    existing = (
        await db.execute(
            select(MediaAsset).where(MediaAsset.org_id == org_id, MediaAsset.prompt_hash == phash)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if _attach_media_url(piece, str(existing.url or "")):
            await db.commit()
        logger.info(
            "media_generation_deduped",
            org_id=str(org_id),
            content_id=str(content_id),
            asset_id=str(existing.id),
        )
        return existing, True

    # 4. Quota before the provider is called, never after.
    await require_media_credits(db, org_id, "image")

    # 5. Generate, then persist: the provider's CDN URL expires, so writing it
    #    to media_urls would produce a post whose image is gone by publish time.
    result = await generate_social_image(prompt, platform, style)
    provider_status = str(result.get("status") or "")
    if provider_status == "skipped":
        raise _not_configured(str(result.get("message") or "Image generation is not configured."))
    if provider_status != "generated":
        raise _provider_failed(
            str(result.get("message") or "The image provider failed."),
            org_id=str(org_id),
            content_id=str(content_id),
        )
    image_url = str(result.get("image_url") or "").strip()
    if not image_url:
        raise _provider_failed(
            "The image provider returned no image.",
            org_id=str(org_id),
            content_id=str(content_id),
        )

    # 6. Cancel, checked once the provider has returned — the cost is sunk by
    #    then, so bailing earlier would save nothing — but *before* the storage
    #    write, which would otherwise leave paid-for bytes no row points at,
    #    invisible to the per-org prefix accounting. Post Studio's semantics:
    #    nothing saved, nothing charged.
    if is_disconnected is not None and await is_disconnected():
        logger.info("media_generation_cancelled", org_id=str(org_id), content_id=str(content_id))
        raise _cancelled()

    asset_id = uuid4()
    try:
        stored = await persist_from_url(
            image_url,
            org_id=org_id,
            client_id=client.id,
            content_id=piece.id,
            asset_id=asset_id,
        )
    except MediaStorageError as exc:
        raise _provider_failed(
            f"Could not store the generated image: {exc}",
            org_id=str(org_id),
            content_id=str(content_id),
        ) from None

    # 7. Screened here, not on the approve path: the user is already waiting on
    #    the provider, so this costs nothing perceptible.
    verdict = await moderate_media(
        kind="image",
        image_url=stored.url,
        # fal's has_nsfw_concepts is the free signal media_moderation wants, but
        # generate_social_image does not forward it today (reported, not fixed:
        # image_generation.py is not this agent's file).
        provider_flags=(
            {"has_nsfw_concepts": result["has_nsfw_concepts"]}
            if "has_nsfw_concepts" in result
            else None
        ),
        brand_context=brand,
    )

    # 8 + 9. One transaction. The charge statement is issued before the INSERT so
    # ``credits_charged`` is known when the row is built and a lost race saves no
    # asset; both land or neither does.
    charged = await charge_media_credits(db, org_id, "image")
    asset = MediaAsset(
        id=asset_id,
        org_id=org_id,
        client_id=client.id,
        content_id=piece.id,
        kind="image",
        storage_key=stored.storage_key,
        url=stored.url,
        thumb_url=stored.thumb_url,
        mime=stored.mime,
        width=stored.width,
        height=stored.height,
        duration_ms=stored.duration_ms,
        bytes=stored.bytes,
        model=model,
        prompt=prompt,
        prompt_hash=phash,
        credits_charged=charged,
        moderation=verdict.as_metadata(),
        created_by=_as_uuid(user_id),
    )
    db.add(asset)

    # media_urls is the publish-facing projection content_approval.py and the
    # publishers read; media_asset is the record. Same transaction, always —
    # including the re-review reset, so an approved piece cannot gain an image
    # nobody reviewed.
    _attach_media_url(piece, stored.url)
    await db.commit()
    await db.refresh(asset)
    logger.info(
        "media_generated",
        org_id=str(org_id),
        content_id=str(content_id),
        asset_id=str(asset.id),
        credits=charged,
        moderation=verdict.status,
    )
    return asset, False
