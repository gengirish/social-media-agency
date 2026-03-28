"""Client portal router — public-facing routes for white-label client access."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from agency.dependencies import get_db
from agency.models.tables import Campaign, ContentPiece, Organization, WhiteLabel

router = APIRouter(prefix="/portal", tags=["Client Portal"])


async def _resolve_org(db, org_slug: str):
    """Resolve org from slug (domain or name-based)."""
    result = await db.execute(
        select(Organization).where(Organization.domain == org_slug)
    )
    org = result.scalar_one_or_none()
    if not org:
        result = await db.execute(
            select(Organization).where(Organization.name == org_slug)
        )
        org = result.scalar_one_or_none()
    return org


async def _require_portal_branding(db, org_id: UUID) -> WhiteLabel:
    result = await db.execute(
        select(WhiteLabel).where(
            WhiteLabel.org_id == org_id,
            WhiteLabel.is_active == True,
        )
    )
    branding = result.scalar_one_or_none()
    if not branding or not branding.portal_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Portal not enabled")
    return branding


@router.get("/{org_slug}/campaigns")
async def portal_campaigns(
    org_slug: str,
    client_id: str | None = None,
    db=Depends(get_db),
):
    """Public campaign listing for client portal."""
    org = await _resolve_org(db, org_slug)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    branding = await _require_portal_branding(db, org.id)

    q = select(Campaign).where(Campaign.org_id == org.id)
    if client_id:
        q = q.where(Campaign.client_id == UUID(client_id))
    q = q.order_by(Campaign.created_at.desc()).limit(50)

    result = await db.execute(q)
    campaigns = result.scalars().all()

    return {
        "branding": {
            "company_name": branding.company_name,
            "logo_url": branding.logo_url,
            "primary_color": branding.primary_color,
        },
        "items": [
            {
                "id": str(c.id),
                "name": c.name,
                "status": c.status,
                "channels": c.channels,
                "start_date": str(c.start_date) if c.start_date else None,
                "end_date": str(c.end_date) if c.end_date else None,
            }
            for c in campaigns
        ],
    }


@router.get("/{org_slug}/content")
async def portal_content(
    org_slug: str,
    status_filter: str | None = None,
    db=Depends(get_db),
):
    """Public content listing for client portal with approve/reject."""
    org = await _resolve_org(db, org_slug)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    await _require_portal_branding(db, org.id)

    q = select(ContentPiece).where(ContentPiece.org_id == org.id)
    if status_filter:
        q = q.where(ContentPiece.status == status_filter)
    q = q.order_by(ContentPiece.created_at.desc()).limit(100)

    result = await db.execute(q)
    pieces = result.scalars().all()

    return {
        "items": [
            {
                "id": str(p.id),
                "platform": p.platform,
                "title": p.title,
                "body": p.body,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in pieces
        ],
    }


@router.patch("/{org_slug}/content/{content_id}")
async def portal_review_content(
    org_slug: str,
    content_id: UUID,
    body: dict,
    db=Depends(get_db),
):
    """Allow clients to approve/reject content via portal."""
    org = await _resolve_org(db, org_slug)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    await _require_portal_branding(db, org.id)

    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id, ContentPiece.org_id == org.id
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    decision = body.get("decision", "")
    if decision == "approve":
        piece.status = "approved"
    elif decision == "reject":
        piece.status = "rejected"
    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "decision must be 'approve' or 'reject'",
        )

    await db.commit()
    return {"status": piece.status, "content_id": str(content_id)}
