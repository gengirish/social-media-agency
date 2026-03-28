import json
import uuid as uuid_module
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.schemas import ContentPieceResponse, ContentUpdateRequest
from agency.models.tables import Client, ContentPiece

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
    """Suggest top-performing content for recycling."""
    result = await db.execute(
        select(ContentPiece)
        .where(
            ContentPiece.org_id == org_id,
            ContentPiece.status == "published",
        )
        .order_by(ContentPiece.performance_score.desc().nulls_last())
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

    return {"items": suggestions}


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

    brand_context = {"brand_name": "CampaignForge", "industry": "Marketing"}
    if client_id:
        result = await db.execute(
            select(Client).where(
                Client.id == UUID(str(client_id)), Client.org_id == org_id
            )
        )
        client = result.scalar_one_or_none()
        if client:
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
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Get analytics for a content piece."""
    from agency.services.analytics_fetcher import get_content_analytics

    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id, ContentPiece.org_id == org_id
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    return {"items": await get_content_analytics(db, content_id)}


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

    from agency.services.llm_provider import get_worker_llm

    llm = get_worker_llm()

    PLATFORM_GUIDELINES = {
        "twitter": "Max 280 chars. Conversational, punchy. Use 1-3 hashtags. Thread-friendly.",
        "linkedin": "Professional tone. 1300 char sweet spot. Use line breaks for readability.",
        "instagram": "Visual-first caption. Storytelling. 5-10 relevant hashtags at end.",
        "facebook": "Conversational, community-oriented. Questions drive engagement.",
        "tiktok": "Gen-Z friendly. Hook in first line. Trending sounds/hashtags.",
    }

    created = []
    for platform in target_platforms:
        if platform == piece.platform:
            continue
        guidelines = PLATFORM_GUIDELINES.get(platform, "Adapt naturally for this platform.")
        prompt = f"""Repurpose this content for {platform}.

Original ({piece.platform}):
{piece.body}

Platform guidelines: {guidelines}

Return JSON: {{"body": "...", "title": "...", "hashtags": ["..."]}}"""

        response = await llm.ainvoke(prompt)
        try:
            text = response.content if hasattr(response, "content") else str(response)
            if not isinstance(text, str):
                text = str(text)
            text = text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            data = json.loads(text)
        except Exception:
            raw = response.content if hasattr(response, "content") else str(response)
            data = {
                "body": raw if isinstance(raw, str) else str(raw),
                "title": piece.title,
                "hashtags": [],
            }

        new_piece = ContentPiece(
            campaign_id=piece.campaign_id,
            client_id=piece.client_id,
            org_id=org_id,
            content_type=piece.content_type,
            platform=platform,
            title=data.get("title", piece.title),
            body=data.get("body", ""),
            hashtags=data.get("hashtags", []),
            metadata_={"repurposed_from": str(content_id)},
            ai_generated=True,
            status="draft",
        )
        db.add(new_piece)
        created.append(platform)

    await db.commit()
    return {"status": "repurposed", "platforms": created, "count": len(created)}


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

    from agency.services.llm_provider import get_worker_llm

    llm = get_worker_llm()

    labels = ["B", "C", "D", "E"]
    created = []

    for i in range(min(num_variants, 4)):
        prompt = f"""Create variant {labels[i]} of this {piece.platform} post.
Keep the same intent but vary: tone, CTA, hook, structure, or angle.

Original:
{piece.body}

Return JSON: {{"body": "...", "title": "...", "hashtags": ["..."]}}"""

        response = await llm.ainvoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        text = text.strip()

        try:
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            data = json.loads(text)
        except Exception:
            data = {"body": text, "title": piece.title, "hashtags": []}

        variant = ContentPiece(
            campaign_id=piece.campaign_id,
            client_id=piece.client_id,
            org_id=org_id,
            content_type=piece.content_type,
            platform=piece.platform,
            title=data.get("title", piece.title),
            body=data.get("body", ""),
            hashtags=data.get("hashtags", piece.hashtags),
            metadata_={"variant_group": variant_group, "variant_label": labels[i]},
            ai_generated=True,
            status="draft",
        )
        db.add(variant)
        created.append(labels[i])

    await db.commit()
    return {
        "status": "variants_created",
        "variant_group": variant_group,
        "variants": created,
    }


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
