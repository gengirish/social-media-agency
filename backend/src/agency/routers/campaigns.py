"""Campaign router — create campaigns, trigger LangGraph pipeline, SSE streaming."""

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam, status
from jose import JWTError, jwt as jose_jwt
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from agency.agents.graph import get_compiled_graph
from agency.agents.state import BrandContext, CampaignState
from agency.config import get_settings
from agency.dependencies import (
    _resolve_clerk_user,
    _verify_clerk_jwt,
    get_current_user,
    get_db,
    get_org_id,
)
from agency.models.database import get_session_factory
from agency.models.schemas import (
    AgentStreamEvent,
    CampaignBrief,
    CampaignListResponse,
    CampaignResponse,
)
from agency.models.tables import (
    AgentRun,
    Campaign,
    Client,
    ContentPiece,
    Subscription,
    Workflow,
)
from agency.services.billing import PLAN_CONFIG

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

# In-memory stream store for SSE events (production: use Redis pub/sub)
_campaign_streams: dict[str, asyncio.Queue] = {}


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    brief: CampaignBrief,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Create a campaign and trigger the LangGraph agent pipeline."""
    # Verify client exists and belongs to org
    result = await db.execute(
        select(Client)
        .where(Client.id == brief.client_id, Client.org_id == org_id)
        .options(selectinload(Client.brand_profile))
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    # Quota check
    result_sub = await db.execute(
        select(Subscription).where(Subscription.org_id == org_id)
    )
    sub = result_sub.scalar_one_or_none()
    plan_tier = sub.plan_tier if sub else "free"
    plan = PLAN_CONFIG.get(plan_tier, PLAN_CONFIG["free"])
    campaigns_limit = plan.get("campaigns_limit", 5)

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result_count = await db.execute(
        select(func.count(Campaign.id)).where(
            Campaign.org_id == org_id,
            Campaign.created_at >= month_start,
        )
    )
    campaign_count = result_count.scalar() or 0
    if campaign_count >= campaigns_limit:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Campaign limit reached ({campaigns_limit}/mo). Upgrade your plan.",
        )

    # Create campaign record
    campaign = Campaign(
        client_id=brief.client_id,
        org_id=org_id,
        name=brief.campaign_name,
        objective=brief.objective,
        channels=brief.channels,
        start_date=brief.start_date,
        end_date=brief.end_date,
        budget={"total_usd": brief.budget_usd},
        status="running",
    )
    db.add(campaign)
    await db.flush()

    # Create workflow record
    workflow = Workflow(
        campaign_id=campaign.id,
        org_id=org_id,
        status="running",
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(campaign)

    # Build brand context
    brand_ctx = BrandContext(
        brand_name=client.brand_name,
        industry=client.industry or "",
        description=client.description or "",
    )
    if client.brand_profile:
        bp = client.brand_profile
        brand_ctx.update({
            "voice_description": bp.voice_description or "",
            "tone_attributes": bp.tone_attributes or {},
            "target_audience": bp.target_audience or "",
            "style_rules": bp.style_rules or [],
            "vocabulary_include": bp.vocabulary_include or [],
            "vocabulary_exclude": bp.vocabulary_exclude or [],
            "emoji_policy": bp.emoji_policy or "moderate",
            "competitor_differentiation": bp.competitor_differentiation or "",
        })

    # Compose the client brief text
    brief_text = f"""Campaign: {brief.campaign_name}
Objective: {brief.objective}
Target Audience: {brief.target_audience}
Key Messages: {', '.join(brief.key_messages) if brief.key_messages else 'Not specified'}
Channels: {', '.join(brief.channels)}
Budget: ${brief.budget_usd}
Duration: {brief.start_date} to {brief.end_date}
Additional Context: {brief.additional_context}
Languages: {', '.join(brief.languages) if brief.languages else 'Default (brief language)'}"""

    # Initialize SSE stream
    campaign_id_str = str(campaign.id)
    _campaign_streams[campaign_id_str] = asyncio.Queue()

    # Launch LangGraph pipeline in background
    asyncio.create_task(
        _run_campaign_pipeline(
            campaign_id=campaign_id_str,
            org_id=str(org_id),
            client_id=str(brief.client_id),
            brief_text=brief_text,
            brand_ctx=brand_ctx,
            channels=brief.channels,
            budget_usd=brief.budget_usd,
            target_languages=brief.languages,
        )
    )

    return campaign


async def _run_campaign_pipeline(
    campaign_id: str,
    org_id: str,
    client_id: str,
    brief_text: str,
    brand_ctx: BrandContext,
    channels: list[str],
    budget_usd: float,
    target_languages: list[str] | None = None,
):
    """Execute the LangGraph campaign pipeline and emit SSE events."""
    queue = _campaign_streams.get(campaign_id)
    if not queue:
        return

    initial_state: CampaignState = {
        "client_brief": brief_text,
        "client_id": client_id,
        "campaign_id": campaign_id,
        "org_id": org_id,
        "channels": channels,
        "budget_usd": budget_usd,
        "target_languages": list(target_languages or []),
        "brand_context": brand_ctx,
        "status": "running",
        "errors": [],
        "retry_count": 0,
        "messages": [],
    }

    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": campaign_id}}

    agent_order = [
        "orchestrate", "strategise", "seo_research",
        "create_content", "write_ads", "human_review",
        "qa_check", "compile_output", "analytics",
    ]

    try:
        async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name == "__interrupt__":
                    await queue.put(AgentStreamEvent(
                        type="waiting_human",
                        agent="human_review",
                        content="Content generated. Awaiting human review.",
                    ).model_dump_json())
                    continue

                current_idx = agent_order.index(node_name) if node_name in agent_order else 0
                progress = int((current_idx + 1) / len(agent_order) * 100)

                await queue.put(AgentStreamEvent(
                    type="step_complete",
                    agent=node_name,
                    content=f"Agent '{node_name}' completed.",
                    progress=progress,
                ).model_dump_json())

                # Track agent run in DB
                if node_name != "__interrupt__":
                    try:
                        factory = get_session_factory()
                        async with factory() as tracking_db:
                            agent_run = AgentRun(
                                campaign_id=UUID(campaign_id),
                                org_id=UUID(org_id),
                                agent_name=node_name,
                                status="completed",
                                output=(
                                    json.dumps(node_output)
                                    if isinstance(node_output, dict)
                                    else str(node_output)
                                ),
                            )
                            tracking_db.add(agent_run)
                            await tracking_db.commit()
                    except Exception:
                        pass  # Don't let tracking failures break the pipeline

        await queue.put(AgentStreamEvent(
            type="complete",
            agent="pipeline",
            content="Campaign pipeline completed successfully.",
            progress=100,
        ).model_dump_json())

        # Persist content pieces to DB
        await _persist_campaign_results(campaign_id, org_id, client_id, graph, config)

    except Exception as e:
        await queue.put(AgentStreamEvent(
            type="error",
            agent="pipeline",
            content=f"Pipeline error: {str(e)}",
        ).model_dump_json())


async def _persist_campaign_results(
    campaign_id: str, org_id: str, client_id: str, graph, config: dict
):
    """Save agent outputs to the database after pipeline completes."""
    try:
        state = graph.get_state(config)
        if not state or not state.values:
            return

        values = state.values
        factory = get_session_factory()

        async with factory() as db:
            # Save content pieces
            for piece in values.get("content_pieces", []):
                cp = ContentPiece(
                    campaign_id=campaign_id,
                    client_id=client_id,
                    org_id=org_id,
                    content_type=piece.get("content_type", "social_post"),
                    platform=piece.get("platform", ""),
                    title=piece.get("title", ""),
                    body=piece.get("body", ""),
                    hashtags=piece.get("hashtags", []),
                    metadata_=piece.get("metadata", {}),
                    ai_generated=True,
                    status="draft",
                )
                db.add(cp)

            # Save ad variants as content pieces
            for ad in values.get("ad_variants", []):
                cp = ContentPiece(
                    campaign_id=campaign_id,
                    client_id=client_id,
                    org_id=org_id,
                    content_type=f"{ad.get('platform', 'google')}_ad",
                    platform=ad.get("platform", "google"),
                    title=f"Ad Variant {ad.get('variant', 1)} - {ad.get('angle', 'general')}",
                    body=json.dumps(ad.get("headlines", [])),
                    metadata_=ad,
                    ai_generated=True,
                    status="draft",
                )
                db.add(cp)

            # Update campaign status
            result = await db.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            campaign = result.scalar_one_or_none()
            if campaign:
                campaign.status = "completed"
                campaign.agent_plan = values.get("execution_plan", {})

            # Update workflow
            result = await db.execute(
                select(Workflow).where(Workflow.campaign_id == campaign_id)
            )
            workflow = result.scalar_one_or_none()
            if workflow:
                workflow.status = "completed"
                workflow.completed_at = datetime.now(timezone.utc)

            try:
                from agency.services.brand_learning import update_brand_learnings

                content_summary = {
                    "topics_covered": [
                        p.get("title", "") for p in values.get("content_pieces", [])
                    ],
                    "platforms_used": list(
                        {p.get("platform", "") for p in values.get("content_pieces", [])}
                    ),
                    "ad_platforms": list(
                        {a.get("platform", "") for a in values.get("ad_variants", [])}
                    ),
                }
                if values.get("seo_keywords"):
                    content_summary["best_performing_topics"] = [
                        kw.get("keyword", "")
                        for kw in values.get("seo_keywords", [])[:5]
                    ]
                await update_brand_learnings(
                    db, UUID(client_id), content_summary
                )
            except Exception:
                pass  # Brand learning is non-critical

            await db.commit()
    except Exception:
        pass  # Log error in production


@router.get("/{campaign_id}/stream")
async def stream_campaign(
    campaign_id: str,
    token: str = QueryParam(default=""),
):
    """SSE endpoint — streams agent progress events in real time.

    Accepts JWT via ``token`` query param because EventSource cannot send
    Authorization headers.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token required",
        )

    settings = get_settings()
    user = None

    if settings.clerk_jwks_url and settings.clerk_secret_key:
        try:
            clerk_payload = await _verify_clerk_jwt(token, settings.clerk_jwks_url)
            user = await _resolve_clerk_user(clerk_payload, settings)
        except Exception:
            pass

    if not user:
        try:
            user = jose_jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

    org_raw = user.get("org_id")
    if not org_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization context required",
        )
    try:
        cid = UUID(campaign_id)
        oid = UUID(str(org_raw))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid campaign id",
        )

    factory = get_session_factory()
    async with factory() as auth_db:
        result = await auth_db.execute(
            select(Campaign).where(Campaign.id == cid, Campaign.org_id == oid)
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

    queue = _campaign_streams.get(campaign_id)

    async def event_generator():
        if not queue:
            yield json.dumps(AgentStreamEvent(
                type="error",
                content="No active pipeline for this campaign.",
            ).model_dump())
            return

        while True:
            try:
                event_data = await asyncio.wait_for(queue.get(), timeout=120)
                yield event_data

                parsed = json.loads(event_data)
                if parsed.get("type") in ("complete", "error"):
                    _campaign_streams.pop(campaign_id, None)
                    break
            except asyncio.TimeoutError:
                yield AgentStreamEvent(type="heartbeat").model_dump_json()

    return EventSourceResponse(event_generator())


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    client_id: UUID | None = None,
    page: int = QueryParam(1, ge=1),
    per_page: int = QueryParam(20, ge=1, le=100),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    q = select(Campaign).where(Campaign.org_id == org_id)
    count_q = select(func.count(Campaign.id)).where(Campaign.org_id == org_id)

    if client_id:
        q = q.where(Campaign.client_id == client_id)
        count_q = count_q.where(Campaign.client_id == client_id)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(
        q.order_by(Campaign.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    campaigns = result.scalars().all()
    return CampaignListResponse(items=campaigns, total=total, page=page, per_page=per_page)


@router.get("/trends")
async def get_trends(
    platform: str | None = None,
    user=Depends(get_current_user),
):
    """Get trending topics for campaign inspiration."""
    from agency.services.trends import get_trending_topics

    trends = await get_trending_topics(platform)
    return {"items": trends}


@router.post("/autonomous")
async def create_autonomous_campaign(
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Create an autonomous campaign that runs on weekly cycles."""
    goal = body.get("goal", "")
    client_id = body.get("client_id")
    if not client_id or not goal:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "client_id and goal required"
        )

    result = await db.execute(
        select(Client)
        .where(Client.id == UUID(str(client_id)), Client.org_id == org_id)
        .options(selectinload(Client.brand_profile))
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    brand_context = {
        "brand_name": client.brand_name,
        "industry": client.industry or "",
    }

    from agency.agents.autonomous_operator import plan_autonomous_cycle

    plan = await plan_autonomous_cycle(goal, brand_context)

    today = datetime.now(timezone.utc).date()
    campaign = Campaign(
        client_id=UUID(str(client_id)),
        org_id=org_id,
        name=f"Autonomous: {goal[:50]}",
        objective=goal,
        channels=["twitter", "linkedin", "instagram"],
        start_date=today,
        end_date=today,
        budget={},
        status="autonomous",
        agent_plan=plan,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "status": "autonomous",
        "plan": plan,
    }


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.org_id == org_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    return campaign


@router.get("/{campaign_id}/content")
async def get_campaign_content(
    campaign_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await db.execute(
        select(ContentPiece)
        .where(ContentPiece.campaign_id == campaign_id, ContentPiece.org_id == org_id)
        .order_by(ContentPiece.created_at)
    )
    pieces = result.scalars().all()
    return {"items": pieces, "total": len(pieces)}


@router.patch("/{campaign_id}/review")
async def submit_human_review(
    campaign_id: UUID,
    decision: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Submit human review for a paused campaign pipeline.
    Body: {"decision": "approved|revise_content|revise_ads", "feedback": "optional text"}
    """
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.org_id == org_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")

    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": str(campaign_id)}}

    graph.update_state(
        config,
        {
            "human_review": decision.get("decision", "approved"),
            "human_feedback": decision.get("feedback", ""),
        },
    )

    # Resume the pipeline
    campaign_id_str = str(campaign_id)
    if campaign_id_str not in _campaign_streams:
        _campaign_streams[campaign_id_str] = asyncio.Queue()

    asyncio.create_task(
        _resume_pipeline(
            graph,
            config,
            campaign_id_str,
            str(org_id),
            str(campaign.client_id),
        )
    )

    return {"status": "review_submitted", "decision": decision.get("decision")}


async def _resume_pipeline(
    graph,
    config: dict,
    campaign_id: str,
    org_id: str,
    client_id: str,
):
    """Resume pipeline after human review."""
    queue = _campaign_streams.get(campaign_id)
    if not queue:
        return

    agent_order = [
        "orchestrate", "strategise", "seo_research",
        "create_content", "write_ads", "human_review",
        "qa_check", "compile_output", "analytics",
    ]

    try:
        async for event in graph.astream(None, config=config, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name == "__interrupt__":
                    await queue.put(AgentStreamEvent(
                        type="waiting_human",
                        agent="human_review",
                        content="Awaiting human review.",
                    ).model_dump_json())
                    continue

                current_idx = agent_order.index(node_name) if node_name in agent_order else 0
                progress = int((current_idx + 1) / len(agent_order) * 100)

                await queue.put(AgentStreamEvent(
                    type="step_complete",
                    agent=node_name,
                    content=f"Agent '{node_name}' completed after review.",
                    progress=progress,
                ).model_dump_json())

                try:
                    factory = get_session_factory()
                    async with factory() as tracking_db:
                        agent_run = AgentRun(
                            campaign_id=UUID(campaign_id),
                            org_id=UUID(org_id),
                            agent_name=node_name,
                            status="completed",
                            output=(
                                json.dumps(node_output)
                                if isinstance(node_output, dict)
                                else str(node_output)
                            ),
                        )
                        tracking_db.add(agent_run)
                        await tracking_db.commit()
                except Exception:
                    pass

        await queue.put(AgentStreamEvent(
            type="complete",
            agent="pipeline",
            content="Campaign completed after human review.",
            progress=100,
        ).model_dump_json())

        await _persist_campaign_results(campaign_id, org_id, client_id, graph, config)

    except Exception as e:
        await queue.put(AgentStreamEvent(
            type="error",
            agent="pipeline",
            content=f"Error after review: {str(e)}",
        ).model_dump_json())
