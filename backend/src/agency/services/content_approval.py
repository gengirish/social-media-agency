"""The approval gate — the only way content becomes publishable.

Status lifecycle enforced here (DB values; the UI labels ``draft`` as *Pending*)::

    draft / rejected --approve (moderated)--> approved --schedule--> scheduled --> published
                                                  \\------publish now------------------/

- :func:`approve_content_piece` is the single approval path (dashboard and portal).
  It runs :func:`~agency.services.moderation.moderate_content` first.
- :func:`ensure_publishable` guards schedule and publish-now.
- :func:`ensure_client_active` refuses both for an archived client.
- :func:`apply_content_edit` is the PATCH logic: it refuses status moves that belong to
  the dedicated endpoints, and sends edited approved/scheduled content back to ``draft``
  so it is re-moderated.

Violations raise :class:`ContentGateError`, which routers translate to an HTTP error
with the structured ``detail`` the frontend branches on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import Client
from agency.services import product_analytics as pa
from agency.services.moderation import load_brand_context, moderate_content
from agency.services.publishing import UNAVAILABLE_PUBLISH_PLATFORMS

logger = structlog.get_logger()

APPROVABLE_STATUSES: Final = frozenset({"draft", "rejected"})
PUBLISHABLE_STATUSES: Final = frozenset({"approved", "scheduled"})
#: Statuses only the dedicated endpoints may set.
GATED_STATUSES: Final = frozenset({"approved", "scheduled", "published"})
#: Statuses a plain PATCH may set.
PATCHABLE_STATUSES: Final = frozenset({"draft", "rejected"})


#: A ``models.tables.ContentPiece`` row. Typed ``Any`` because the models use classic
#: ``Column(...)`` declarations, which mypy (without the SQLAlchemy plugin) reads as
#: ``Column[str]`` and rejects every plain attribute assignment on.
ContentRow = Any


class ContentGateError(Exception):
    """A gate refused the operation. ``detail`` is the structured API error body."""

    def __init__(self, status_code: int, detail: dict[str, Any]):
        super().__init__(detail.get("code", "content_gate"))
        self.status_code = status_code
        self.detail = detail


def _merge_metadata(piece: ContentRow, updates: dict[str, Any]) -> None:
    base = dict(piece.metadata_ or {})
    base.update(updates)
    piece.metadata_ = base


def empty_content_reason(piece: ContentRow) -> str | None:
    """Why this piece has nothing to approve, or ``None`` when it does.

    The pipeline stores a variant the ad agent returned empty as ``failed`` rather
    than ``draft``, so it never reaches approval — but rows written before that are
    drafts whose body is the string ``"[]"``, and hiding the button in the UI does
    not stop a direct call. Both are covered by judging the content.

    A blank body is only empty when there is no attached media either: an
    image-only post is legitimately bodyless.
    """
    metadata = piece.metadata_ or {}
    generation = metadata.get("generation")
    if isinstance(generation, dict) and generation.get("status") == "failed":
        reason = generation.get("reason")
        return str(reason) if reason else "This item was generated empty."

    ad = metadata.get("ad")
    if isinstance(ad, dict):
        fields = ad.get("fields")
        if isinstance(fields, dict) and not any(fields.values()):
            return "The ad copy agent returned no usable copy for this variant."
        # Structured ad variants carry their copy in ``fields``; the body is only a
        # flattened mirror of it, so an empty body is not itself a problem here.
        return None

    body = (piece.body or "").strip()
    # "[]" and "{}" are what the old ad-variant path wrote when the agent returned
    # no headlines. They read as content to any length check but say nothing.
    if body in {"", "[]", "{}", '""'} and not (piece.media_urls or []):
        return "This item has no content."
    return None


def ensure_has_content(piece: ContentRow) -> None:
    """Approval gate: refuse an item with nothing in it (CF-05)."""
    reason = empty_content_reason(piece)
    if reason is not None:
        raise ContentGateError(
            409, {"code": "empty_content", "status": piece.status, "message": reason}
        )


async def approve_content_piece(
    db: AsyncSession,
    piece: ContentRow,
    *,
    org_id: UUID,
    override: bool = False,
    user_id: UUID | None = None,
) -> dict[str, Any]:
    """Moderate, then approve. Commits on success; leaves the piece untouched on refusal.

    ``piece`` must already have been loaded with an ``org_id`` filter by the caller.

    Raises :class:`ContentGateError`:

    - 409 ``invalid_status`` — only ``draft``/``rejected`` pieces can be approved.
    - 409 ``empty_content`` — the piece has nothing in it to approve.
    - 409 ``moderation_flagged`` — issues found and ``override`` is false.

    With ``override=True`` a flagged piece is approved and the override is recorded
    in ``metadata.moderation`` (who and when). Returns the approve response body.
    """
    if piece.status not in APPROVABLE_STATUSES:
        raise ContentGateError(409, {"code": "invalid_status", "status": piece.status})
    return await _moderate_then_approve(
        db, piece, org_id=org_id, override=override, user_id=user_id
    )


async def retry_failed_content(
    db: AsyncSession,
    piece: ContentRow,
    *,
    org_id: UUID,
    override: bool = False,
    user_id: UUID | None = None,
) -> dict[str, Any]:
    """Move a piece whose publish failed back to ``approved`` so it can be retried (CF-06).

    A ``failed`` post had only Delete on it, which made a transient publish failure —
    an expired token, a platform 503 — unrecoverable: the copy had to be written
    again from scratch. It now goes back to the publishable state it was in before
    the attempt.

    Moderation runs again rather than being skipped. The body may have been edited
    since the failure (editing a failed piece leaves it failed), and product rule 3
    is that nothing reaches a publishable status without a moderation check on the
    text as it now stands.

    Raises :class:`ContentGateError`:

    - 409 ``not_failed`` — only a ``failed`` piece can be retried.
    - 409 ``empty_content`` / ``moderation_flagged`` — as for approval.
    """
    if piece.status != "failed":
        raise ContentGateError(409, {"code": "not_failed", "status": piece.status})
    return await _moderate_then_approve(
        db,
        piece,
        org_id=org_id,
        override=override,
        user_id=user_id,
        # The previous attempt's error must not linger: the card renders it from
        # metadata, so leaving it would label a retried post as still failing.
        clear_metadata_keys=("publish_error",),
    )


async def _moderate_then_approve(
    db: AsyncSession,
    piece: ContentRow,
    *,
    org_id: UUID,
    override: bool,
    user_id: UUID | None,
    clear_metadata_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    """The shared body of approve and retry: check, moderate, set ``approved``.

    Kept in one place so a second route into ``approved`` cannot drift from the
    first — the gate is only worth anything if every path runs it.
    """
    # Before moderation: there is nothing to moderate, and approving it would put an
    # empty post in the publish queue.
    ensure_has_content(piece)

    brand_context = await load_brand_context(db, piece.client_id, org_id)
    result = await moderate_content(
        piece.body or "", piece.platform, brand_context, hashtags=piece.hashtags
    )

    if result.issues and not override:
        logger.info(
            "moderation_flagged",
            content_id=str(piece.id),
            issue_count=len(result.issues),
        )
        # The piece stays untouched; the refusal itself is recorded so Insights'
        # clean-approval rate and the activity log count real moderation runs.
        await pa.track(
            db,
            name=pa.MODERATION_FLAGGED,
            org_id=org_id,
            user_id=user_id,
            campaign_id=piece.campaign_id,
            properties={
                "content_id": str(piece.id),
                "client_id": str(piece.client_id),
                "platform": piece.platform,
                "issue_count": len(result.issues),
            },
        )
        await db.commit()
        raise ContentGateError(
            409, {"code": "moderation_flagged", "issues": result.issues}
        )

    now = datetime.now(UTC).isoformat()
    record: dict[str, Any] = {
        "issues": result.issues,
        "at": now,
        "llm_checked": result.llm_checked,
    }
    if result.issues:
        record["status"] = "overridden"
        record["override_by"] = str(user_id) if user_id else None
        logger.warning(
            "moderation_overridden",
            content_id=str(piece.id),
            override_by=record["override_by"],
            issue_count=len(result.issues),
        )
    else:
        record["status"] = result.status  # "passed" or "unavailable"

    piece.status = "approved"
    if clear_metadata_keys:
        meta = dict(piece.metadata_ or {})
        for key in clear_metadata_keys:
            meta.pop(key, None)
        piece.metadata_ = meta
    _merge_metadata(piece, {"moderation": record})
    await db.commit()

    return {
        "id": str(piece.id),
        "status": "approved",
        "moderation": {"status": record["status"], "issues": result.issues},
    }


def ensure_publishable(piece: ContentRow) -> None:
    """Schedule / publish-now gate: only ``approved`` or ``scheduled`` content."""
    if piece.status not in PUBLISHABLE_STATUSES:
        raise ContentGateError(409, {"code": "not_approved", "status": piece.status})


async def ensure_client_active(db: AsyncSession, piece: ContentRow) -> None:
    """Schedule / publish-now gate: nothing goes live on an archived client's accounts.

    Archiving already refuses while posts are scheduled, so together these mean an
    archived client has nothing queued and nothing new can be queued.
    """
    is_active = (
        await db.execute(
            select(Client.is_active).where(
                Client.id == piece.client_id, Client.org_id == piece.org_id
            )
        )
    ).scalar_one_or_none()
    if not is_active:
        raise ContentGateError(409, {"code": "client_archived"})


def ensure_schedulable(piece: ContentRow) -> None:
    """Schedule gate: publishable *and* on a platform the scheduler can publish to.

    A scheduled Instagram/TikTok post would only turn into a ``failed`` row when it
    comes due, so refuse it up front with 409 ``platform_unavailable``.
    """
    ensure_publishable(piece)
    reason = UNAVAILABLE_PUBLISH_PLATFORMS.get((piece.platform or "").lower())
    if reason:
        raise ContentGateError(
            409, {"code": "platform_unavailable", "platform": piece.platform, "reason": reason}
        )


def apply_content_edit(
    piece: ContentRow,
    *,
    title: str | None = None,
    body: str | None = None,
    hashtags: list[str] | None = None,
    status: str | None = None,
) -> None:
    """Apply a PATCH to ``piece`` in place (caller commits).

    - ``status`` cannot change once ``published`` (409 ``published_locked``).
    - ``status`` may only be ``draft`` or ``rejected``; ``approved``/``scheduled``/
      ``published`` → 400 ``status_via_dedicated_endpoint``, anything else → 400
      ``unsupported_status``.
    - Changing ``body`` or ``hashtags`` (what the publisher posts) of an ``approved`` or
      ``scheduled`` piece resets it to ``draft`` (and drops its schedule and moderation
      record): edited content must be re-moderated before it can be published.
    """
    if status is not None:
        # A published piece is live on the client's account. Moving it back to
        # draft/rejected would let it be re-approved and published a second time.
        if piece.status == "published":
            raise ContentGateError(409, {"code": "published_locked", "status": piece.status})
        if status in GATED_STATUSES:
            raise ContentGateError(
                400, {"code": "status_via_dedicated_endpoint", "status": status}
            )
        if status not in PATCHABLE_STATUSES:
            raise ContentGateError(
                400,
                {"code": "unsupported_status", "allowed": sorted(PATCHABLE_STATUSES)},
            )

    content_changed = (body is not None and body != piece.body) or (
        hashtags is not None and list(hashtags) != list(piece.hashtags or [])
    )

    if title is not None:
        piece.title = title
    if body is not None:
        piece.body = body
    if hashtags is not None:
        piece.hashtags = hashtags

    if content_changed and piece.status in APPROVABLE_STATUSES:
        # Insights' quality signal: an edit while still pending means the draft
        # needed a fix before approval ("edited", not "kept"). Later corrections
        # to approved content are not counted, as in Cadence.
        _merge_metadata(piece, {"edited_before_approval": True})

    if content_changed and piece.status in PUBLISHABLE_STATUSES:
        logger.info(
            "content_edit_reset_to_draft", content_id=str(piece.id), was=piece.status
        )
        piece.status = "draft"
        piece.scheduled_at = None
        meta = dict(piece.metadata_ or {})
        meta.pop("moderation", None)
        piece.metadata_ = meta

    if status is not None:
        piece.status = status
