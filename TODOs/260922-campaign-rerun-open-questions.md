# Campaign re-run — open questions

Raised 260922 while building `POST /api/v1/campaigns/{id}/rerun` (commit `1a8fa94`, branch `feat/campaign-rerun`). The feature works; these are decisions and follow-ups it left open.

Code: `rerun_campaign` in [backend/src/agency/routers/campaigns.py](../backend/src/agency/routers/campaigns.py), tests in [backend/tests/test_campaign_rerun.py](../backend/tests/test_campaign_rerun.py).

---

## 1. Should a re-run count against quota?

**Now:** no. A re-run creates no `campaign` row, so the monthly `campaigns_limit` check in `create_campaign` never sees it. Each re-run still spends a full pipeline of LLM calls, so re-runs are free and unlimited.

**Options:**
- Leave it free. That's simplest, and fine while retrying failed runs is the main use.
- Charge completed/failed campaigns only, and keep "stuck in `running`" free as recovery.
- Add a separate per-plan `reruns_limit` in `PLAN_CONFIG`.

**Decision:** _open_

## 2. The brief is lost when the checkpoint is gone

**Now:** the original brief (target audience, key messages, additional context, languages) lives only in the LangGraph checkpoint (`client_brief`, `target_languages`). If the thread is missing (a `MemorySaver` fallback, a restart under memory, or a pre-checkpointer campaign), the re-run rebuilds a thinner brief from the `campaign` row. That brief has only name, objective, channels, budget and dates. It logs `campaign_rerun_brief_reconstructed`.

**Fix:** persist the brief on the campaign.
- Add a `brief JSONB` column in `db/init.sql` and `models/tables.py`.
- Add a dated script in `db/migrations/` and run it by hand on Neon.
- Write it in `create_campaign`; prefer it over the checkpoint in `rerun_campaign`.

**Decision:** _open_

## 3. The "still running" guard only sees one machine

**Now:** `_active_pipelines` is an in-process set. A 409 `pipeline_active` fires only if the run executes on the machine serving the re-run request. With more than one Fly machine, a re-run could delete the checkpoint of a run that is still executing elsewhere. `_campaign_streams` has the same single-process assumption; see the Redis pub/sub note at the top of the router.

**Options:** pin the Fly app to one machine for now, or move both to a shared store (Redis, or a `workflow.status` + heartbeat column).

**Decision:** _open_

## 4. Re-runs skew the beta completion metrics

**Now:** a re-run records no `campaign_created` event, but its `campaign_completed` / `campaign_failed` still count. `services/product_analytics.py` counts raw events, so completion and failure rates can go above 100% after re-runs.

**Options:**
- Add a server-authored `campaign_rerun` event and count it in the denominator.
- Count distinct `campaign_id`s instead of raw events.

**Decision:** _open_

## 5. Possible existing bug: the run "completes" when it pauses for review

**Not caused by the re-run change. Found while reading the code; not yet confirmed.**

The graph compiles with `interrupt_before=["human_review"]`, so `graph.astream` in `_run_campaign_pipeline` returns when it reaches the review gate. The code after the loop then runs unconditionally:
- It emits a `complete` SSE event.
- It calls `_persist_campaign_results`, which saves content pieces and sets the campaign and workflow to `completed`.
- It tracks `campaign_completed` and dispatches the `campaign.completed` webhook.

After review, `_resume_pipeline` does all of this again.

**Likely effects, if confirmed:**
- The campaign shows `completed` while it is still awaiting review.
- Content pieces are saved twice.
- Completion events and webhooks are sent twice.

**To confirm:** run a campaign locally to the review gate, then check `campaign.status` and the `content_piece` count before and after approving.

**Fix direction:** after the stream ends, check `(await graph.aget_state(config)).next`. If it is non-empty, the graph is paused: emit `waiting_human` and return without persisting.

**Decision:** _open — confirm first_
