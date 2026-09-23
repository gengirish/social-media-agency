"""Amplify — turn one source into up to 8 angle-distinct drafts.

Two-step on purpose: ``preview`` generates and saves nothing to
``content_piece``; ``commit`` writes only the atoms the human kept, and always
as ``status="draft"`` (Pending). Nothing here approves, schedules or publishes.

Tenancy: every client-supplied id (``client_id``, ``source_content_id``,
``pack_id``) is resolved against the caller's ``org_id`` before use — there is
no row-level security, so these filters are the isolation boundary.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents.amplify import generate_amplify_atoms
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import (
    Campaign,
    Client,
    ContentPiece,
    RepurposePack,
)
from agency.services import product_analytics as pa
from agency.services.brand_context import get_org_client, load_brand_context
from agency.services.generation_quota import charge_generation, require_generation_quota
from agency.services.repurpose import (
    MAX_ATOMS,
    PLATFORM_CHAR_LIMITS,
    is_angle_duplicate,
    plan_atoms,
    rendered_length,
    validate_atoms,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/amplify", tags=["Amplify"])

#: How many of the client's recent posts the duplicate check compares against.
RECENT_BODIES_FOR_DUPLICATE_CHECK = 50
MAX_SOURCE_TEXT = 20_000


class PreviewRequest(BaseModel):
    client_id: UUID
    source_content_id: UUID | None = None
    source_text: str | None = Field(default=None, max_length=MAX_SOURCE_TEXT)
    platforms: list[str] = Field(min_length=1)
    max_atoms: int = Field(default=MAX_ATOMS, ge=1, le=MAX_ATOMS)

    @model_validator(mode="after")
    def _one_source(self) -> PreviewRequest:
        has_text = bool(self.source_text and self.source_text.strip())
        if (self.source_content_id is None) == (not has_text):
            raise ValueError("Provide exactly one of source_content_id or source_text")
        unknown = [p for p in self.platforms if p not in PLATFORM_CHAR_LIMITS]
        if unknown:
            raise ValueError(
                f"Unsupported platforms {unknown}; supported: {sorted(PLATFORM_CHAR_LIMITS)}"
            )
        return self


class AtomIn(BaseModel):
    platform: str
    angle: str
    title: str = ""
    body: str
    hashtags: list[str] = Field(default_factory=list)


class CommitRequest(BaseModel):
    atoms: list[AtomIn] = Field(min_length=1, max_length=MAX_ATOMS)


def _as_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None


def _meta(piece: ContentPiece) -> dict[str, Any]:
    raw: Any = piece.metadata_
    return raw if isinstance(raw, dict) else {}


async def _campaign_brief(db: AsyncSession, campaign_id: Any, org_id: UUID) -> str | None:
    if not campaign_id:
        return None
    camp = (
        await db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.org_id == org_id)
        )
    ).scalar_one_or_none()
    if camp is None:
        return None
    parts = [f"Campaign: {camp.name}"]
    if camp.objective:
        parts.append(f"Objective: {camp.objective}")
    if camp.channels:
        parts.append(f"Channels: {', '.join(camp.channels)}")
    return "\n".join(parts)


@router.post("/preview")
async def preview(
    body: PreviewRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Generate a pack. Charges one generation; writes nothing to ``content_piece``."""
    client = await get_org_client(db, body.client_id, org_id)

    source: ContentPiece | None = None
    if body.source_content_id is not None:
        source = (
            await db.execute(
                select(ContentPiece).where(
                    ContentPiece.id == body.source_content_id,
                    ContentPiece.org_id == org_id,
                    ContentPiece.client_id == client.id,
                )
            )
        ).scalar_one_or_none()
        if source is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source content not found")
        source_text = "\n\n".join(
            str(t) for t in (source.title, source.body) if t and str(t).strip()
        )
        if not source_text.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Source content is empty")
    else:
        source_text = (body.source_text or "").strip()

    await require_generation_quota(db, org_id)

    # The client's recent posts: duplicate-check corpus, and — for posts that
    # came from this same source — the angles already used, which plan_atoms
    # pushes to the back so a repeat pack explores new ground first.
    recent = list(
        (
            await db.execute(
                select(ContentPiece)
                .where(ContentPiece.org_id == org_id, ContentPiece.client_id == client.id)
                .order_by(ContentPiece.created_at.desc())
                .limit(RECENT_BODIES_FOR_DUPLICATE_CHECK)
            )
        ).scalars()
    )
    source_key = str(source.id) if source is not None else None
    used_angles = [
        str(_meta(p).get("angle"))
        for p in recent
        if source_key and _meta(p).get("source_id") == source_key
    ]
    recent_bodies = [str(p.body or "") for p in recent if source is None or p.id != source.id]

    requests = plan_atoms(body.platforms, body.max_atoms, used_angles)
    try:
        result = await generate_amplify_atoms(
            source_text=source_text,
            requests=requests,
            brand=await load_brand_context(db, client, org_id),
            campaign_brief=await _campaign_brief(
                db, source.campaign_id if source is not None else None, org_id
            ),
        )
    except Exception as exc:
        logger.error("amplify_generation_failed", org_id=str(org_id), error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Generation failed; no quota was used. Try again."
        ) from None

    if not result.atoms:
        # Charging for an empty pack would bill the user for our failure.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The model returned no usable drafts; no quota was used. Try again.",
        )

    platforms = list(dict.fromkeys(body.platforms))
    pack = RepurposePack(
        org_id=org_id,
        client_id=client.id,
        source_content_id=source.id if source is not None else None,
        source_text=None if source is not None else source_text,
        platforms=platforms,
        atom_count=len(result.atoms),
        committed_count=0,
        created_by=_as_uuid(user.get("sub")),
    )
    db.add(pack)
    await charge_generation(db, org_id)
    await db.flush()
    await pa.track(
        db,
        name=pa.AMPLIFY_PACK_GENERATED,
        org_id=org_id,
        user_id=user.get("sub"),
        campaign_id=source.campaign_id if source is not None else None,
        properties={
            "pack_id": str(pack.id),
            "requested": len(requests),
            "atoms": len(result.atoms),
            "dropped": len(result.dropped),
            "platforms": platforms,
            "source": "content" if source is not None else "text",
        },
    )
    await db.commit()

    atoms_out: list[dict[str, Any]] = []
    prior_in_pack: list[str] = []
    for atom in result.atoms:
        atoms_out.append(
            {
                **atom,
                "char_count": rendered_length(atom["body"], atom["hashtags"]),
                "char_limit": PLATFORM_CHAR_LIMITS[atom["platform"]],
                # Against the client's recent posts AND the atoms before it in
                # this pack. Warn, never block — the human decides.
                "duplicate_warning": is_angle_duplicate(
                    atom["body"], [*recent_bodies, *prior_in_pack]
                ),
            }
        )
        prior_in_pack.append(atom["body"])

    return {
        "pack_id": str(pack.id),
        "atoms": atoms_out,
        "requested": len(requests),
        "dropped": len(result.dropped),
    }


@router.post("/{pack_id}/commit")
async def commit(
    pack_id: UUID,
    body: CommitRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Write the kept atoms as Pending drafts. Never approved, never scheduled."""
    pack = (
        await db.execute(
            select(RepurposePack).where(
                RepurposePack.id == pack_id, RepurposePack.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if pack is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pack not found")
    if (pack.committed_count or 0) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "This pack was already added to the queue")

    checked = validate_atoms(
        [a.model_dump() for a in body.atoms], list(pack.platforms or []), MAX_ATOMS
    )
    if checked.dropped:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"code": "invalid_atoms", "errors": checked.dropped},
        )

    source: ContentPiece | None = None
    if pack.source_content_id is not None:
        source = (
            await db.execute(
                select(ContentPiece).where(
                    ContentPiece.id == pack.source_content_id, ContentPiece.org_id == org_id
                )
            )
        ).scalar_one_or_none()

    created: list[ContentPiece] = []
    for atom in checked.kept:
        piece = ContentPiece(
            org_id=org_id,
            client_id=pack.client_id,
            campaign_id=source.campaign_id if source is not None else None,
            content_type="social_post",
            platform=atom["platform"],
            title=atom["title"],
            body=atom["body"],
            hashtags=atom["hashtags"],
            metadata_={
                "amplify_pack_id": str(pack.id),
                "source_id": str(pack.source_content_id) if pack.source_content_id else None,
                "angle": atom["angle"],
            },
            media_urls=[],
            ai_generated=True,
            # Pending. Hard-coded, never taken from the request: an Amplify pack
            # is eight posts at once, so a bypass here would be eight times worse.
            status="draft",
            scheduled_at=None,
        )
        db.add(piece)
        created.append(piece)

    # Legacy Column-typed model (no Mapped[]): mypy sees Column[int] here.
    pack.committed_count = len(created)  # type: ignore[assignment]
    await db.flush()
    await pa.track(
        db,
        name=pa.AMPLIFY_PACK_COMMITTED,
        org_id=org_id,
        user_id=user.get("sub"),
        campaign_id=source.campaign_id if source is not None else None,
        properties={
            "pack_id": str(pack.id),
            "committed": len(created),
            "generated": pack.atom_count,
            "angles": [a["angle"] for a in checked.kept],
        },
    )
    await db.commit()
    return {"created": [str(p.id) for p in created], "count": len(created)}


@router.get("/packs")
async def list_packs(
    client_id: UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Recent packs for the caller's org, newest first."""
    q = (
        select(RepurposePack, ContentPiece.title, Client.brand_name)
        .outerjoin(
            ContentPiece,
            (ContentPiece.id == RepurposePack.source_content_id)
            & (ContentPiece.org_id == org_id),
        )
        .outerjoin(Client, (Client.id == RepurposePack.client_id) & (Client.org_id == org_id))
        .where(RepurposePack.org_id == org_id)
    )
    if client_id is not None:
        q = q.where(RepurposePack.client_id == client_id)
    rows = (await db.execute(q.order_by(RepurposePack.created_at.desc()).limit(limit))).all()

    items = []
    for pack, source_title, brand_name in rows:
        excerpt = (pack.source_text or "").strip().replace("\n", " ")
        items.append(
            {
                "id": str(pack.id),
                "client_id": str(pack.client_id),
                "client_name": brand_name,
                "source_content_id": str(pack.source_content_id)
                if pack.source_content_id
                else None,
                "source_title": source_title,
                "source_excerpt": excerpt[:140] if excerpt else None,
                "platforms": pack.platforms or [],
                "atom_count": pack.atom_count,
                "committed_count": pack.committed_count,
                "created_at": pack.created_at.isoformat() if pack.created_at else None,
            }
        )
    return {"items": items}
