from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.schemas import (
    BrandProfileCreate,
    ClientCreate,
    ClientListResponse,
    ClientResponse,
)
from agency.models.tables import BrandProfile, Client

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    request: ClientCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    client = Client(
        org_id=org_id,
        brand_name=request.brand_name,
        industry=request.industry,
        description=request.description,
        website_url=request.website_url,
        contact_email=request.contact_email,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return client


@router.get("", response_model=ClientListResponse)
async def list_clients(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    count_q = select(func.count(Client.id)).where(Client.org_id == org_id, Client.is_active == True)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Client)
        .where(Client.org_id == org_id, Client.is_active == True)
        .order_by(Client.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(q)
    clients = result.scalars().all()

    return ClientListResponse(items=clients, total=total, page=page, per_page=per_page)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.org_id == org_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return client


@router.post("/{client_id}/brand-profile", status_code=status.HTTP_201_CREATED)
async def create_brand_profile(
    client_id: UUID,
    request: BrandProfileCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.org_id == org_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    profile = BrandProfile(
        client_id=client_id,
        org_id=org_id,
        **request.model_dump(),
    )
    db.add(profile)
    await db.commit()
    return {"status": "created", "client_id": str(client_id)}
