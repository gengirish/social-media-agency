from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.schemas import ContentPieceResponse, ContentUpdateRequest
from agency.models.tables import ContentPiece

router = APIRouter(prefix="/content", tags=["Content"])


@router.get("")
async def list_content(
    campaign_id: UUID | None = None,
    client_id: UUID | None = None,
    content_status: str | None = None,
    platform: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    q = select(ContentPiece).where(ContentPiece.org_id == org_id)
    count_q = select(func.count(ContentPiece.id)).where(ContentPiece.org_id == org_id)

    if campaign_id:
        q = q.where(ContentPiece.campaign_id == campaign_id)
        count_q = count_q.where(ContentPiece.campaign_id == campaign_id)
    if client_id:
        q = q.where(ContentPiece.client_id == client_id)
        count_q = count_q.where(ContentPiece.client_id == client_id)
    if content_status:
        q = q.where(ContentPiece.status == content_status)
        count_q = count_q.where(ContentPiece.status == content_status)
    if platform:
        q = q.where(ContentPiece.platform == platform)
        count_q = count_q.where(ContentPiece.platform == platform)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(
        q.order_by(ContentPiece.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    pieces = result.scalars().all()

    return {"items": pieces, "total": total, "page": page, "per_page": per_page}


@router.get("/{content_id}", response_model=ContentPieceResponse)
async def get_content(
    content_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id, ContentPiece.org_id == org_id
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")
    return piece


@router.patch("/{content_id}", response_model=ContentPieceResponse)
async def update_content(
    content_id: UUID,
    request: ContentUpdateRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id, ContentPiece.org_id == org_id
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    if request.title is not None:
        piece.title = request.title
    if request.body is not None:
        piece.body = request.body
    if request.hashtags is not None:
        piece.hashtags = request.hashtags
    if request.status is not None:
        piece.status = request.status

    await db.commit()
    await db.refresh(piece)
    return piece


@router.post("/{content_id}/approve")
async def approve_content(
    content_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id, ContentPiece.org_id == org_id
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    piece.status = "approved"
    await db.commit()
    return {"status": "approved", "content_id": str(content_id)}
