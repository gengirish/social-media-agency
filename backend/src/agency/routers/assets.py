"""Generic read/rename/delete for creative assets (the Create screens' saved output).

Generation lives in each feature's own router; this one only manages what was
kept. Every id from the client is resolved against ``org_id`` first.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import CreativeAsset
from agency.services.brand_context import get_org_client
from agency.services.creative_assets import (
    MAX_TITLE,
    asset_out,
    get_org_asset,
    validate_kind,
)

router = APIRouter(prefix="/assets", tags=["Creative assets"])


class AssetUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_TITLE)
    payload: dict[str, Any] | None = None


@router.get("")
async def list_assets(
    client_id: UUID,
    kind: list[str] | None = Query(None, description="Repeat to include several kinds"),
    q: str | None = Query(None, max_length=200, description="Case-insensitive title search"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    await get_org_client(db, client_id, org_id)
    where = [CreativeAsset.org_id == org_id, CreativeAsset.client_id == client_id]
    if kind:
        where.append(CreativeAsset.kind.in_([validate_kind(k) for k in kind]))
    if q and q.strip():
        where.append(CreativeAsset.title.ilike(f"%{q.strip()}%"))
    total = (await db.execute(select(func.count(CreativeAsset.id)).where(*where))).scalar() or 0
    rows = (
        await db.execute(
            select(CreativeAsset)
            .where(*where)
            .order_by(CreativeAsset.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars()
    return {"items": [asset_out(a) for a in rows], "total": total}


@router.get("/{asset_id}")
async def get_asset(
    asset_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    return asset_out(await get_org_asset(db, asset_id, org_id))


@router.patch("/{asset_id}")
async def update_asset(
    asset_id: UUID,
    body: AssetUpdate,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    asset = await get_org_asset(db, asset_id, org_id)
    if body.title is not None:
        asset.title = body.title  # type: ignore[assignment]
    if body.payload is not None:
        asset.payload = body.payload  # type: ignore[assignment]
    await db.commit()
    await db.refresh(asset)
    return asset_out(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> Response:
    asset = await get_org_asset(db, asset_id, org_id)
    await db.delete(asset)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
