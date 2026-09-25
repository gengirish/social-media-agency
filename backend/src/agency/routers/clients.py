from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.schemas import (
    BrandProfileCreate,
    BrandProfileResponse,
    ClientCreate,
    ClientListResponse,
    ClientResponse,
    ClientUpdate,
)
from agency.models.tables import BrandProfile, Client, ContentPiece, PlatformAccount
from agency.services.brand_context import resolve_voice

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
    archived: bool = Query(False, description="List archived clients instead of active ones"),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    count_q = select(func.count(Client.id)).where(
        Client.org_id == org_id, Client.is_active.is_(not archived)
    )
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Client)
        .where(Client.org_id == org_id, Client.is_active.is_(not archived))
        .order_by(Client.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(q)
    clients = result.scalars().all()

    return ClientListResponse(items=clients, total=total, page=page, per_page=per_page)


@router.get("/overview")
async def clients_overview(
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Per active client: setup progress and queue counts, for the client switcher and Welcome.

    Real counts only — a client with nothing yet reports zeros, never a guess.
    Declared before ``/{client_id}`` so "overview" is not parsed as an id.
    """
    clients = list(
        (
            await db.execute(
                select(Client)
                .where(Client.org_id == org_id, Client.is_active.is_(True))
                .order_by(Client.created_at.desc())
            )
        ).scalars()
    )
    ids = [c.id for c in clients]
    profiled: set[Any] = set()
    accounts: dict[Any, int] = {}
    counts: dict[Any, dict[str, int]] = {}
    if ids:
        profiled = set(
            (
                await db.execute(
                    select(BrandProfile.client_id).where(
                        BrandProfile.org_id == org_id, BrandProfile.client_id.in_(ids)
                    )
                )
            ).scalars()
        )
        for cid, n in await db.execute(
            select(PlatformAccount.client_id, func.count(PlatformAccount.id))
            .where(
                PlatformAccount.org_id == org_id,
                PlatformAccount.client_id.in_(ids),
                PlatformAccount.status == "connected",
            )
            .group_by(PlatformAccount.client_id)
        ):
            accounts[cid] = int(n)
        for cid, st, n in await db.execute(
            select(ContentPiece.client_id, ContentPiece.status, func.count(ContentPiece.id))
            .where(ContentPiece.org_id == org_id, ContentPiece.client_id.in_(ids))
            .group_by(ContentPiece.client_id, ContentPiece.status)
        ):
            counts.setdefault(cid, {})[str(st)] = int(n)
    items = []
    for c in clients:
        by_status = counts.get(c.id, {})
        items.append(
            {
                "id": str(c.id),
                "brand_name": c.brand_name,
                "website_url": c.website_url,
                "has_brand_profile": c.id in profiled,
                "connected_accounts": accounts.get(c.id, 0),
                "total_posts": sum(by_status.values()),
                "pending": by_status.get("draft", 0),
                "approved": by_status.get("approved", 0),
                "scheduled": by_status.get("scheduled", 0),
                "published": by_status.get("published", 0),
                "failed": by_status.get("failed", 0),
                "campaign_focus": _campaign_focus(c),
            }
        )
    return {"items": items}


def _campaign_focus(client: Client) -> str | None:
    settings: Any = client.settings
    focus = settings.get("campaign_focus") if isinstance(settings, dict) else None
    desc = focus.get("description") if isinstance(focus, dict) else None
    return desc.strip() if isinstance(desc, str) and desc.strip() else None


class CampaignFocusRequest(BaseModel):
    description: str = Field(min_length=1, max_length=300)


@router.put("/{client_id}/campaign-focus")
async def set_campaign_focus(
    client_id: UUID,
    body: CampaignFocusRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Cadence's "Campaign": a short, human-typed statement of what is going on right now.

    Every generator reads it through ``brand_context.brand_prompt_block``. No AI
    involved — it is deliberately a plain statement the human owns and clears.
    """
    client = await _get_org_client(db, client_id, org_id)
    settings: Any = client.settings
    merged = dict(settings) if isinstance(settings, dict) else {}
    merged["campaign_focus"] = {
        "description": body.description.strip(),
        "set_at": datetime.now(UTC).isoformat(),
    }
    # Reassign (not mutate) so SQLAlchemy sees the JSONB change.
    client.settings = merged  # type: ignore[assignment]
    await db.commit()
    return {"campaign_focus": _campaign_focus(client)}


@router.delete("/{client_id}/campaign-focus")
async def clear_campaign_focus(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    client = await _get_org_client(db, client_id, org_id)
    settings: Any = client.settings
    merged = dict(settings) if isinstance(settings, dict) else {}
    merged.pop("campaign_focus", None)
    client.settings = merged  # type: ignore[assignment]
    await db.commit()
    return {"campaign_focus": None}


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


async def _get_org_client(db: AsyncSession, client_id: UUID, org_id: UUID) -> Client:
    result = await db.execute(
        select(Client).where(Client.id == client_id, Client.org_id == org_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return client


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: UUID,
    request: ClientUpdate,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> Client:
    client = await _get_org_client(db, client_id, org_id)
    updates = request.model_dump(exclude_unset=True)
    for required in ("brand_name", "industry"):
        if required in updates and updates[required] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{required} cannot be empty")
    for field, value in updates.items():
        setattr(client, field, value)
    await db.commit()
    await db.refresh(client)
    return client


@router.post("/{client_id}/archive", response_model=ClientResponse)
async def archive_client(
    client_id: UUID,
    unschedule: bool = Query(
        False, description="Move this client's scheduled posts back to approved first"
    ),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> Client:
    """Hide a client from lists and block new schedules/publishes for it.

    Soft delete: campaigns, posts and history are kept, and ``/restore`` undoes it.
    Scheduled posts would otherwise go live after the client was archived, so while any
    exist this is refused with 409 ``{"code": "has_scheduled_posts", "count": n}``
    unless ``unschedule=true``, which returns them to ``approved`` (still reviewed, but
    no longer queued) in the same transaction.
    """
    client = await _get_org_client(db, client_id, org_id)
    scheduled = (
        (
            await db.execute(
                select(ContentPiece).where(
                    ContentPiece.client_id == client_id,
                    ContentPiece.org_id == org_id,
                    ContentPiece.status == "scheduled",
                )
            )
        )
        .scalars()
        .all()
    )
    if scheduled and not unschedule:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"code": "has_scheduled_posts", "count": len(scheduled)}
        )
    for piece in scheduled:
        piece.status = "approved"  # type: ignore[assignment]
        piece.scheduled_at = None  # type: ignore[assignment]
    client.is_active = False  # type: ignore[assignment]
    await db.commit()
    await db.refresh(client)
    return client


@router.post("/{client_id}/restore", response_model=ClientResponse)
async def restore_client(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> Client:
    client = await _get_org_client(db, client_id, org_id)
    client.is_active = True  # type: ignore[assignment]
    await db.commit()
    await db.refresh(client)
    return client


def _with_effective_voice(profile: BrandProfile, client: Client) -> BrandProfileResponse:
    """The profile, plus the one resolved answer for "what is this client's voice?".

    Resolved here rather than in each screen, because doing it per screen is how
    one client came to show three different voices at once (CF-08).
    """
    settings: Any = client.settings
    prefs = (settings or {}).get("posting_prefs") if isinstance(settings, dict) else None
    voice, source = resolve_voice(
        profile.voice_description,
        profile.tone_attributes,
        prefs if isinstance(prefs, dict) else None,
    )
    response = BrandProfileResponse.model_validate(profile)
    response.effective_voice = voice
    response.voice_source = source
    return response


@router.get("/{client_id}/brand-profile", response_model=BrandProfileResponse)
async def get_brand_profile(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> BrandProfileResponse:
    client = await _get_org_client(db, client_id, org_id)
    result = await db.execute(
        select(BrandProfile).where(
            BrandProfile.client_id == client_id, BrandProfile.org_id == org_id
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand profile not found")
    return _with_effective_voice(profile, client)


@router.put("/{client_id}/brand-profile", response_model=BrandProfileResponse)
async def upsert_brand_profile(
    client_id: UUID,
    request: BrandProfileCreate,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> BrandProfileResponse:
    """Create the brand profile, or update only the fields sent if one exists."""
    client = await _get_org_client(db, client_id, org_id)
    result = await db.execute(
        select(BrandProfile).where(
            BrandProfile.client_id == client_id, BrandProfile.org_id == org_id
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = BrandProfile(client_id=client_id, org_id=org_id, **request.model_dump())
        db.add(profile)
    else:
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return _with_effective_voice(profile, client)


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
