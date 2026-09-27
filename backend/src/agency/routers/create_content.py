"""Create › Content — blog post, comparison page, niche scan, video script, AI-SEO.

Every generate endpoint follows the same contract (Cadence's ContentScreen):
resolve the client against the caller's org, require a brand profile, check
quota, call the model, validate the shape in code, save one ``creative_asset``,
then charge one generation. A failed or malformed generation is a 502 that
saves nothing and charges nothing. Listing, reading and deleting the saved
items goes through the generic ``/assets`` router.

None of this output enters the post queue: a blog post, comparison page, scan
or video script has no platform and no publish path, so it is copied or
exported, not scheduled. Amplify is the route from here into the queue.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents import create_content as agent
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import BrandProfile, Client, CreativeAsset
from agency.services.brand_context import get_org_client, load_brand_context
from agency.services.competitor_research import research_competitors, sources_note
from agency.services.create_content import (
    MAX_NAME_CHARS,
    MAX_SCAN_COMPETITORS,
    MIN_SCAN_COMPETITORS,
    MalformedGenerationError,
    clean_competitor_names,
    used_keywords,
    validate_ai_seo_pack,
    validate_blog,
    validate_comparison,
    validate_niche_scan,
    validate_video_script,
)
from agency.services.creative_assets import asset_out, get_org_asset, save_asset
from agency.services.generation_quota import charge_generation, require_generation_quota

logger = structlog.get_logger()

router = APIRouter(prefix="/create/content", tags=["Create content"])

#: Earlier blog posts read for keyword memory.
KEYWORD_MEMORY_LIMIT = 100

GENERATION_FAILED = "Generation failed; no quota was used. Try again."
MALFORMED = "The model returned an unusable draft; no quota was used. Try again."


class ClientRequest(BaseModel):
    client_id: UUID


class ComparisonRequest(ClientRequest):
    competitor_name: str = Field(min_length=1, max_length=MAX_NAME_CHARS)


class NicheScanRequest(ClientRequest):
    competitor_names: list[str] = Field(min_length=1, max_length=20)


async def _require_brand_profile(db: AsyncSession, client: Client, org_id: UUID) -> None:
    """Cadence gates every Content generator on an approved profile; ours is a brand profile."""
    exists = (
        await db.execute(
            select(BrandProfile.id).where(
                BrandProfile.client_id == client.id, BrandProfile.org_id == org_id
            )
        )
    ).first()
    if exists is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "brand_profile_required",
                "message": "Set up this client's brand profile before generating content.",
            },
        )


async def _prepare(
    db: AsyncSession, client_id: UUID, org_id: UUID
) -> tuple[Client, dict[str, Any]]:
    client = await get_org_client(db, client_id, org_id)
    await _require_brand_profile(db, client, org_id)
    return client, await load_brand_context(db, client, org_id)


async def _run(
    call: Callable[[], Awaitable[Any]],
    validate: Callable[[Any], dict[str, Any]],
    *,
    kind: str,
    org_id: UUID,
) -> dict[str, Any]:
    """Call the model and validate the reply; any failure is a 502 with nothing charged."""
    try:
        raw = await call()
    except Exception as exc:
        logger.error(
            "create_content_generation_failed", kind=kind, org_id=str(org_id), error=str(exc)
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, GENERATION_FAILED) from None
    try:
        return validate(raw)
    except MalformedGenerationError as exc:
        logger.warning("create_content_malformed", kind=kind, org_id=str(org_id), error=str(exc))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, MALFORMED) from None


async def _save_and_charge(
    db: AsyncSession,
    *,
    org_id: UUID,
    client: Client,
    kind: str,
    title: str,
    payload: dict[str, Any],
    user: dict[str, Any],
    source_asset_id: UUID | None = None,
) -> dict[str, Any]:
    asset = await save_asset(
        db,
        org_id=org_id,
        client_id=client.id,  # type: ignore[arg-type]
        kind=kind,
        title=title,
        payload=payload,
        created_by=user.get("sub"),
        source_asset_id=source_asset_id,
    )
    await charge_generation(db, org_id)
    await db.commit()
    await db.refresh(asset)
    return asset_out(asset)


async def _used_keywords(db: AsyncSession, client: Client, org_id: UUID) -> list[str]:
    rows = (
        await db.execute(
            select(CreativeAsset.payload)
            .where(
                CreativeAsset.org_id == org_id,
                CreativeAsset.client_id == client.id,
                CreativeAsset.kind == "blog_post",
            )
            .order_by(CreativeAsset.created_at.desc())
            .limit(KEYWORD_MEMORY_LIMIT)
        )
    ).scalars()
    return used_keywords([p for p in rows if isinstance(p, dict)])


async def _blog(
    db: AsyncSession,
    *,
    client: Client,
    brand: dict[str, Any],
    org_id: UUID,
    user: dict[str, Any],
    gap: str | None = None,
    source_asset_id: UUID | None = None,
) -> dict[str, Any]:
    await require_generation_quota(db, org_id)
    used = await _used_keywords(db, client, org_id)
    blog = await _run(
        lambda: agent.generate_blog_post(brand, used, gap),
        lambda raw: validate_blog(raw, used),
        kind="blog_post",
        org_id=org_id,
    )
    if gap:
        blog["fromGap"] = gap
    return await _save_and_charge(
        db,
        org_id=org_id,
        client=client,
        kind="blog_post",
        title=blog["title"],
        payload=blog,
        user=user,
        source_asset_id=source_asset_id,
    )


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------
@router.post("/blog")
async def generate_blog(
    body: ClientRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """A blog draft targeting one keyword this client has not targeted before."""
    client, brand = await _prepare(db, body.client_id, org_id)
    return await _blog(db, client=client, brand=brand, org_id=org_id, user=user)


@router.post("/comparison")
async def generate_comparison(
    body: ComparisonRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """A fair "us vs <named competitor>" page. The human always names the competitor."""
    names = clean_competitor_names([body.competitor_name])
    if not names:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Name a competitor")
    competitor = names[0]
    client, brand = await _prepare(db, body.client_id, org_id)
    await require_generation_quota(db, org_id)
    research = await research_competitors([competitor], str(brand.get("industry") or ""))
    page = await _run(
        lambda: agent.generate_comparison_page(brand, competitor, research["sources"]),
        validate_comparison,
        kind="comparison_page",
        org_id=org_id,
    )
    payload = {
        "competitorName": competitor,
        **page,
        "sourcesNote": sources_note(research, ""),
        "webResearch": _research_record(research),
    }
    return await _save_and_charge(
        db,
        org_id=org_id,
        client=client,
        kind="comparison_page",
        title=page["title"],
        payload=payload,
        user=user,
    )


@router.post("/niche-scan")
async def generate_niche_scan(
    body: NicheScanRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Angles across 2-5 named competitors, their saturation, and one gap."""
    names = clean_competitor_names(body.competitor_names)
    if not MIN_SCAN_COMPETITORS <= len(names) <= MAX_SCAN_COMPETITORS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Name {MIN_SCAN_COMPETITORS}-{MAX_SCAN_COMPETITORS} different competitors",
        )
    client, brand = await _prepare(db, body.client_id, org_id)
    await require_generation_quota(db, org_id)
    research = await research_competitors(names, str(brand.get("industry") or ""))
    scan = await _run(
        lambda: agent.generate_niche_scan(brand, names, research["sources"]),
        lambda raw: validate_niche_scan(raw, names),
        kind="niche_scan",
        org_id=org_id,
    )
    payload = {
        "competitorNames": names,
        "scannedAt": datetime.now(UTC).isoformat(),
        **scan,
        # Provenance is stamped in code: the model's own note is kept, but it
        # can never claim live research that did not happen.
        "sourcesNote": sources_note(research, scan["sourcesNote"]),
        "webResearch": _research_record(research),
    }
    return await _save_and_charge(
        db,
        org_id=org_id,
        client=client,
        kind="niche_scan",
        title=f"vs {', '.join(names)}",
        payload=payload,
        user=user,
    )


@router.post("/video-script")
async def generate_video_script(
    body: ClientRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """A shootable short-form script. A script, not a video: nothing is rendered."""
    client, brand = await _prepare(db, body.client_id, org_id)
    await require_generation_quota(db, org_id)
    script = await _run(
        lambda: agent.generate_video_script(brand),
        validate_video_script,
        kind="video_script",
        org_id=org_id,
    )
    return await _save_and_charge(
        db,
        org_id=org_id,
        client=client,
        kind="video_script",
        title=script["hook"],
        payload=script,
        user=user,
    )


@router.post("/niche-scan/{asset_id}/blog")
async def generate_blog_from_gap(
    asset_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Turn a niche scan's gap into a blog draft (saved as a new blog_post asset)."""
    scan = await get_org_asset(db, asset_id, org_id)
    if scan.kind != "niche_scan":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Not a niche scan")
    payload: Any = scan.payload
    gap = payload.get("gapRecommendation") if isinstance(payload, dict) else None
    if not isinstance(gap, str) or not gap.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "This scan has no gap to write from"
        )
    client, brand = await _prepare(db, scan.client_id, org_id)  # type: ignore[arg-type]
    return await _blog(
        db,
        client=client,
        brand=brand,
        org_id=org_id,
        user=user,
        gap=gap.strip(),
        source_asset_id=scan.id,  # type: ignore[arg-type]
    )


@router.post("/blog/{asset_id}/ai-seo")
async def optimize_for_ai_search(
    asset_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Attach an ``aiSeoPack`` to an existing blog post. Merges; never replaces the draft."""
    asset = await get_org_asset(db, asset_id, org_id)
    if asset.kind != "blog_post":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Not a blog post")
    current: Any = asset.payload
    blog = dict(current) if isinstance(current, dict) else {}
    if blog.get("aiSeoPack"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "already_optimized", "message": "This post already has an AI-search pack."},
        )
    if not str(blog.get("body") or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This post has no draft body")
    client, brand = await _prepare(db, asset.client_id, org_id)  # type: ignore[arg-type]
    await require_generation_quota(db, org_id)
    pack = await _run(
        lambda: agent.generate_ai_seo_pack(brand, blog),
        validate_ai_seo_pack,
        kind="ai_seo",
        org_id=org_id,
    )
    # Reassign a new dict: JSONB columns do not track in-place mutation.
    asset.payload = {**blog, "aiSeoPack": pack}  # type: ignore[assignment]
    await charge_generation(db, org_id)
    await db.commit()
    await db.refresh(asset)
    return asset_out(asset)


def _research_record(research: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": research["status"],
        "reason": research.get("reason"),
        "retrievedAt": research.get("retrievedAt"),
        "sources": research.get("public") or [],
    }
