"""Client review — the public pages a client opens from a review link.

Unauthenticated by design: the token in the path is the whole credential, and
``services/client_review.py`` scopes every read and write to the one client (and
campaign) the link was made for.

This replaced the ``/portal/{org_slug}/...`` routes on 261031. Those resolved an
org from its public slug and then listed — and accepted approvals for — every
client's content in that org, so anyone with an agency's slug could read client A's
unreleased drafts and approve client B's. Nothing in the frontend called them.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.dependencies import get_db
from agency.models.tables import ContentPiece
from agency.services.client_review import (
    ReviewLinkError,
    decide,
    resolve_review_link,
    review_page,
)
from agency.services.handoff import approved_event_payload
from agency.services.webhook_dispatcher import EVENT_CONTENT_APPROVED, dispatch_webhook

router = APIRouter(prefix="/portal", tags=["Client Review"])


@router.get("/review/{token}")
async def get_review(token: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """The review page: agency branding, the client, and the posts to decide on.

    404 ``link_not_found``; 410 ``link_revoked`` / ``link_expired`` / ``link_inactive``.
    """
    try:
        resolved = await resolve_review_link(db, token)
        return await review_page(db, resolved)
    except ReviewLinkError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None


@router.post("/review/{token}/content/{content_id}")
async def post_review_decision(
    token: str,
    content_id: UUID,
    background: BackgroundTasks,
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Approve, or ask for changes on, one post.

    Body: ``{"decision": "approve" | "request_changes", "comment"?: str, "name"?: str}``.
    ``comment`` is required for ``request_changes``. Approval runs moderation with no
    override; a flagged post answers 409 ``approval_held`` and stays Pending for the
    agency. See :func:`agency.services.client_review.decide` for every code.
    """
    try:
        resolved = await resolve_review_link(db, token)
        result = await decide(
            db,
            resolved,
            content_id=content_id,
            decision=str(body.get("decision", "")),
            comment=body.get("comment"),
            reviewer_name=body.get("name"),
        )
    except ReviewLinkError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None

    if result["approved"]:
        piece = (
            await db.execute(
                select(ContentPiece).where(
                    ContentPiece.id == content_id,
                    ContentPiece.org_id == resolved.link.org_id,
                )
            )
        ).scalar_one()
        # Same event the dashboard's approve fires: a scheduler recipe listening for
        # approvals must not miss the ones a client gave.
        background.add_task(
            dispatch_webhook,
            resolved.link.org_id,
            EVENT_CONTENT_APPROVED,
            await approved_event_payload(db, piece),
        )
    return {"item": result["item"]}
