import uuid as uuid_module
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.schemas import ContentPieceResponse, ContentUpdateRequest
from agency.models.tables import Client, ContentPiece
from agency.services.webhook_dispatcher import EVENT_CONTENT_APPROVED, dispatch_webhook

logger = structlog.get_logger()

#: Per-platform repurposing guidance. Module scope so it is built once, not
#: rebuilt on every repurpose request.
PLATFORM_GUIDELINES = {
    "twitter": "Max 280 chars. Conversational, punchy. Use 1-3 hashtags. Thread-friendly.",
    "linkedin": "Professional tone. 1300 char sweet spot. Use line breaks for readability.",
    "instagram": "Visual-first caption. Storytelling. 5-10 relevant hashtags at end.",
    "facebook": "Conversational, community-oriented. Questions drive engagement.",
    "tiktok": "Gen-Z friendly. Hook in first line. Trending sounds/hashtags.",
}

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


@router.get("/suggestions")
async def content_suggestions(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Suggest top-performing content for recycling.

    Only ranks pieces that actually carry a ``performance_score``. The previous
    version ordered by ``.nulls_last()`` with no filter, so unscored posts came
    back labelled "Top performing content" purely because they were published.
    Nothing in the product writes ``performance_score`` yet, so this legitimately
    returns an empty list with an explicit reason.
    """
    result = await db.execute(
        select(ContentPiece)
        .where(
            ContentPiece.org_id == org_id,
            ContentPiece.status == "published",
            ContentPiece.performance_score.isnot(None),
        )
        .order_by(ContentPiece.performance_score.desc())
        .limit(10)
    )
    pieces = result.scalars().all()

    suggestions = []
    for p in pieces:
        suggestions.append(
            {
                "original_id": str(p.id),
                "platform": p.platform,
                "title": p.title,
                "body": p.body[:200] + ("..." if len(p.body) > 200 else ""),
                "performance_score": p.performance_score,
                "reason": "Top performing content — consider reposting or refreshing",
            }
        )

    if not suggestions:
        return {
            "items": [],
            "status": "unavailable",
            "reason": (
                "No content has a measured performance score yet, so there is "
                "nothing to rank. Scores are not produced by the pipeline today."
            ),
        }

    return {"items": suggestions, "status": "available"}


@router.post("/video-script")
async def create_video_script(
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Generate a video/podcast script."""
    format_type = body.get("format", "youtube")
    topic = body.get("topic", "")
    client_id = body.get("client_id")

    if not topic:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "topic required")

    # Do not silently substitute a hardcoded brand. The old default was
    # {"brand_name": "CampaignForge", "industry": "Marketing"}, so a caller with a
    # bad client_id got a script written for the wrong company with no signal.
    if not client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "client_id required")

    result = await db.execute(
        select(Client).where(Client.id == UUID(str(client_id)), Client.org_id == org_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    brand_context = {
        "brand_name": client.brand_name,
        "industry": client.industry or "",
    }

    from agency.agents.video_script import generate_script

    script = await generate_script(
        format_type,
        topic,
        brand_context,
        body.get("target_audience", ""),
    )
    return script


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


@router.get("/{content_id}/analytics")
async def get_analytics(
    content_id: UUID,
    refresh: bool = Query(True, description="Attempt a live platform fetch first"),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Analytics for a content piece, with an explicit availability status.

    Metric values are ``null`` when the platform does not expose them — that is
    distinct from a measured ``0``. ``status`` is one of ``ok`` (fresh metrics
    recorded), ``skipped`` (already measured today), ``unavailable`` (with a
    ``reason``; nothing was persisted), ``error``, or ``not_refreshed``.
    """
    from agency.services.analytics_fetcher import fetch_content_metrics, get_content_analytics

    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id, ContentPiece.org_id == org_id
        )
    )
    piece = result.scalar_one_or_none()
    if piece is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    live: dict[str, Any] = {"status": "not_refreshed", "reason": None}
    if refresh and piece.status == "published":
        live = await fetch_content_metrics(db, content_id, skip_if_fetched_today=True)
        await db.commit()

    items = await get_content_analytics(db, content_id)
    return {
        "content_id": str(content_id),
        "platform": piece.platform,
        "status": live.get("status"),
        "reason": live.get("reason"),
        "latest": items[0] if items else None,
        "items": items,
    }


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


@router.post("/{content_id}/repurpose")
async def repurpose_content(
    content_id: UUID,
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Repurpose a content piece for other platforms."""
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id, ContentPiece.org_id == org_id
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    target_platforms = body.get("target_platforms", [])
    if not target_platforms:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "target_platforms required")

    from agency.agents.utils import parse_llm_json
    from agency.services.llm_provider import get_lite_llm

    wanted = [p for p in target_platforms if p != piece.platform]
    if not wanted:
        return {"status": "repurposed", "platforms": [], "count": 0, "skipped": []}

    # One call for every platform, not one call each. The content writer agent
    # already generates a whole batch per call; adapting one post to N platforms
    # is strictly easier, and N round trips cost N times as much for no gain.
    guideline_lines = "\n".join(
        f"- {p}: {PLATFORM_GUIDELINES.get(p, 'Adapt naturally for this platform.')}"
        for p in wanted
    )
    prompt = f"""Repurpose this content for each target platform.

Original ({piece.platform}):
{piece.body}

Target platforms and their guidelines:
{guideline_lines}

Return ONLY a JSON array with one object per target platform, in the order
listed above. Every object must carry the platform name it belongs to:
[{{"platform": "<name>", "title": "...", "body": "...", "hashtags": ["..."]}}]"""

    llm = get_lite_llm()
    response = await llm.ainvoke(prompt)
    raw = response.content if hasattr(response, "content") else str(response)
    parsed = parse_llm_json(raw if isinstance(raw, str) else str(raw))

    by_platform: dict[str, dict] = {}
    if isinstance(parsed, list):
        for entry in parsed:
            if isinstance(entry, dict) and entry.get("platform") in wanted:
                by_platform[str(entry["platform"])] = entry

    created: list[str] = []
    for platform in wanted:
        data = by_platform.get(platform)
        # A platform the model omitted or returned unusably is skipped rather
        # than written as an empty draft — a blank post is worse than no post.
        if not data or not str(data.get("body") or "").strip():
            continue
        db.add(
            ContentPiece(
                campaign_id=piece.campaign_id,
                client_id=piece.client_id,
                org_id=org_id,
                content_type=piece.content_type,
                platform=platform,
                title=data.get("title") or piece.title,
                body=data["body"],
                hashtags=data.get("hashtags") or [],
                metadata_={"repurposed_from": str(content_id)},
                ai_generated=True,
                status="draft",
            )
        )
        created.append(platform)

    await db.commit()
    skipped = [p for p in wanted if p not in created]
    if skipped:
        logger.warning(
            "repurpose_incomplete", content_id=str(content_id), skipped=skipped
        )
    return {
        "status": "repurposed",
        "platforms": created,
        "count": len(created),
        "skipped": skipped,
    }


@router.post("/{content_id}/variants")
async def generate_variants(
    content_id: UUID,
    body: dict | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Generate A/B variants of a content piece."""
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id, ContentPiece.org_id == org_id
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    num_variants = (body or {}).get("count", 2)
    if not isinstance(num_variants, int) or num_variants < 1:
        num_variants = 2
    variant_group = str(uuid_module.uuid4())

    piece.metadata_ = {
        **(piece.metadata_ or {}),
        "variant_group": variant_group,
        "variant_label": "A",
    }
    await db.flush()

    from agency.agents.utils import parse_llm_json
    from agency.services.llm_provider import get_lite_llm

    labels = ["B", "C", "D", "E"][: min(num_variants, 4)]

    # One call for all variants. Besides costing a quarter as much at four
    # variants, it is the only way the model can see the other variants while
    # writing each one — independent calls have no way to avoid converging on
    # near-duplicates, which defeats the point of an A/B test.
    prompt = f"""Create {len(labels)} distinct variants of this {piece.platform} post.

Original:
{piece.body}

Every variant keeps the original intent but differs from the original AND from
the other variants on at least one of: tone, CTA, hook, structure, or angle.
Label them {", ".join(labels)}.

Return ONLY a JSON array with one object per variant, in label order:
[{{"label": "<label>", "title": "...", "body": "...", "hashtags": ["..."]}}]"""

    llm = get_lite_llm()
    response = await llm.ainvoke(prompt)
    raw = response.content if hasattr(response, "content") else str(response)
    parsed = parse_llm_json(raw if isinstance(raw, str) else str(raw))

    by_label: dict[str, dict] = {}
    if isinstance(parsed, list):
        for entry in parsed:
            if isinstance(entry, dict) and entry.get("label") in labels:
                by_label[str(entry["label"])] = entry

    created: list[str] = []
    for label in labels:
        data = by_label.get(label)
        if not data or not str(data.get("body") or "").strip():
            continue
        db.add(
            ContentPiece(
                campaign_id=piece.campaign_id,
                client_id=piece.client_id,
                org_id=org_id,
                content_type=piece.content_type,
                platform=piece.platform,
                title=data.get("title") or piece.title,
                body=data["body"],
                hashtags=data.get("hashtags") or piece.hashtags,
                metadata_={"variant_group": variant_group, "variant_label": label},
                ai_generated=True,
                status="draft",
            )
        )
        created.append(label)

    await db.commit()
    missing = [label for label in labels if label not in created]
    if missing:
        logger.warning(
            "variants_incomplete", content_id=str(content_id), missing=missing
        )
    return {
        "status": "variants_created",
        "variant_group": variant_group,
        "variants": created,
        "missing": missing,
    }


@router.post("/{content_id}/approve")
async def approve_content(
    content_id: UUID,
    background: BackgroundTasks,
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

    # After the response: retries + backoff must not sit in the request path.
    background.add_task(
        dispatch_webhook,
        org_id,
        EVENT_CONTENT_APPROVED,
        {
            "content_id": str(content_id),
            "campaign_id": str(piece.campaign_id) if piece.campaign_id else None,
            "client_id": str(piece.client_id),
            "platform": piece.platform,
        },
    )
    return {"status": "approved", "content_id": str(content_id)}


@router.post("/{content_id}/generate-image")
async def generate_image(
    content_id: UUID,
    body: dict | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Generate a social media image for a content piece."""
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id, ContentPiece.org_id == org_id
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    from agency.services.image_generation import generate_social_image

    body = body or {}
    snippet = (piece.body or "")[:100]
    prompt = body.get("prompt", piece.title or snippet)
    style = body.get("style", "professional")

    result_img = await generate_social_image(prompt, piece.platform, style)

    if result_img.get("image_url"):
        media = list(piece.media_urls or [])
        media.append(result_img["image_url"])
        piece.media_urls = media
        await db.commit()

    return result_img
