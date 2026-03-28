"""Integrations router — API keys, white-label, webhooks, templates."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
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


# --- Organization Settings ---


@router.get("/settings")
async def get_settings_endpoint(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    from agency.models.tables import Organization

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return {
        "name": org.name,
        "domain": org.domain,
        "settings": org.settings or {},
    }


@router.patch("/settings")
async def update_settings_endpoint(
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    from agency.models.tables import Organization

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if "name" in body:
        org.name = body["name"]
    if "domain" in body:
        org.domain = body["domain"]
    if "settings" in body:
        merged = {**(org.settings or {}), **body["settings"]}
        org.settings = merged
    await db.commit()
    return {
        "status": "updated",
        "name": org.name,
        "domain": org.domain,
        "settings": org.settings,
    }


@router.get("/platform-accounts")
async def list_platform_accounts(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    from agency.models.tables import PlatformAccount

    result = await db.execute(
        select(PlatformAccount).where(PlatformAccount.org_id == org_id)
    )
    accounts = result.scalars().all()
    return {
        "items": [
            {
                "id": str(a.id),
                "platform": a.platform,
                "account_handle": a.account_handle,
                "display_name": a.display_name,
                "status": a.status,
                "followers_count": a.followers_count,
            }
            for a in accounts
        ]
    }


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
    return {"status": "created", "id": str(template.id)    }


@router.get("/templates/marketplace")
async def list_marketplace_templates(
    category: str | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """List all public templates in the marketplace."""
    q = select(CampaignTemplate).where(CampaignTemplate.is_public == True)
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
                "channels": t.channels,
                "uses_count": t.uses_count,
            }
            for t in templates
        ]
    }


@router.post("/templates/{template_id}/fork")
async def fork_template(
    template_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Clone a public template to your organization."""
    result = await db.execute(
        select(CampaignTemplate).where(
            CampaignTemplate.id == template_id,
            CampaignTemplate.is_public == True,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")

    clone = CampaignTemplate(
        org_id=org_id,
        name=f"{source.name} (copy)",
        description=source.description,
        category=source.category,
        objective_template=source.objective_template,
        channels=source.channels,
        content_directives=source.content_directives,
        is_public=False,
    )
    db.add(clone)
    source.uses_count = (source.uses_count or 0) + 1
    await db.commit()
    return {"status": "forked", "id": str(clone.id)}


@router.post("/templates/{template_id}/publish")
async def publish_template(
    template_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Make an org template public on the marketplace."""
    result = await db.execute(
        select(CampaignTemplate).where(
            CampaignTemplate.id == template_id,
            CampaignTemplate.org_id == org_id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")

    template.is_public = True
    await db.commit()
    return {"status": "published", "id": str(template.id)}


@router.get("/templates/{template_id}")
async def get_template(
    template_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(CampaignTemplate).where(
            CampaignTemplate.id == template_id,
            (CampaignTemplate.is_public == True) | (CampaignTemplate.org_id == org_id),
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    return {
        "id": str(t.id),
        "name": t.name,
        "description": t.description,
        "category": t.category,
        "objective_template": t.objective_template,
        "channels": t.channels,
        "content_directives": t.content_directives,
        "uses_count": t.uses_count,
        "is_public": t.is_public,
    }


@router.post("/templates/{template_id}/launch")
async def launch_template(
    template_id: UUID,
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(CampaignTemplate).where(CampaignTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")

    template.uses_count = (template.uses_count or 0) + 1
    await db.commit()

    return {
        "status": "ready",
        "prefill": {
            "campaign_name": template.name,
            "objective": template.objective_template,
            "channels": template.channels,
            "content_directives": template.content_directives,
        },
    }
