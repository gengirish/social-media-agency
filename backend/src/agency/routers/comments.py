"""Comments router — threaded comments on content pieces."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from agency.dependencies import get_current_user, get_current_user_id, get_db, get_org_id
from agency.models.tables import ContentComment, ContentPiece, User

router = APIRouter(prefix="/comments", tags=["Comments"])


@router.post("/content/{content_id}")
async def add_comment(
    content_id: UUID,
    body: dict,
    user: dict[str, Any] = Depends(get_current_user),
    user_id: UUID = Depends(get_current_user_id),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    comment_body = body.get("body", "").strip()
    if not comment_body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Comment body required")

    # TENANCY: ``content_id`` is a path param and is not otherwise checked. Without this
    # the caller can hang comment rows off another tenant's content piece.
    owner = await db.execute(
        select(ContentPiece.id).where(
            ContentPiece.id == content_id, ContentPiece.org_id == org_id
        )
    )
    if owner.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    comment = ContentComment(
        content_id=content_id,
        user_id=user_id,
        org_id=org_id,
        body=comment_body,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # The token carries no display name, so resolve it; fall back to the token email.
    author = await db.execute(
        select(User.full_name).where(User.id == user_id, User.org_id == org_id)
    )
    return {
        "id": str(comment.id),
        "content_id": str(content_id),
        "user_id": str(user_id),
        "user_name": author.scalar_one_or_none() or user.get("email") or "Unknown",
        "body": comment.body,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


@router.get("/content/{content_id}")
async def list_comments(
    content_id: UUID,
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(ContentComment)
        .where(ContentComment.content_id == content_id, ContentComment.org_id == org_id)
        .order_by(ContentComment.created_at.asc())
    )
    comments = result.scalars().all()

    items = []
    for c in comments:
        user_result = await db.execute(
            select(User).where(User.id == c.user_id, User.org_id == org_id)
        )
        u = user_result.scalar_one_or_none()
        items.append({
            "id": str(c.id),
            "content_id": str(c.content_id),
            "user_id": str(c.user_id),
            "user_name": u.full_name if u else "Unknown",
            "body": c.body,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return {"items": items}


@router.delete("/{comment_id}")
async def delete_comment(
    comment_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(ContentComment).where(
            ContentComment.id == comment_id,
            ContentComment.org_id == org_id,
        )
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
    if comment.user_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Can only delete own comments")

    await db.delete(comment)
    await db.commit()
    return {"status": "deleted"}
