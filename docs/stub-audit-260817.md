# Stub Audit Sweep — T1.6

<!-- created: 260817 -->

**Scope:** repo-wide sweep of `backend/src`, `frontend/src`, and `.cursor/` prompt assets for anything that "looks real but isn't". Closing task of Phase 1.

**Method:** grep for `In production`, `for now`, `mock`, `placeholder`, `stub`, `dummy`, `fake`, `simulat`, `TODO`, `FIXME`, `coming soon`, `not implemented`, `hardcoded` — plus a full read of every backend service/router/agent and every frontend page/component looking for functions that return constant or literal data a caller would read as measured or retrieved. Text greps alone found almost nothing important; every serious finding came from reading code.

## Classification counts

| Class | Meaning | Count |
|---|---|---|
| **(a)** Real — stale wording only | Code is genuine, comment/copy was misleading | 6 |
| **(b)** Real stub, user-reachable | **Fixed, gated, or badged unavailable** | 21 |
| **(c)** Stub not reachable by any user | Left as-is, listed below | 7 |
| **(r)** Reported only — owned by another task or an excluded file | Not touched | 12 |

**"Looks real but isn't" column: empty.** Every user-reachable item in class (b) now either works, fails loudly, or is visibly labelled unavailable.

---

## (b) User-reachable stubs — fixed / gated / badged

| # | File:line | What it was | Classification & action | Why this choice |
|---|---|---|---|---|
| 1 | `backend/src/agency/services/publishing.py:52` (dispatcher) | `_publish_instagram` returned normally, so `publish()` wrapped it as `{"success": True, "post_id": ""}`. `routers/publishing.py:101` and `services/scheduler.py:140` then set `status = "published"`, stamped `published_at`, and **burned post quota** for a post that was never made. User saw a green success toast and a green `published` badge. | **Gated.** Added `UNAVAILABLE_PUBLISH_PLATFORMS` (`instagram`, `tiktok`) short-circuited in `publish()` to return `success: false` with an actionable message. The `_publish_instagram` body is untouched — T2.1 owns it and just removes the map entry. | Labelling alone was not enough: the API itself was lying. A guard is the smallest change that makes the failure honest without implementing the feature. |
| 2 | `frontend/src/app/(dashboard)/content/page.tsx:164` | "Publish Now" offered for every approved piece, including Instagram/TikTok. | **Badged.** Button replaced by an amber "Publishing unavailable" badge (with the reason on hover) for platforms in the new `frontend/src/lib/platforms.ts` map. | Prefer labelling over deleting — the content itself is real and useful, only the auto-push is missing. |
| 3 | `frontend/src/app/(dashboard)/content/page.tsx:88` | Toast said "Publish requested" regardless of the API response, which was discarded. | **Fixed.** Reads the response and reports what actually happened; refuses locally for gated platforms. | |
| 4 | `frontend/src/app/(dashboard)/content/page.tsx:15` (repurpose targets) | TikTok / Instagram offered as repurpose targets with no hint they cannot be published. | **Badged** "draft only" + explanatory line under the list. | Repurposing to those platforms genuinely works; only publishing does not. |
| 5 | `frontend/src/app/(dashboard)/campaigns/new/page.tsx:24` | TikTok/Instagram offered as campaign channels; no publisher and (TikTok) no OAuth. | **Badged** "draft only" + explanatory line. | Same reasoning — content generation for those channels is real. |
| 6 | `frontend/src/app/(dashboard)/settings/page.tsx:20` | Instagram listed under "Connect social platforms to enable direct publishing". | **Badged** "publishing unavailable" + reworded section copy (connect for analytics, publish manually). | Connecting the account is still useful for metrics later. |
| 7 | `frontend/src/app/page.tsx:90` | Landing copy: "Push to X, LinkedIn, and Meta (Facebook & Instagram) from one workflow." | **Fixed copy** — names the three platforms that actually publish and says Instagram/TikTok are drafted and scheduled. | |
| 8 | `frontend/src/app/page.tsx:262` | Hero diagram: `Publish → X · LinkedIn · Meta`. | **Fixed** → `X · LinkedIn · Facebook`. | "Meta" implied Instagram. |
| 9 | `frontend/src/app/page.tsx:457-490` | `SocialProof`: five invented company names ("Northline", "Vector Labs", …) under *"Trusted by teams who ship campaigns weekly"*, plus two fabricated testimonials including a made-up **"We replaced a $6k/mo retainer"** result. | **Removed entirely** — section deleted, component deleted, call site removed, replaced by a comment forbidding reinstatement. Nothing invented in its place. | The task and the data-reliability rules both forbid fabricated proof. There is no honest version of a customer logo you do not have. |
| 10 | `frontend/src/app/page.tsx:210` | "Watch Demo" button anchored to `#demo`, a static CSS swimlane diagram. No video exists. | **Fixed copy** → "See the pipeline". | |
| 11 | `frontend/src/app/page.tsx:65` | Agency plan bullets "Dedicated success" and "Custom SLAs" — no backend or operational representation. | **Fixed** → "White-label" and "API access", both of which are real (`services/white_label.py`, `routers/public_api.py` + API keys). | Replaced with true claims already in `PLAN_CONFIG`, not with new inventions. |
| 12 | `backend/src/agency/services/billing.py` (`PLAN_CONFIG` starter) + `frontend/src/app/(dashboard)/pricing/page.tsx:29` | Feature bullet "Email reports" — nothing in `routers/reports.py` or `services/reporting.py` sends mail. | **Removed** from both. | |
| 13 | `backend/src/agency/services/billing.py` (`PLAN_CONFIG` growth) + `frontend/src/app/(dashboard)/pricing/page.tsx:42` | "Team (3 seats)" — no seat limit exists in `PLAN_CONFIG` and none is enforced. | **Fixed** → "Team workspaces" (multi-tenant orgs are real). | |
| 14 | `frontend/src/app/(dashboard)/settings/page.tsx:58-83, 227-231, 437-469` | Notification preferences: four switches with baked-in on/off state, toggled in local `useState`, never read from or written to any API — and no notification delivery exists at all. | **Badged.** Replaced with a "Not available yet" amber panel and a disabled "Planned" list. | Deleting the tab would hide the roadmap; live-looking switches that silently discard state are worse than an honest disabled list. |
| 15 | `frontend/src/app/(dashboard)/settings/page.tsx:295-304` | "Upload" logo button firing `toast.message("Logo upload coming soon")`, with "(placeholder)" in the helper text. No upload endpoint exists. | **Badged.** Button replaced by a static "Logo upload not available yet" chip. | A button that only shows a toast is a fake control. |
| 16 | `frontend/src/components/notifications-bell.tsx:116` | Bell polls every 30s and renders "No notifications" forever — `services/notifications.py::create_notification` has no callers anywhere. | **Badged.** Empty state now says notifications are not generated yet. | "No notifications" reads as "you're caught up". |
| 17 | `backend/src/agency/routers/notifications.py:37` | Same, at the API layer. | **Fixed.** Response carries `producers_wired: false` + `reason`. | |
| 18 | `frontend/src/app/(dashboard)/team/page.tsx` | Role badges (admin / manager / content creator / viewer) rendered as if enforced. `services/team.py::check_permission` is defined but **never called** — a viewer can hit every write route. | **Badged.** Amber banner: roles are labels, not restrictions. | This is a security expectation, not a cosmetic one — users must not staff their org on a false assumption. Actually enforcing RBAC is feature work, not an audit fix. |
| 19 | `frontend/src/app/(dashboard)/team/page.tsx:62` | `toast.success("Invitation sent")` regardless of outcome. The backend only mails an invite when AgentMail is configured **and** the org has an inbox id — usually neither. | **Fixed.** Surfaces the backend's own message; on the no-email path shows a 30s warning toast carrying the temporary password to share out of band. | |
| 20 | `backend/src/agency/routers/team.py:86` | `except Exception: pass` swallowed AgentMail send failures; the "pending AgentMail integration" message was ambiguous about whether mail went out. | **Fixed.** Logs the failure, adds an explicit `email_sent: bool`, and the no-email message now says plainly that **no** email was sent. | |
| 21 | `frontend/src/app/(dashboard)/analytics/page.tsx:366-383` | "Platform Insights" card promising that connecting accounts reveals per-platform engagement, ROI, and posting times. No code path ever populates it. | **Badged** "Not available yet" + honest copy explaining that per-post metrics exist but there is no roll-up view. | The promise was conditional on an action the user could take, which made it read as a real, unlocked-later feature. |

## (b) Backend data fabrication — fixed

| # | File:line | What it was | Action |
|---|---|---|---|
| 22 | `backend/src/agency/agents/analytics.py:40` | `engagement_data` is **never written anywhere in the repo**. The Analytics agent — the final node of the pipeline, whose output is streamed to the user and persisted to `AgentRun.output` — always received `{}` and had the LLM invent a performance summary, per-platform insights, and recommendations (the prompt's own example is *"Your LinkedIn posts about [topic] get 3x engagement"*). | **Fixed.** Returns `{"status": "unavailable", "reason": ...}` without calling the model when there is no engagement data. Successful runs are stamped `status: "available"`. |
| 23 | `backend/src/agency/agents/qa_brand.py:98-103` | On an unparseable QA response, fabricated `{"overall_score": 7, "pass": True}` — an invented 7/10 that `graph.py:45` then read as "quality gate passed". | **Fixed.** Returns `overall_score: None`, `pass: None`, `score_available: false`, and an `error` saying the campaign was not quality-checked. Routing is unchanged (`_route_after_qa` still lands on `compile_output` with no critical issues), so this is honest without altering pipeline behaviour. |
| 24 | `backend/src/agency/agents/seo.py:83` | Bare keyword strings were stamped `{"search_volume": "medium", "difficulty": "medium"}` — constants that read as keyword-research metrics. No search API is called anywhere in the agent. | **Fixed.** Constants dropped; every keyword dict is stamped `metrics_source: "llm_estimate"`, and the prompt now tells the model these bands are its own estimate and to omit them when it has no basis. |
| 25 | `backend/src/agency/routers/campaigns.py:419-423` | The first five **LLM-guessed** SEO keywords were persisted into `BrandProfile.tone_attributes["learned"]["best_performing_topics"]` and read back by `GET /brand-analytics/clients/{id}/intelligence`. No performance data was ever consulted. | **Fixed.** Renamed to `seo_target_keywords` in both `campaigns.py` and the `brand_learning.py` passthrough list. `best_performing_topics` remains reserved for a real producer. |
| 26 | `backend/src/agency/services/cross_learning.py:30-34` | `func.avg(...)` over zero rows returns `NULL`, coerced to `0.0`. `GET /brand-analytics/cross-learning?industry=X` therefore reported an "industry benchmark" of all zeros. (The frontend happened to gate on `sample_size > 0`; the API did not.) | **Fixed.** Returns `status: "unavailable"` + `reason` with `null` averages when `sample_size == 0`; `NULL` averages stay `None` rather than becoming `0.0`. |
| 27 | `backend/src/agency/routers/content.py:67,81` | `GET /content/suggestions` ordered by `performance_score.desc().nulls_last()` with **no filter**, so arbitrary published posts came back labelled `"Top performing content — consider reposting or refreshing"` with `performance_score: null`. Nothing in the product ever writes `performance_score`. | **Fixed.** Added `performance_score.isnot(None)`; the (currently always) empty result returns `status: "unavailable"` with a reason. |
| 28 | `backend/src/agency/routers/content.py:121` | `POST /content/video-script` fell back to a hardcoded `{"brand_name": "CampaignForge", "industry": "Marketing"}` when `client_id` was missing **or did not resolve** — a script silently written for the wrong company. | **Fixed.** `client_id` is now required (400) and an unresolved id 404s. *Note:* `VideoScriptRequest.client_id` is optional in `frontend/src/lib/api.ts:798` and should become required — see the excluded-file list. No UI calls this endpoint, so nothing breaks today. |
| 29 | `backend/src/agency/agents/graph.py:70-79` | `human_review_node` recorded `human_review: "approved"` when it resumed with no human decision — an unreviewed campaign was indistinguishable from a signed-off one. | **Fixed.** Records `auto_approved_no_human`. `_route_after_human_review` sends both to `qa_check`, so routing is unchanged; `state.py` comment updated. |
| 30 | `backend/src/agency/routers/slack.py:67-76` | `/campaignforge create` replied *"🚀 Creating campaign… I'll update you when it's ready!"* and returned `"Campaign creation started"`. **No `Campaign` row was created and no pipeline started** — the injected `db` was unused, and the promised follow-up could never arrive. | **Fixed.** Replies that Slack campaign creation is not available and points at the dashboard. `/status` and the `app_mention` reply reworded the same way. |
| 31 | `backend/src/agency/routers/slack.py:15` | `_verify_slack_signature` was defined but **never called** — both `/events` and `/commands` were entirely unauthenticated. Security code that looks present but is not. | **Fixed.** Added `_require_slack_signature`, enforced on both endpoints. Enforcement is conditional on `SLACK_SIGNING_SECRET` being set (logs a warning when it is not) so an unconfigured deployment does not break Slack's URL-verification handshake. **Residual: an unconfigured deployment is still open** — set the secret. |
| 32 | `backend/src/agency/routers/audit.py:34` | `GET /audit` (tagged *"Enterprise — Audit"*, docstring "track all state-changing operations") always returns `[]` because `services/audit.py::log_action` has no callers. An empty audit trail is indistinguishable from "no suspicious activity". | **Fixed.** Empty result returns `status: "unavailable"` + reason. Wiring `log_action` into routes is feature work, deliberately not done here. |
| 33 | `backend/src/agency/routers/campaigns.py:432` | `except Exception: pass  # Log error in production` — post-run bookkeeping failures (workflow completion, brand learning) vanished silently. Same pattern at line 428. | **Fixed.** Both now log via `structlog` (`campaign_completion_bookkeeping_failed`, `brand_learning_update_failed`). |

## (a) Real — stale wording only, comment/doc fixed

| # | File:line | Stale wording | Action |
|---|---|---|---|
| 34 | `backend/src/agency/services/image_generation.py:26` | *"In production, calls fal.ai's text-to-image API"* — it calls it in every environment. | Docstring rewritten to document the three real return shapes (`skipped` / `error` / `generated`) and to tell callers to branch on `status`, never to treat a missing `image_url` as a pending image. |
| 35 | `backend/src/agency/routers/reports.py:37` | `GET /reports/clients/{id}` returned three literal rows shaped like stored reports. It is in fact a fixed enum of the periods `POST` accepts. | Added `kind: "available_periods"` and a docstring saying nothing is persisted. Behaviour unchanged. |
| 36 | `backend/src/agency/services/webhook_dispatcher.py:155` | *"Isolated so tests can inject an `httpx.MockTransport`"* | Genuine and accurate — test seam, not a stub. No change. |
| 37 | `backend/src/agency/services/trends.py:3,94` / `platform_metrics.py:43` | The words "fake"/"hardcoded" appear only in docstrings **forbidding** fabrication. | No change — these are the guardrails, not violations. |
| 38 | `backend/src/agency/agents/competitive_intel.py:488` | `# noqa: BLE001 — an LLM failure must not become fake intel` | Correct as written. No change. |
| 39 | `frontend/src/**` `placeholder="…"` (≈15 hits) | HTML input placeholder attributes. | Not stubs. No change. |
| 40 | `docs/features/README.md:33-44` | "Feature Honesty" table still listed analytics / trends / RAG as stubs, all fixed in T1.1–T1.5. | Rewritten: what Phase 1 fixed, plus a remaining-gaps table naming exactly how each gap is surfaced to the user. |

## (c) Stubs not reachable by any user — left in place

| # | File:line | Why it is unreachable |
|---|---|---|
| 41 | `backend/src/agency/services/ad_optimization.py:12` `analyze_ad_performance` | Zero callers — no router imports it. Would also swallow a parse failure into a plausible-looking response if ever wired; fix that before exposing it. |
| 42 | `backend/src/agency/services/audit.py:13` `log_action` | Defined, never called. Kept — it is the correct API for whoever wires auditing. |
| 43 | `backend/src/agency/services/notifications.py:13` `create_notification` | Same. |
| 44 | `backend/src/agency/services/team.py:89` `check_permission` | Same. Its *effect* (unenforced roles) is now surfaced — see #18. |
| 45 | `frontend/src/app/(dashboard)/page.tsx` + `frontend/src/components/dashboard-content.tsx` | Route collision: `src/app/page.tsx` and `src/app/(dashboard)/page.tsx` both resolve to `/`, and the marketing page wins the build. No nav item links to `/` (the "Overview" entry points at `/campaigns`). The six KPI cards — including a `?? 0` fallback that renders six confident zeros on a failed `getStats()` — are dead code. **Reported, not fixed:** deleting it or fixing the route is a routing decision, not an audit fix. |
| 46 | `frontend/src/app/(dashboard)/templates/page.tsx:46-53` | `/templates` has zero inbound links. `launchTemplate` then redirects to `/campaigns/new?template=…`, but `campaigns/new` never reads `searchParams` — the template's channels/objective are silently dropped and the user lands on a blank wizard. **Reported, not fixed:** a functional gap, not a fabrication. |
| 47 | `frontend/src/app/(dashboard)/campaigns/new/magic-brief/page.tsx` | A complete, working feature with no entry point anywhere in the app. `campaigns/new` renders a "Magic Brief profile ready" card that can only appear if the user reached the orphaned page by URL. **Reported, not fixed.** |

## (r) Reported only — owned by another task, or in an excluded file

| # | Where | Finding | Owner |
|---|---|---|---|
| 48 | `backend/src/agency/services/publishing.py:167` | `_publish_instagram` not implemented. | **T2.1** — only the caller was gated (#1). Removing `"instagram"` from `UNAVAILABLE_PUBLISH_PLATFORMS` is the last step of that task. |
| 49 | `backend/src/agency/services/platform_metrics.py:304` | Instagram metrics return `_unavailable(...)`. Honest already. | **T2.2** |
| 50 | `backend/src/agency/services/billing.py:193` | `_handle_subscription_updated` returns `{"status": "noted"}`. It is registered in the webhook handler map so it **looks** handled, but Stripe plan upgrades/downgrades/past-due transitions are silently discarded behind a success-shaped body. | **T1.7** owns `billing.py`. Not touched beyond the two `PLAN_CONFIG` feature strings (#12, #13). |
| 51 | `backend/src/agency/services/cross_learning.py:25` | `get_industry_benchmarks` filters only on `Client.industry` — **no `org_id` scoping**. It aggregates other tenants' analytics snapshots into a benchmark. Arguably intended (cross-org benchmarking), but it violates the project's own "every org-scoped query filters on `org_id`" rule with no RLS behind it, and leaks a signal about other tenants' volume. | **T1.7 / security review.** Left as-is pending a deliberate decision on whether cross-org benchmarking is intended. |
| 52 | `backend/src/agency/services/image_generation.py:43` | Posts to `https://queue.fal.run/fal-ai/flux/schnell` — the **queue** endpoint, which returns `{request_id, status_url}` with HTTP 200, not `{"images": [...]}`. The parser can therefore never match, and every call falls through to `{"status": "error", "message": "fal.ai returned 200"}`. The sync endpoint is `https://fal.run/...`. Not deceptive (it fails, loudly-ish), but the feature cannot ever have worked. | Reported — needs a `FAL_API_KEY` to verify a fix, so not changed blind. |
| 53 | `backend/src/agency/routers/content.py:279-285, 364-365` | An LLM JSON parse failure is converted into a real `ContentPiece` row whose `body` is the raw unparsed model output (possibly prose or code fences), and the endpoint returns `{"status": "repurposed"}` with no error signal. Reachable via `POST /content/{id}/repurpose` and `/variants`. | Reported — the row is real content, just possibly malformed; fixing it is a content-pipeline change, not an audit fix. |
| 54 | `backend/src/agency/routers/campaigns.py:295` | SSE `progress` is `(index_in_hardcoded_9_element_list + 1) / 9 * 100`, not work done; an unrecognised node reports 11%. Cosmetic, but the field reads as measured. | Reported. |
| 55 | `frontend/src/lib/api.ts` **(EXCLUDED — not edited)** | 19 declared endpoints that **no component calls**: `health`, `getClient`, `submitReview`, `updateContent`, `scheduleContent` (an exact duplicate of `rescheduleContent`), `generateReport`, `getReportPeriods`, `oauthCallback`, `getComments`/`addComment`/`deleteComment`, `getTemplate`, `runCompetitiveScan`, `generateImage`, `createAutonomousCampaign`, `generateOutreach`, `createVideoScript`, `getAuditLogs`, `generateVariants`, `getContentSuggestions`, `getBetaMetrics`. | Reported. |
| 56 | `frontend/src/lib/api.ts:186` **(EXCLUDED)** | `oauthCallback` is declared but **the OAuth loop is never closed in-app**: `settings/page.tsx:188` opens the authorize URL in a new tab and nothing handles the return. Platform connection may therefore never complete from the UI. This is the most consequential item in the excluded file — it undermines every "connect an account" affordance. | Reported — needs an owner. |
| 57 | `frontend/src/lib/api.ts:468-525` **(EXCLUDED)** | `BetaMetrics` declares ~58 fields (time-to-first-campaign percentiles, agent-step drop-off, feature adoption, return-rate cohorts, per-endpoint error rates). `lib/analytics.ts` faithfully ships events to `/api/v1/events`, but **nothing in the app ever reads them back** — the entire beta-metrics surface is write-only. | Reported. |
| 58 | `frontend/src/lib/api.ts:798` **(EXCLUDED)** | `VideoScriptRequest.client_id` is optional but the endpoint now requires it (#28). Should become required. | Reported. |
| 59 | `frontend/src/components/agents/live-agent-dashboard.tsx:228-277` | "Approve & Continue" / "Request Revisions" use raw `fetch` instead of `api.submitReview`, and on failure only `console.error` — no toast, no UI change. To the user the button does nothing. | Reported — a real bug, but an error-handling gap rather than a fabrication. |

---

## Notes on judgement calls

- **Removed vs. labelled.** Only one thing was deleted outright: the fabricated social-proof section (#9). Fabricated evidence has no honest form. Everything else was labelled, because in each case a real capability sits behind the missing piece — Instagram content is genuinely generated, TikTok posts are genuinely scheduled, roles are genuinely stored — and hiding those would cost the user a working feature to fix a wording problem.
- **Nothing was invented.** No replacement logos, testimonials, metrics, or sample data were added anywhere. Where a number could not be measured, the code now returns `null` plus an explicit `status`/`reason`, per `.cursor/workflows/data-reliability-rules.md`.
- **Backend/frontend duplication.** `UNAVAILABLE_PUBLISH_PLATFORMS` exists in both `services/publishing.py` and `frontend/src/lib/platforms.ts`. The backend is authoritative (it enforces); the frontend mirror only decides whether to render a button. Both files carry a comment saying to keep them in sync. An endpoint exposing platform capabilities would be better and is worth doing when the list next changes.

## Gate results

| Gate | Baseline | After |
|---|---|---|
| `pytest tests/ -q --no-cov` | 172 passed, 0 errors | **181 passed, 0 errors** (+9 from a concurrent task; all pass) |
| `ruff check src/ tests/` | 291 | **290** |
| `mypy src/agency/ --ignore-missing-imports` | 410 errors / 61 files | **409 / 61** |
| `npm run lint` | 0 errors, 0 warnings | **0 / 0** |
| `npx tsc --noEmit` | exit 0 | **exit 0** |
| `npm run build` | succeeds | **succeeds** |
