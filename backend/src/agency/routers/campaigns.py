"""Campaign router — create campaigns, trigger LangGraph pipeline, SSE streaming."""

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from agency.agents.graph import get_compiled_graph
from agency.agents.state import BrandContext, CampaignState
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.schemas import (
    AgentStreamEvent,
    CampaignBrief,
    CampaignListResponse,
    CampaignResponse,
)
from agency.models.tables import (
    AgentRun,
    BrandProfile,
    Campaign,
    Client,
    ContentPiece,
    Workflow,
)

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
Additional Context: {brief.additional_context}"""

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
        "qa_check", "compile_output",
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
    from agency.models.database import get_session_factory

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

            await db.commit()
    except Exception:
        pass  # Log error in production


@router.get("/{campaign_id}/stream")
async def stream_campaign(
    campaign_id: str,
    user=Depends(get_current_user),
):
    """SSE endpoint — streams agent progress events in real time."""
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
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
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

    asyncio.create_task(_resume_pipeline(graph, config, campaign_id_str))

    return {"status": "review_submitted", "decision": decision.get("decision")}


async def _resume_pipeline(graph, config: dict, campaign_id: str):
    """Resume pipeline after human review."""
    queue = _campaign_streams.get(campaign_id)
    if not queue:
        return

    try:
        async for event in graph.astream(None, config=config, stream_mode="updates"):
            for node_name, node_output in event.items():
                await queue.put(AgentStreamEvent(
                    type="step_complete",
                    agent=node_name,
                    content=f"Agent '{node_name}' completed after review.",
                    progress=90,
                ).model_dump_json())

        await queue.put(AgentStreamEvent(
            type="complete",
            agent="pipeline",
            content="Campaign completed after human review.",
            progress=100,
        ).model_dump_json())

    except Exception as e:
        await queue.put(AgentStreamEvent(
            type="error",
            agent="pipeline",
            content=f"Error after review: {str(e)}",
        ).model_dump_json())
