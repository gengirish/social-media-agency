"""Queue / Calendar actions that create, rewrite or remove a single post.

Cadence's Posts screen, server side: "Generate a post", "Regenerate" in place,
the Creative Director's brief, a manual post from the Calendar, and delete.

Invariants (CLAUDE.md, Approval gate):

- Everything created or rewritten here is ``status="draft"`` (Pending). Nothing
  here writes ``approved``, ``scheduled`` or ``published``; moderation runs at
  approve time, as for every other content path.
- A draft may carry ``scheduled_at`` as its *planned* day (Calendar's "Add
  post" / "Fill with AI"). That is only a plan: the scheduler publishes
  ``status == "scheduled"`` rows only, and a draft reaches ``scheduled`` solely
  through approve (moderated) and then the schedule endpoint.
- Each user-initiated generation charges one generation, only after a usable
  result, and only if the caller is still waiting for it (Cancel).
- Every client-supplied id is resolved against ``org_id`` before use.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents.post_writer import (
    PostWriterError,
    generate_creative_brief,
    generate_platform_post,
)
from agency.models.tables import Client, ContentPiece, PlatformAccount
from agency.services.brand_context import get_org_client, load_brand_context
from agency.services.generation_quota import charge_generation, require_generation_quota
from agency.services.repurpose import PLATFORM_CHAR_LIMITS, rendered_length

logger = structlog.get_logger()

#: Platforms a post can be written for — the ones with a known format and cap.
SUPPORTED_PLATFORMS: tuple[str, ...] = tuple(PLATFORM_CHAR_LIMITS)

#: Only never-approved drafts can be regenerated (Cadence offers it on Pending only).
REGENERATABLE_STATUSES = frozenset({"draft", "rejected"})

#: Returns True when the caller has gone away (Cancel). Checked after the model
#: returns and before anything is saved or charged.
CancelCheck = Callable[[], Awaitable[bool]]

#: Legacy Column-typed model; mypy reads attributes as Column[...] without the plugin.
Row = Any


def _meta(piece: Row) -> dict[str, Any]:
    raw = piece.metadata_
    return dict(raw) if isinstance(raw, dict) else {}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _unsupported(platform: str) -> HTTPException:
    return HTTPException(
        422,
        {
            "code": "unsupported_platform",
            "platform": platform,
            "supported": list(SUPPORTED_PLATFORMS),
        },
    )


def _generation_failed(exc: Exception, **log: Any) -> HTTPException:
    logger.error("post_generation_failed", error=str(exc), **log)
    message = (
        f"{exc}; no quota was used. Try again."
        if isinstance(exc, PostWriterError)
        else "Generation failed; no quota was used. Try again."
    )
    return HTTPException(status.HTTP_502_BAD_GATEWAY, message)


def _cancelled() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {"code": "cancelled", "message": "Cancelled — nothing was saved and no quota was used."},
    )


async def get_org_piece(db: AsyncSession, content_id: UUID, org_id: UUID) -> Row:
    """The content piece, or 404 — including when it belongs to another org."""
    piece = (
        await db.execute(
            select(ContentPiece).where(ContentPiece.id == content_id, ContentPiece.org_id == org_id)
        )
    ).scalar_one_or_none()
    if piece is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")
    return piece


async def _active_client(db: AsyncSession, client_id: UUID, org_id: UUID) -> Client:
    client = await get_org_client(db, client_id, org_id)
    if not client.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "client_archived"})
    return client


async def connected_platforms(db: AsyncSession, client_id: UUID, org_id: UUID) -> list[str]:
    """Platforms with a connected account for this client, in a stable order."""
    await get_org_client(db, client_id, org_id)
    rows = await db.execute(
        select(PlatformAccount.platform).where(
            PlatformAccount.org_id == org_id,
            PlatformAccount.client_id == client_id,
            PlatformAccount.status == "connected",
        )
    )
    found = {str(p).lower() for p in rows.scalars().all() if p}
    ordered = [p for p in SUPPORTED_PLATFORMS if p in found]
    return ordered + sorted(found - set(ordered))


async def generate_draft(
    db: AsyncSession,
    *,
    org_id: UUID,
    client_id: UUID,
    platform: str,
    context_note: str = "",
    planned_for: datetime | None = None,
    cancelled: CancelCheck | None = None,
) -> Row:
    """"Generate a post": one new Pending draft. Charges one generation."""
    platform = platform.lower()
    if platform not in SUPPORTED_PLATFORMS:
        raise _unsupported(platform)
    client = await _active_client(db, client_id, org_id)
    await require_generation_quota(db, org_id)
    brand = await load_brand_context(db, client, org_id)

    try:
        draft = await generate_platform_post(
            platform=platform, brand=brand, context_note=context_note
        )
    except Exception as exc:
        raise _generation_failed(exc, org_id=str(org_id), platform=platform) from None

    if cancelled is not None and await cancelled():
        logger.info("post_generation_cancelled", org_id=str(org_id), platform=platform)
        raise _cancelled()

    note = context_note.strip()
    piece = ContentPiece(
        org_id=org_id,
        client_id=client.id,
        campaign_id=None,
        content_type="social_post",
        platform=platform,
        title=draft["title"],
        body=draft["body"],
        hashtags=draft["hashtags"],
        metadata_={
            "source": "queue_generate",
            **({"context_note": note[:280]} if note else {}),
        },
        media_urls=[],
        ai_generated=True,
        # Pending, always — never taken from the request.
        status="draft",
        scheduled_at=planned_for,
    )
    db.add(piece)
    await charge_generation(db, org_id)
    await db.commit()
    await db.refresh(piece)
    return piece


async def regenerate_draft(
    db: AsyncSession,
    *,
    org_id: UUID,
    content_id: UUID,
    cancelled: CancelCheck | None = None,
) -> Row:
    """Rewrite a Pending draft in place: same id, platform and position.

    Stays ``draft``; any earlier moderation record is dropped because the text
    it judged is gone. Charges one generation.
    """
    piece = await get_org_piece(db, content_id, org_id)
    if piece.status not in REGENERATABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"code": "invalid_status", "status": piece.status}
        )
    platform = str(piece.platform or "").lower()
    if platform not in SUPPORTED_PLATFORMS:
        raise _unsupported(platform)
    client = await _active_client(db, piece.client_id, org_id)
    await require_generation_quota(db, org_id)
    brand = await load_brand_context(db, client, org_id)
    meta = _meta(piece)

    try:
        draft = await generate_platform_post(
            platform=platform,
            brand=brand,
            context_note=str(meta.get("context_note") or ""),
            previous_body=str(piece.body or ""),
        )
    except Exception as exc:
        raise _generation_failed(exc, org_id=str(org_id), content_id=str(content_id)) from None

    if cancelled is not None and await cancelled():
        logger.info("post_regenerate_cancelled", content_id=str(content_id))
        raise _cancelled()

    # Re-read status: a concurrent approve during the model call must not be
    # silently overwritten with unmoderated text.
    await db.refresh(piece)
    if piece.status not in REGENERATABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"code": "invalid_status", "status": piece.status}
        )

    meta = _meta(piece)
    meta.pop("moderation", None)
    meta["regenerated_at"] = _now_iso()
    meta["regenerate_count"] = int(meta.get("regenerate_count") or 0) + 1
    piece.title = draft["title"]
    piece.body = draft["body"]
    piece.hashtags = draft["hashtags"]
    piece.ai_generated = True
    piece.status = "draft"
    piece.metadata_ = meta
    await charge_generation(db, org_id)
    await db.commit()
    await db.refresh(piece)
    return piece


async def attach_creative_brief(
    db: AsyncSession,
    *,
    org_id: UUID,
    content_id: UUID,
    cancelled: CancelCheck | None = None,
) -> Row:
    """Creative Director: store a designer brief on the piece. No image is made.

    Written to ``metadata.creative_brief``; the post's text and status are
    untouched, so an approved post stays approved. Charges one generation.
    """
    piece = await get_org_piece(db, content_id, org_id)
    if piece.status == "published":
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"code": "published_locked", "status": piece.status}
        )
    client = await get_org_client(db, piece.client_id, org_id)
    await require_generation_quota(db, org_id)
    brand = await load_brand_context(db, client, org_id)

    try:
        brief = await generate_creative_brief(
            platform=str(piece.platform or ""),
            body=str(piece.body or ""),
            hashtags=list(piece.hashtags or []),
            brand=brand,
        )
    except Exception as exc:
        raise _generation_failed(exc, org_id=str(org_id), content_id=str(content_id)) from None

    if cancelled is not None and await cancelled():
        logger.info("creative_brief_cancelled", content_id=str(content_id))
        raise _cancelled()

    meta = _meta(piece)
    meta["creative_brief"] = {**brief, "generated_at": _now_iso()}
    piece.metadata_ = meta
    await charge_generation(db, org_id)
    await db.commit()
    await db.refresh(piece)
    return piece


async def create_manual_draft(
    db: AsyncSession,
    *,
    org_id: UUID,
    client_id: UUID,
    platform: str,
    body: str,
    planned_for: datetime | None = None,
) -> Row:
    """Calendar's "Add your own post". A Pending draft — never scheduled.

    Cadence documents the bug this avoids: a hand-written post added straight
    to ``scheduled`` skipped moderation. Free: no model is called.
    """
    platform = platform.lower()
    if platform not in SUPPORTED_PLATFORMS:
        raise _unsupported(platform)
    text = body.strip()
    if not text:
        raise HTTPException(422, "Post text is required")
    limit = PLATFORM_CHAR_LIMITS[platform]
    if rendered_length(text, []) > limit:
        raise HTTPException(
            422,
            {"code": "over_limit", "limit": limit, "length": len(text)},
        )
    client = await _active_client(db, client_id, org_id)
    piece = ContentPiece(
        org_id=org_id,
        client_id=client.id,
        campaign_id=None,
        content_type="social_post",
        platform=platform,
        title=text.split("\n", 1)[0][:80],
        body=text,
        hashtags=[],
        metadata_={"source": "calendar_manual"},
        media_urls=[],
        ai_generated=False,
        status="draft",
        scheduled_at=planned_for,
    )
    db.add(piece)
    await db.commit()
    await db.refresh(piece)
    return piece


async def delete_piece(db: AsyncSession, *, org_id: UUID, content_id: UUID) -> None:
    """Delete a post that has not gone out.

    ``published`` → 409 ``published_locked``: it is live on the client's
    account, and its row carries the post id/url analytics hang off. A
    ``scheduled`` piece may be deleted — it simply never publishes.
    """
    piece = await get_org_piece(db, content_id, org_id)
    if piece.status == "published":
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"code": "published_locked", "status": piece.status}
        )
    logger.info(
        "content_deleted", content_id=str(content_id), org_id=str(org_id), was=piece.status
    )
    await db.delete(piece)
    await db.commit()
