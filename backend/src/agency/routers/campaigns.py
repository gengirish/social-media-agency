"""Campaign router — create campaigns, trigger LangGraph pipeline, SSE streaming."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Query as QueryParam
from jose import JWTError
from jose import jwt as jose_jwt
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from agency.agents.graph_runtime import get_runtime_compiled_graph
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
    CampaignProgressResponse,
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
from agency.permissions import Capability, require_cap
from agency.services import product_analytics as pa
from agency.services.billing import PLAN_CONFIG
from agency.services.webhook_dispatcher import EVENT_CAMPAIGN_COMPLETED, dispatch_webhook

logger = structlog.get_logger()

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

# In-memory stream store for SSE events (production: use Redis pub/sub)
_campaign_streams: dict[str, asyncio.Queue] = {}

# Campaigns whose graph is executing in this process right now. Per-process only:
# on a multi-machine deploy a run on another machine is not visible here.
_active_pipelines: set[str] = set()

# Graph node order, and therefore the denominator of the progress percentage.
# The dashboard rehydrates against this list, so it must stay in step with
# graph.py's node names.
AGENT_ORDER = [
    "orchestrate", "strategise", "seo_research",
    "create_content", "write_ads", "human_review",
    "qa_check", "compile_output", "analytics",
]


@router.post(
    "",
    response_model=CampaignResponse,
    status_code=status.HTTP_201_CREATED,
    # Running the pipeline spends the org's campaign allowance, so it needs more
    # than read access. ``member`` holds campaign.run; ``viewer`` does not.
    dependencies=[Depends(require_cap(Capability.CAMPAIGN_RUN))],
)
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

    now = datetime.now(UTC)
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

    # Anchors time-to-first-campaign and the completion-rate denominator.
    await pa.track(
        db,
        name=pa.CAMPAIGN_CREATED,
        org_id=org_id,
        user_id=user.get("sub"),
        campaign_id=campaign.id,
        properties={"channels": brief.channels, "plan_tier": plan_tier},
    )

    await db.commit()
    await db.refresh(campaign)

    brand_ctx = _build_brand_context(client)

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


def _build_brand_context(client: Client) -> BrandContext:
    """Brand context for a pipeline run, read fresh from the client's profile."""
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
    return brand_ctx


def _brief_from_campaign(campaign: Campaign) -> str:
    """Rebuild a brief from the campaign row when the checkpoint is gone.

    Target audience, key messages and additional context are not stored on the
    campaign, so this is strictly less than the original brief — used only when
    the checkpointer lost the thread (memory fallback, restart).
    """
    budget = (campaign.budget or {}).get("total_usd", 0)
    return f"""Campaign: {campaign.name}
Objective: {campaign.objective}
Channels: {', '.join(campaign.channels or [])}
Budget: ${budget}
Duration: {campaign.start_date} to {campaign.end_date}"""


@router.post(
    "/{campaign_id}/rerun",
    response_model=CampaignResponse,
    dependencies=[Depends(require_cap(Capability.CAMPAIGN_RUN))],
)
async def rerun_campaign(
    campaign_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Run the agent pipeline again on an existing campaign, from the start.

    Discards the campaign's LangGraph checkpoint (including any pending human
    review) and starts a fresh thread under the same id, so review and streaming
    keep working unchanged. Content from earlier runs is left alone; the new run
    adds its own drafts, which go through the approval gate like any other.
    """
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.org_id == org_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    if campaign.status == "autonomous":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {"code": "not_rerunnable", "message": "Autonomous campaigns do not use the pipeline."},
        )

    campaign_id_str = str(campaign_id)
    if campaign_id_str in _active_pipelines:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "pipeline_active", "message": "This campaign's pipeline is still running."},
        )

    result = await db.execute(
        select(Client)
        .where(Client.id == campaign.client_id, Client.org_id == org_id)
        .options(selectinload(Client.brand_profile))
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    # The original brief (audience, key messages, languages) lives only in the
    # checkpoint — recover it before the thread is deleted.
    graph = get_runtime_compiled_graph()
    config = {"configurable": {"thread_id": campaign_id_str}}
    prior: dict[str, Any] = {}
    try:
        snapshot = await graph.aget_state(config)
        if snapshot and snapshot.values:
            prior = dict(snapshot.values)
    except Exception as e:  # noqa: BLE001 — fall back to the campaign row
        logger.warning(
            "campaign_rerun_state_unavailable", campaign_id=campaign_id_str, error=str(e)
        )

    brief_text = prior.get("client_brief") or _brief_from_campaign(campaign)
    target_languages = list(prior.get("target_languages") or [])
    if not prior.get("client_brief"):
        logger.warning("campaign_rerun_brief_reconstructed", campaign_id=campaign_id_str)

    # A fresh thread: re-running on top of a finished checkpoint would merge the
    # new input into old state (appended messages/errors, spent retry_count).
    await graph.checkpointer.adelete_thread(campaign_id_str)

    campaign.status = "running"
    result = await db.execute(select(Workflow).where(Workflow.campaign_id == campaign_id))
    workflow = result.scalar_one_or_none()
    if workflow:
        workflow.status = "running"
        workflow.current_node = ""
        workflow.completed_at = None
    else:
        db.add(Workflow(campaign_id=campaign_id, org_id=org_id, status="running"))

    await db.commit()
    await db.refresh(campaign)

    logger.info(
        "campaign_rerun_started",
        campaign_id=campaign_id_str,
        org_id=str(org_id),
        user_id=user.get("sub"),
        brief_source="checkpoint" if prior.get("client_brief") else "campaign_row",
    )

    _campaign_streams[campaign_id_str] = asyncio.Queue()
    asyncio.create_task(
        _run_campaign_pipeline(
            campaign_id=campaign_id_str,
            org_id=str(org_id),
            client_id=str(campaign.client_id),
            brief_text=brief_text,
            brand_ctx=_build_brand_context(client),
            channels=list(campaign.channels or []),
            budget_usd=float((campaign.budget or {}).get("total_usd", 0) or 0),
            target_languages=target_languages,
        )
    )

    return campaign


async def _record_agent_step(
    campaign_id: str, org_id: str, node_name: str, node_output
) -> None:
    """Persist the agent run and its analytics event. Never breaks the pipeline."""
    try:
        factory = get_session_factory()
        async with factory() as tracking_db:
            tracking_db.add(
                AgentRun(
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
            )
            await tracking_db.commit()
    except Exception:
        pass  # Don't let tracking failures break the pipeline

    await pa.track_detached(
        name=pa.AGENT_STEP_COMPLETED,
        org_id=org_id,
        campaign_id=campaign_id,
        properties={"agent": node_name},
    )


async def _mark_campaign_failed(campaign_id: str, org_id: str, error: str) -> None:
    """Move a crashed pipeline out of 'running' and record the failure.

    Without this a pipeline exception leaves the campaign 'running' forever,
    which both misleads the user and hides the failure from the failure-rate
    metric.
    """
    logger.error("campaign_pipeline_failed", campaign_id=campaign_id, org_id=org_id, error=error)
    try:
        factory = get_session_factory()
        async with factory() as db:
            result = await db.execute(select(Campaign).where(Campaign.id == UUID(campaign_id)))
            campaign = result.scalar_one_or_none()
            if campaign:
                campaign.status = "failed"

            result = await db.execute(
                select(Workflow).where(Workflow.campaign_id == UUID(campaign_id))
            )
            workflow = result.scalar_one_or_none()
            if workflow:
                workflow.status = "failed"
                workflow.completed_at = datetime.now(UTC)

            await db.commit()
    except Exception as e:  # noqa: BLE001 — recording the failure must not raise
        logger.error("campaign_mark_failed_error", campaign_id=campaign_id, error=str(e))

    await pa.track_detached(
        name=pa.CAMPAIGN_FAILED,
        org_id=org_id,
        campaign_id=campaign_id,
        properties={"error": error[:500]},
    )


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

    graph = get_runtime_compiled_graph()
    config = {"configurable": {"thread_id": campaign_id}}

    _active_pipelines.add(campaign_id)
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

                current_idx = AGENT_ORDER.index(node_name) if node_name in AGENT_ORDER else 0
                progress = int((current_idx + 1) / len(AGENT_ORDER) * 100)

                await queue.put(AgentStreamEvent(
                    type="step_complete",
                    agent=node_name,
                    content=f"Agent '{node_name}' completed.",
                    progress=progress,
                ).model_dump_json())

                # Track agent run in DB
                if node_name != "__interrupt__":
                    await _record_agent_step(campaign_id, org_id, node_name, node_output)

        await queue.put(AgentStreamEvent(
            type="complete",
            agent="pipeline",
            content="Campaign pipeline completed successfully.",
            progress=100,
        ).model_dump_json())

        # Persist content pieces to DB
        await _persist_campaign_results(campaign_id, org_id, client_id, graph, config)

        await pa.track_detached(
            name=pa.CAMPAIGN_COMPLETED,
            org_id=org_id,
            campaign_id=campaign_id,
            properties={"resumed": False},
        )

        await dispatch_webhook(
            org_id,
            EVENT_CAMPAIGN_COMPLETED,
            {"campaign_id": str(campaign_id), "client_id": str(client_id), "resumed": False},
        )

    except Exception as e:
        await queue.put(AgentStreamEvent(
            type="error",
            agent="pipeline",
            content=f"Pipeline error: {str(e)}",
        ).model_dump_json())
        await _mark_campaign_failed(campaign_id, org_id, str(e))
    finally:
        _active_pipelines.discard(campaign_id)


async def _persist_campaign_results(
    campaign_id: str, org_id: str, client_id: str, graph, config: dict
):
    """Save agent outputs to the database after pipeline completes."""
    try:
        state = await graph.aget_state(config)
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
                workflow.completed_at = datetime.now(UTC)

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
                    # These are the SEO agent's *target* keywords, not measured
                    # performance. They used to be stored as
                    # ``best_performing_topics``, which read as an analytics result.
                    content_summary["seo_target_keywords"] = [
                        kw.get("keyword", "")
                        for kw in values.get("seo_keywords", [])[:5]
                    ]
                await update_brand_learnings(
                    db, UUID(client_id), content_summary
                )
            except Exception as e:  # noqa: BLE001 — brand learning is non-critical
                logger.warning("brand_learning_update_failed", error=str(e))

            await db.commit()
    except Exception as e:  # noqa: BLE001 — post-run bookkeeping must not crash the run
        logger.error("campaign_completion_bookkeeping_failed", error=str(e))


@router.get("/{campaign_id}/progress", response_model=CampaignProgressResponse)
async def get_campaign_progress(
    campaign_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Pipeline state as the database knows it, independent of the SSE stream.

    The stream replays nothing — its queue is single-consumer and is dropped once
    the run finishes — so a client that reconnects (tab switch, remount, refresh)
    has no way to learn what already happened. This does, from the ``agent_run``
    rows the pipeline writes per node.
    """
    campaign = (
        await db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.org_id == org_id)
        )
    ).scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    rows = (
        await db.execute(
            select(AgentRun.agent_name, AgentRun.status)
            .where(AgentRun.campaign_id == campaign_id, AgentRun.org_id == org_id)
            .order_by(AgentRun.created_at)
        )
    ).all()

    # Every run starts at orchestrate, and a resume after review does not re-enter
    # it, so the last orchestrate row is exactly where the current run began. Rows
    # before it belong to a previous re-run and would otherwise report its progress.
    names = [name for name, _ in rows]
    start = len(names) - 1 - names[::-1].index("orchestrate") if "orchestrate" in names else 0
    agent_statuses: dict[str, str] = {}
    for name, run_status in rows[start:]:
        agent_statuses[name] = "error" if run_status == "failed" else "complete"

    completed = [AGENT_ORDER.index(n) for n in agent_statuses if n in AGENT_ORDER]
    progress = int((max(completed) + 1) / len(AGENT_ORDER) * 100) if completed else 0

    is_active = str(campaign_id) in _active_pipelines
    if campaign.status == "completed":
        progress = 100
    elif (
        campaign.status == "running"
        and "human_review" not in agent_statuses
        and "create_content" in agent_statuses
        and "write_ads" in agent_statuses
    ):
        # Paused at the review gate: the graph interrupts *before* human_review, so
        # that node never runs and never writes a row of its own.
        agent_statuses["human_review"] = "waiting"

    return CampaignProgressResponse(
        campaign_status=campaign.status,
        progress=progress,
        agent_statuses=agent_statuses,
        is_active=is_active,
    )


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
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            ) from e

    org_raw = user.get("org_id")
    if not org_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization context required",
        )
    try:
        cid = UUID(campaign_id)
        oid = UUID(str(org_raw))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid campaign id",
        ) from e

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
            except TimeoutError:
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
    """Get trending topics for campaign inspiration (live Exa search).

    Passes the service payload through unchanged: on failure or a missing
    ``EXA_API_KEY`` this returns ``{"status": "unavailable", "reason": ...}``
    with an empty ``items`` list, never fabricated topics.
    """
    from agency.services.trends import get_trending_topics

    return await get_trending_topics(platform)


@router.post(
    "/autonomous",
    dependencies=[Depends(require_cap(Capability.CAMPAIGN_RUN))],
)
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

    today = datetime.now(UTC).date()
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


@router.patch(
    "/{campaign_id}/review",
    # Product rule 2: a human has final say. A viewer is not that human — this
    # decision resumes the paused graph and spends the rest of the run.
    dependencies=[Depends(require_cap(Capability.CAMPAIGN_RUN))],
)
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

    graph = get_runtime_compiled_graph()
    config = {"configurable": {"thread_id": str(campaign_id)}}

    await graph.aupdate_state(
        config,
        {
            "human_review": decision.get("decision", "approved"),
            "human_feedback": decision.get("feedback", ""),
        },
        as_node="human_review",
    )

    await pa.track(
        db,
        name=pa.HUMAN_REVIEW_SUBMITTED,
        org_id=org_id,
        user_id=user.get("sub"),
        campaign_id=campaign_id,
        properties={"decision": decision.get("decision", "approved")},
    )
    await db.commit()

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

    _active_pipelines.add(campaign_id)
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

                current_idx = AGENT_ORDER.index(node_name) if node_name in AGENT_ORDER else 0
                progress = int((current_idx + 1) / len(AGENT_ORDER) * 100)

                await queue.put(AgentStreamEvent(
                    type="step_complete",
                    agent=node_name,
                    content=f"Agent '{node_name}' completed after review.",
                    progress=progress,
                ).model_dump_json())

                await _record_agent_step(campaign_id, org_id, node_name, node_output)

        await queue.put(AgentStreamEvent(
            type="complete",
            agent="pipeline",
            content="Campaign completed after human review.",
            progress=100,
        ).model_dump_json())

        await _persist_campaign_results(campaign_id, org_id, client_id, graph, config)

        await pa.track_detached(
            name=pa.CAMPAIGN_COMPLETED,
            org_id=org_id,
            campaign_id=campaign_id,
            properties={"resumed": True},
        )

        await dispatch_webhook(
            org_id,
            EVENT_CAMPAIGN_COMPLETED,
            {"campaign_id": str(campaign_id), "client_id": str(client_id), "resumed": True},
        )

    except Exception as e:
        await queue.put(AgentStreamEvent(
            type="error",
            agent="pipeline",
            content=f"Error after review: {str(e)}",
        ).model_dump_json())
        await _mark_campaign_failed(campaign_id, org_id, str(e))
    finally:
        _active_pipelines.discard(campaign_id)
