"""Comments router — threaded comments on content pieces."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import ContentComment, User

router = APIRouter(prefix="/comments", tags=["Comments"])


@router.post("/content/{content_id}")
async def add_comment(
    content_id: UUID,
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    comment_body = body.get("body", "").strip()
    if not comment_body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Comment body required")

    comment = ContentComment(
        content_id=content_id,
        user_id=user.id,
        org_id=org_id,
        body=comment_body,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return {
        "id": str(comment.id),
        "content_id": str(content_id),
        "user_id": str(user.id),
        "user_name": user.full_name,
        "body": comment.body,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


@router.get("/content/{content_id}")
async def list_comments(
    content_id: UUID,
    user=Depends(get_current_user),
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
        user_result = await db.execute(select(User).where(User.id == c.user_id))
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
    user=Depends(get_current_user),
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
    if comment.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Can only delete own comments")

    await db.delete(comment)
    await db.commit()
    return {"status": "deleted"}
