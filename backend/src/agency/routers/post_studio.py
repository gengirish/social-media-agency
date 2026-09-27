"""Posts › Queue and Calendar actions on a single post (Cadence parity).

Thin: logic lives in ``services/post_studio.py``, prompts in
``agents/post_writer.py``. Nothing here approves, schedules or publishes —
created and rewritten posts are always Pending (``draft``).

Paths are spelled out in full because they share ``/content`` with
``routers/content.py``; none collides with a route there (it has no
``POST /content``, ``POST /content/generate`` or ``DELETE /content/{id}``).
The channel list lives under ``/post-studio`` so it can never be captured by
``GET /content/{content_id}``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents.post_writer import MAX_CONTEXT_NOTE
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.services import post_studio as svc

router = APIRouter(tags=["Posts"])


class GenerateRequest(BaseModel):
    client_id: UUID
    platform: str = Field(min_length=1, max_length=50)
    context_note: str = Field(default="", max_length=MAX_CONTEXT_NOTE)
    #: Calendar only: the day this draft is planned for. Not a schedule.
    planned_for: datetime | None = None


class ManualPostRequest(BaseModel):
    client_id: UUID
    platform: str = Field(min_length=1, max_length=50)
    body: str = Field(min_length=1, max_length=10_000)
    planned_for: datetime | None = None


def piece_out(piece: Any) -> dict[str, Any]:
    """The Queue's ``QueuePost`` shape."""
    return {
        "id": str(piece.id),
        "campaign_id": str(piece.campaign_id) if piece.campaign_id else None,
        "client_id": str(piece.client_id),
        "content_type": piece.content_type,
        "platform": piece.platform,
        "title": piece.title or "",
        "body": piece.body or "",
        "hashtags": list(piece.hashtags or []),
        "status": piece.status,
        "ai_generated": bool(piece.ai_generated),
        "performance_score": piece.performance_score,
        "metadata_": piece.metadata_ if isinstance(piece.metadata_, dict) else {},
        "scheduled_at": piece.scheduled_at.isoformat() if piece.scheduled_at else None,
        "published_at": piece.published_at.isoformat() if piece.published_at else None,
        "created_at": piece.created_at.isoformat() if piece.created_at else None,
    }


def _cancel_check(request: Request) -> svc.CancelCheck:
    return request.is_disconnected


@router.get("/post-studio/channels")
async def channels(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Connected platforms for one client, plus every platform a post can be written for."""
    return {
        "connected": await svc.connected_platforms(db, client_id, org_id),
        "supported": list(svc.SUPPORTED_PLATFORMS),
    }


@router.post("/content/generate", status_code=status.HTTP_201_CREATED)
async def generate(
    body: GenerateRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """One new Pending draft for ``platform``. Charges one generation (402 when exhausted)."""
    piece = await svc.generate_draft(
        db,
        org_id=org_id,
        client_id=body.client_id,
        platform=body.platform,
        context_note=body.context_note,
        planned_for=body.planned_for,
        cancelled=_cancel_check(request),
    )
    return piece_out(piece)


@router.post("/content", status_code=status.HTTP_201_CREATED)
async def create_manual(
    body: ManualPostRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """A hand-written post. Always Pending — approve (moderated) before scheduling."""
    piece = await svc.create_manual_draft(
        db,
        org_id=org_id,
        client_id=body.client_id,
        platform=body.platform,
        body=body.body,
        planned_for=body.planned_for,
    )
    return piece_out(piece)


@router.post("/content/{content_id}/regenerate")
async def regenerate(
    content_id: UUID,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Rewrite a Pending draft in place. 409 ``invalid_status`` unless draft/rejected."""
    piece = await svc.regenerate_draft(
        db, org_id=org_id, content_id=content_id, cancelled=_cancel_check(request)
    )
    return piece_out(piece)


@router.post("/content/{content_id}/creative-brief")
async def creative_brief(
    content_id: UUID,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """A written brief for a designer, stored in ``metadata.creative_brief``. Not an image."""
    piece = await svc.attach_creative_brief(
        db, org_id=org_id, content_id=content_id, cancelled=_cancel_check(request)
    )
    return piece_out(piece)


@router.delete("/content/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    content_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> Response:
    """Delete an unpublished post. 409 ``published_locked`` for a published one."""
    await svc.delete_piece(db, org_id=org_id, content_id=content_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
