"""Integrations router — API keys, white-label, webhooks, templates."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import CampaignTemplate
from agency.services.api_keys import create_api_key, list_api_keys, revoke_api_key
from agency.services.white_label import get_white_label, upsert_white_label

router = APIRouter(prefix="/integrations", tags=["Integrations"])


# --- API Keys ---


@router.post("/api-keys")
async def create_key(
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    name = body.get("name", "Default Key")
    permissions = body.get("permissions", ["read"])
    result = await create_api_key(db, org_id, name, permissions)
    return result


@router.get("/api-keys")
async def list_keys(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    return {"items": await list_api_keys(db, org_id)}


@router.delete("/api-keys/{key_id}")
async def revoke_key(
    key_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await revoke_api_key(db, org_id, key_id)
    if "error" in result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, result["error"])
    return result


# --- White Label ---


@router.get("/white-label")
async def get_branding(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    wl = await get_white_label(db, org_id)
    return wl or {"is_active": False}


@router.put("/white-label")
async def update_branding(
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    return await upsert_white_label(db, org_id, body)


# --- Campaign Templates ---


@router.get("/templates")
async def list_templates(
    category: str | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    q = select(CampaignTemplate).where(
        (CampaignTemplate.is_public == True) | (CampaignTemplate.org_id == org_id)
    )
    if category:
        q = q.where(CampaignTemplate.category == category)
    q = q.order_by(CampaignTemplate.uses_count.desc())

    result = await db.execute(q)
    templates = result.scalars().all()

    return {
        "items": [
            {
                "id": str(t.id),
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "objective_template": t.objective_template,
                "channels": t.channels,
                "uses_count": t.uses_count,
                "is_public": t.is_public,
            }
            for t in templates
        ]
    }


@router.post("/templates")
async def create_template(
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    template = CampaignTemplate(
        org_id=org_id,
        name=body.get("name", "Untitled"),
        description=body.get("description", ""),
        category=body.get("category", "general"),
        objective_template=body.get("objective_template", ""),
        channels=body.get("channels", []),
        content_directives=body.get("content_directives", {}),
        is_public=False,
    )
    db.add(template)
    await db.commit()
    return {"status": "created", "id": str(template.id)}
