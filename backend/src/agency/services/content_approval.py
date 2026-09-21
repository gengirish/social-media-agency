"""The approval gate — the only way content becomes publishable.

Status lifecycle enforced here (DB values; the UI labels ``draft`` as *Pending*)::

    draft / rejected --approve (moderated)--> approved --schedule--> scheduled --> published
                                                  \\------publish now------------------/

- :func:`approve_content_piece` is the single approval path (dashboard and portal).
  It runs :func:`~agency.services.moderation.moderate_content` first.
- :func:`ensure_publishable` guards schedule and publish-now.
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
from sqlalchemy.ext.asyncio import AsyncSession

from agency.services.moderation import load_brand_context, moderate_content

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
    - 409 ``moderation_flagged`` — issues found and ``override`` is false.

    With ``override=True`` a flagged piece is approved and the override is recorded
    in ``metadata.moderation`` (who and when). Returns the approve response body.
    """
    if piece.status not in APPROVABLE_STATUSES:
        raise ContentGateError(409, {"code": "invalid_status", "status": piece.status})

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


def apply_content_edit(
    piece: ContentRow,
    *,
    title: str | None = None,
    body: str | None = None,
    hashtags: list[str] | None = None,
    status: str | None = None,
) -> None:
    """Apply a PATCH to ``piece`` in place (caller commits).

    - ``status`` may only be ``draft`` or ``rejected``; ``approved``/``scheduled``/
      ``published`` → 400 ``status_via_dedicated_endpoint``, anything else → 400
      ``unsupported_status``.
    - Changing ``body`` or ``hashtags`` (what the publisher posts) of an ``approved`` or
      ``scheduled`` piece resets it to ``draft`` (and drops its schedule and moderation
      record): edited content must be re-moderated before it can be published.
    """
    if status is not None:
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
