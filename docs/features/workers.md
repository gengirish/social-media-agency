# Background Workers
<!-- verified: 260817 -->

No Celery workers, and **no `backend/src/agency/workers/` package exists**. Background processing is asyncio tasks registered from `main.py`, which starts both the LangGraph runtime and the scheduler on the `startup` hook — the two need matching shutdown handling.

## Campaign Pipeline
**Status**: [LIVE]
**File**: `backend/src/agency/routers/campaigns.py`

`asyncio.create_task(_run_campaign_pipeline(...))` — Launched when a campaign is created. Runs the LangGraph agent graph, emits SSE events, inserts AgentRun records per node, and persists results on completion.

`asyncio.create_task(_resume_pipeline(...))` — Resumes after human review decision.

## Content Scheduler
**Status**: [LIVE]
**File**: `backend/src/agency/services/scheduler.py`

`SchedulerEngine` — Asyncio loop started from `main.py` startup. Runs every 60 seconds checking for content where `scheduled_at <= now()` and `status == "scheduled"`. Publishes via `PlatformPublisher`.

## Brand Learning Trigger
**Status**: [LIVE]
**File**: `backend/src/agency/routers/campaigns.py`

Called within `_persist_campaign_results()` after campaign completion. Feeds topics, platforms, and SEO keywords into `update_brand_learnings()` to improve future campaigns.

## Failure Handling

`_mark_campaign_failed` moves both campaign and workflow to `failed` and records the failure event. Before this existed, a crashed pipeline left its campaign stuck in `running` forever and the failure-rate metric under-reported.

## Checkpointing Caveat

`graph_runtime.py` holds the singleton compiled graph and checkpoints via `AsyncPostgresSaver` over `NEON_DATABASE_URL`. If that var is empty or the pool fails, it **silently falls back to `MemorySaver`** — campaigns then do not survive a restart. Check logs for `langgraph_checkpointer_memory_fallback` when resume behaviour looks broken.
