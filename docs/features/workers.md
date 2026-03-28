# Background Workers
<!-- verified: 260328 -->

No Celery workers. Background processing uses asyncio tasks.

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
