# CampaignForge AI — Phased Implementation Plan (Subagent Handoff)

<!-- created: 260817 -->

**Purpose:** every remaining gap, broken into self-contained tasks that can be handed to one Claude subagent each.
**Supersedes:** `docs/campaignforge-hardening-backlog.md` (260701) — that audit is partly stale; items already done are marked ✅ below.

## How to hand a task to a subagent

Each task block below is the prompt. Give the agent: the task block verbatim + "read `CLAUDE.md` and the relevant `.cursor/skills/agency-*` skill first."

Rules for the operator:
- **One task = one agent.** Do not merge tasks across phases.
- **Parallel only within a phase**, and only tasks with no overlapping file in `Files:`. Overlaps are flagged as `Conflicts:`.
- Tasks touching >1 file that another parallel agent also edits → run with `isolation: "worktree"`.
- **Schema changes must land in BOTH `db/init.sql` and `backend/src/agency/models/tables.py`** (no Alembic in this repo).
- **Green bar, corrected 260817:** the repo is **not** clean today — `ruff check src/ tests/` fails across ~40 untouched files (E501 in agent prompts, B008 on every FastAPI `Depends` default, I001) and `mypy src/agency/ --ignore-missing-imports` reports **427 errors in 66 files**. So the achievable bar per agent is: **clean on the files you touched, and zero new violations repo-wide.** Do not ask an agent to fix the baseline as a side quest — that is T4.5.
- `pytest tests/ -v` must pass **in full** — but see T0.3: it currently aborts at collection, so until that lands agents can only run a subset.
- **Data reliability is non-negotiable:** no fabricated metrics. Unavailable data returns an explicit unavailable/`⚠️ NOT AVAILABLE` state, never zeros or invented numbers (`.cursor/workflows/data-reliability-rules.md`).

Legend — Effort: **S** ≤1d · **M** 2–4d · **L** 1–2wk. Impact: 🔴 blocker · 🟠 high · 🟡 medium.

---

## Status — 260817

**Phase 0 complete. Phase 1 complete except T1.6.** Verified by running the gates directly, not from agent reports:

| Metric | Before | After |
|---|---|---|
| Tests passing | 39 (suite aborted at collection) | **172, 0 errors** |
| ruff `src/ tests/` | 286 | 291 (+5: `B008` on `Depends` defaults, `UP017` — same patterns as every existing router) |
| mypy `src/agency/` | 427 errors / 66 files | **410 / 61** |

Done: T0.1 · T0.2 · T0.3 · T0.4 · T1.1 · T1.2 · T1.3 · T1.4 · T1.5. Remaining in Phase 1: **T1.6** (stub audit sweep — run last, alone).

**Operator actions required before any of this is real in production:**
1. Create `backend/.env` from the new `backend/.env.example` (nothing runs locally without it). Note `extra="forbid"` — one unknown key aborts startup, and blank ≠ unset.
2. Run `CREATE EXTENSION IF NOT EXISTS vector;` on the Neon branch, confirm with `SELECT extname FROM pg_extension`. **Unverified** — until then RAG runs keyword mode and says so.
3. Run `cd backend && python scripts/index_knowledge_base.py` — deliberately not wired into startup.
4. Set `EXA_API_KEY` — now gates **both** trends and competitive intel; without it both correctly return unavailable rather than inventing data.

### Bugs found by the newly-live tests (T0.3) — fix these

### T1.7 · Tenant-isolation sweep — 6 routers violate the `org_id` rule 🔴 · M
**Why:** the project rule is "every org-scoped query must filter on `org_id`" precisely because **there is no row-level security in this database**. Six routers break it, found by T0.3's newly-live tests and T3.0's enumeration of all 83 routes. Two are cross-tenant **writes**.
1. 🔴 **`routers/oauth.py:135-148`** — `oauth_callback` accepts `client_id` from the request body and attaches a `PlatformAccount` to it **without verifying the client belongs to `org_id`**. Cross-tenant write: an attacker binds their social account to another tenant's client.
2. 🔴 **`routers/comments.py:26-32`** — `add_comment` never verifies `content_id` belongs to the caller's org. Cross-tenant write.
3. 🟠 **`routers/portal.py:14-25`** — `_resolve_org` falls back to `Organization.name == org_slug` via `scalar_one_or_none()`. `name` is **not unique**, so two orgs sharing a name 500 the whole portal; a name can also shadow the intended slug namespace. **Blocks T3.1** — fix before building the portal UI on top of it.
4. 🟠 **`routers/publishing.py:75-81`** — `publish_now` looks up `PlatformAccount` on `client_id`+`platform`+`status` with no `org_id` filter. Not exploitable today (the piece lookup was org-scoped one query earlier) but it is one refactor away from being a leak.
5. 🟡 **`routers/notifications.py:62-66`** — `mark_read` filters `user_id` but not `org_id`.
6. 🟡 **`routers/reports.py:29-42`** — `list_reports` accepts `client_id` and `org_id` and uses **neither**, returning a hardcoded list without checking the client exists in the org.
**Also fix:** `services/billing.py:167-176` — `_handle_invoice_paid` returns `{"status": "usage_reset"}` even when **no subscription matched** the Stripe customer, silently masking an unmatched-webhook condition.
**Acceptance:** all six queries org-scoped; portal resolves on a unique slug column, not `name`; the unmatched-webhook case returns a distinguishable status; **a new tenancy test per router, each proven to fail when its filter is removed** (follow the red/green method T0.3 established in `tests/conftest.py`).
**Depends on:** T0.3 (done) · **Conflicts:** T3.1 must wait on item 3.

### (superseded) T1.7-old · `publish_now` misses its `org_id` filter 🟠 · S
**Why:** `routers/publishing.py:75-81` looks up `PlatformAccount` on `client_id` + `platform` + `status` with **no `org_id` filter**. Not exploitable today because `piece.client_id` was org-scoped one query earlier — but it breaks the project's own "every org-scoped query filters on `org_id`" rule, and there is no RLS in this database, so defence-in-depth is the entire strategy. It becomes a live cross-tenant leak the moment the upstream lookup is relaxed or a client row is ever shared.
**Also fix:** `services/billing.py:167-176` — `_handle_invoice_paid` returns `{"status": "usage_reset"}` even when **no subscription matched** the Stripe customer, silently masking an unmatched-webhook condition.
**Acceptance:** both queries org-scoped; the unmatched-webhook case returns a distinguishable status; a new tenancy test covers the publish path.
**Depends on:** T0.3 (done) · **Conflicts:** none.

---

## Phase 0 — Unblock (do first, ~1 day, sequential)

### T0.1 · Restore local backend config 🔴 · S
**Why:** `backend/.env` does not exist. Nothing runs locally — no pipeline, no demo, no meaningful test run against real providers.
**Files:** `backend/.env.example` (create), `backend/README` section or `CLAUDE.md` if it drifts.
**Do:**
- Generate `backend/.env.example` from every field in `backend/src/agency/config.py`, grouped by feature, each line commented with what turns off when blank.
- Include `TOKEN_ENCRYPTION_KEY` generation instructions (`generate_token_encryption_key()`).
- Document the minimum viable set to boot: `DATABASE_URL`, `NEON_DATABASE_URL`, `JWT_SECRET`, one LLM provider key.
- Do **not** commit real secrets. `.env` stays gitignored — verify it is.
**Acceptance:** `cp .env.example .env` + one LLM key → `uvicorn agency.main:app --port 8001` boots, `GET /api/v1/health/llm` returns a resolved provider, and logs do **not** contain `langgraph_checkpointer_memory_fallback`.
**Depends on:** —

### T0.2 · Reconcile docs with reality 🟡 · S — ✅ DONE 260817
**Why:** `README.md:68-70` claimed 10 routers / 36 endpoints / 15 tables.
**Verified actual (260817, re-derived from source):** **24 routers · 82 endpoints · 18 tables · 23 services · 17 frontend pages · 9 LangGraph nodes**. Note the estimates in the original task line were themselves off — it is 24 routers not 23, and 82 endpoints not ~90.
**Files:** `README.md`, `docs/features/*.md`.
**Done:**
- All 12 `docs/features/*.md` restamped `<!-- verified: 260817 -->` with corrected counts.
- Root `README.md` structure, tech stack (Next.js 15 / React 19 / Gemini 2.5), env vars (added `NEON_DATABASE_URL`, `STRIPE_WEBHOOK_SECRET`), testing section, and honest Project Status block.
- `services.md` plan limits corrected — it contradicted `billing.md` and `PLAN_CONFIG` (claimed free 2/30, starter 5/100, growth 15/500).
- `platform_metrics.py` documented, including that **nothing imports it** and its `unavailable`-not-zeros contract.
- New `[STUB]` status label + **Feature Honesty** table in `docs/features/README.md` covering analytics, trends, RAG, Instagram publish/metrics.
- `websocket.md` needed no rewrite — it already described SSE correctly; only the filename is a WebSocket artefact, now noted in-file.
**Not done:** `websocket.md` was not renamed (kept for link stability). `docs/yc-pitch.md` tech table updated separately.
**Depends on:** — · **Conflicts:** none (docs only) — safe to run parallel with everything.

### T0.3 · Repair the test harness 🔴 · S — discovered 260817, blocks everything
**Why:** `backend/tests/test_billing.py`, `test_quota.py`, `test_tenancy.py` (all untracked) import `create_org`, `create_subscription`, `auth_header_for` and friends from `tests.conftest`, which defines only `anyio_backend`, `client`, `auth_headers`. They raise `ImportError` at **collection**, so `pytest tests/` aborts before running a single test. Every agent's "tests pass" claim is currently scoped to a subset, and the money/tenancy paths — the ones the 260701 audit flagged as P0 — are unverified in CI.
**Files:** `backend/tests/conftest.py`, and only if unavoidable the three test files.
**Do:**
- Read all three test files first and derive the exact fixture/helper contract they expect (names, signatures, return shapes). Implement those helpers in `conftest.py` — do **not** rewrite the tests to match a different contract unless a test is itself wrong, and say so if it is.
- Helpers need real DB rows with correct `org_id` scoping; `create_org` must produce a genuinely isolated tenant so the tenancy tests actually prove isolation rather than passing vacuously.
- Verify the tenancy tests **fail** if you deliberately remove an `org_id` filter from a router — a tenant-isolation test that cannot fail is worse than none.
**Acceptance:** `pytest tests/ -v` collects and runs the whole suite; billing/quota/tenancy tests pass; a deliberately broken `org_id` filter makes them fail.
**Depends on:** run **after** T1.1 and T1.3 land (both are writing new test files and may touch `conftest.py`). · **Conflicts:** any task adding fixtures.

### T0.4 · Frontend lint is a no-op 🟠 · S — discovered 260817
**Why:** `frontend/package.json` declares `eslint` + `eslint-config-next` as devDeps but there is **no ESLint config file**. `next lint` therefore drops into its interactive "How would you like to configure ESLint?" prompt and exits 0 on EOF. `npm run lint` passes without linting anything — and CI's frontend lint step is consequently checking nothing.
**Files:** `frontend/eslint.config.mjs` (or `.eslintrc.json`), `frontend/package.json`, `.github/workflows/ci.yml`.
**Do:** add a real Next.js ESLint config, fix or explicitly baseline what it flags, and make CI fail on lint errors. Use `npx tsc --noEmit` as the interim type gate (it does work today).
**Acceptance:** `npm run lint` non-interactively reports real results and exits non-zero on an introduced violation.
**Depends on:** — · **Conflicts:** none.
**✅ DONE 260817** — `.eslintrc.json` (ESLint 8.57.1 installed; flat config would have been silently ignored). `lint` script moved off `next lint` (deprecated, **removed in Next 16**) to the ESLint CLI with `--max-warnings=0`, which also widened scope to `e2e/`, `middleware.ts`, and root configs that were never linted. 16 findings → 0. Exit-code gate proven by introducing and reverting a violation. Added a `tsc --noEmit` step to CI.

### T0.5 · Remove the build-time check suppressions 🟠 · S — discovered 260817
**Why:** `frontend/next.config.mjs` sets **`typescript.ignoreBuildErrors: true`** and **`eslint.ignoreDuringBuilds: true`**. `next build` therefore type-checks nothing and lints nothing — a production build cannot fail on a type error. Combined with the (now-fixed) no-op lint script, the frontend had no working correctness gate at all. T0.4 bolted `tsc --noEmit` onto CI as a workaround; the real fix is deleting the overrides.
**Files:** `frontend/next.config.mjs`, `.github/workflows/ci.yml`.
**Do:** remove both flags, then fix whatever `next build` now surfaces. `npx tsc --noEmit` and `npm run lint` both pass clean as of 260817, so the blast radius should be small — but verify against the real Vercel build, and **do not remove the `page_client-reference-manifest.js` workaround in `frontend/vercel.json`** (CLAUDE.md flags it as load-bearing).
**Acceptance:** both flags gone; a deliberately introduced type error fails `npm run build`; the Vercel deploy still succeeds.
**Depends on:** T0.4 · **Conflicts:** none.

---

## Phase 1 — Kill the hollow features (trust blockers)

> These currently **look real and are not**. Anything shipped or demoed before this phase risks selling a lie. Highest priority in the whole plan.

### T1.1 · Wire real analytics — `platform_metrics.py` is dead code 🔴 · M
**Why:** `services/platform_metrics.py` is fully implemented (X/LinkedIn/Meta fetchers, retries, explicit `unavailable` results) but **is imported by nothing**. Meanwhile `services/analytics_fetcher.py:38` still comments "Return mock data for now" and writes hardcoded **zeros** into `AnalyticsSnapshot`. The ROI story is the product's core value prop and it is currently fabricated.
**Files:** `backend/src/agency/services/analytics_fetcher.py`, `backend/src/agency/services/scheduler.py`, `backend/src/agency/routers/content.py` (`GET /{content_id}/analytics`), `backend/src/agency/routers/stats.py`, `backend/tests/test_analytics_fetcher.py` (create).
**Do:**
- Replace the mock block in `fetch_content_metrics` with a dispatch into `platform_metrics.fetch_*_metrics`, passing the decrypted `PlatformAccount` token and the platform post id.
- **Never persist a snapshot from an `{"status": "unavailable"}` result** — the module docstring already mandates this. Return the unavailable reason to the caller instead.
- Add a scheduler job that refreshes metrics daily for content `status == "published"` in the last 30 days. Reuse the existing `_run_loop` cadence; do not add a second loop.
- Surface unavailability in the API response shape so the frontend can render "⚠️ not available" rather than 0.
**Acceptance:** a published post with a connected account returns non-zero live metrics; a post with a disconnected/unauthorized account returns an explicit unavailable reason and writes **no** snapshot row; tests cover both paths with mocked HTTP.
**Depends on:** T0.1 · **Conflicts:** T2.2 (both touch `platform_metrics.py`) — run after or in a worktree.

### T1.2 · Trends: real source or delete 🟠 · S
**Why:** `services/trends.py` returns a hardcoded `PLATFORM_TRENDS` dict while the docstring claims "In production, uses Exa search API". It is surfaced in the Analytics page trends tab — invented data shown as insight.
**Files:** `backend/src/agency/services/trends.py`, `backend/src/agency/routers/campaigns.py` (`GET /trends`), `frontend/src/app/(dashboard)/analytics/page.tsx`.
**Do:** implement against Exa (`EXA_API_KEY` already in config). If the key is blank → return an explicit unavailable payload and have the UI render the ⚠️ state. **Delete the hardcoded dict entirely** — do not keep it as a fallback.
**Acceptance:** with a key, topics come from Exa and vary by platform; without a key, the tab shows an unavailable notice with setup instructions and zero invented topics.
**Depends on:** — · **Conflicts:** T3.x analytics UI work.

### T1.3 · Webhooks for real 🟠 · M
**Why:** `routers/webhooks_config.py:13` stores registrations in a **module-level in-memory dict** (`_webhook_store`) — lost on restart, not tenant-durable, not in the DB. `services/webhook_dispatcher.py` only `logger.info`s and has the real implementation commented out. There is no `Webhook` model in `tables.py`.
**Files:** `db/init.sql`, `backend/src/agency/models/tables.py`, `backend/src/agency/models/schemas.py`, `backend/src/agency/routers/webhooks_config.py`, `backend/src/agency/services/webhook_dispatcher.py`, `backend/tests/test_webhooks.py` (create).
**Do:**
- Add a `webhook` table: `id, org_id, url, events[], secret, is_active, created_at`, plus `webhook_delivery` for attempt/status/response-code history.
- Rewrite the router to persist per `org_id` (org-scoped queries — no RLS in this DB).
- Implement real dispatch: HMAC-SHA256 `X-Webhook-Signature` over the raw body, exponential-backoff retries (3 attempts), delivery rows recorded, failures never raising into the caller.
- Fire on at least `campaign.completed` and `content.approved` from the existing call sites.
**Acceptance:** a registered endpoint receives a signed POST on campaign completion; signature verifies against the stored secret; a failing endpoint produces retry rows and does not break the pipeline; registrations survive a restart.
**Depends on:** — · **Conflicts:** T1.4, T4.3 (all touch `tables.py`/`init.sql`) — serialize schema tasks.

### T1.4 · Real RAG (pgvector) 🟡 · M
**Why:** `services/knowledge_base.py` is titled "vector-indexed" and says "In production, this uses pgvector similarity search" but does keyword matching.
**Files:** `db/init.sql`, `backend/src/agency/models/tables.py`, `backend/src/agency/services/knowledge_base.py`, `backend/tests/test_knowledge_base.py` (create).
**Do:** enable the `vector` extension, add an embeddings table, embed the skill library on startup or via a one-shot script, swap `retrieve_knowledge` to cosine similarity with a keyword fallback that is **labelled as such** in the return payload. Neon supports pgvector — confirm before designing around a workaround.
**Acceptance:** semantically related queries with no shared keywords return the right skill docs; the response states which retrieval mode served it.
**Depends on:** — · **Conflicts:** T1.3, T4.3 (schema).

### T1.5 · Ground competitive intel 🟡 · L
**Why:** `agents/competitive_intel.py` + `routers/competitive.py` produce LLM-guessed competitor claims with no source. Presented as intelligence, it is hallucination.
**Files:** `backend/src/agency/agents/competitive_intel.py`, `backend/src/agency/routers/competitive.py`, `backend/tests/test_competitive.py` (create).
**Do:** back every claim with a retrieved source (Exa search + page fetch of the competitor's public social/site content). Each finding must carry a `source_url`. Findings without a source are dropped, not emitted.
**Acceptance:** every returned finding has a resolvable `source_url`; with no `EXA_API_KEY`, the endpoint returns unavailable rather than guessing.
**Depends on:** T1.2 (shares the Exa client — build it once, reuse) · **Conflicts:** —

### T1.6 · Stub audit sweep 🔴 · S
**Why:** closing item — after T1.1–T1.5, verify nothing else "looks real but isn't."
**Files:** repo-wide (read), plus whatever labelling is needed in `frontend/src/`.
**Do:** grep for `In production`, `mock`, `for now`, `placeholder`, `TODO` across `backend/src` and `frontend/src`. For each hit: fix, feature-flag off, or badge "Coming soon" in the UI. Also remove the "Placeholder logos — add your customers here" block on `frontend/src/app/page.tsx:463` or replace with real design-partner logos.
**Acceptance:** a written audit list where every user-facing feature is either real or visibly marked unavailable; zero items in the "looks real but isn't" column.
**Depends on:** T1.1–T1.5 (run **last** in the phase) · **Conflicts:** touches many files — run alone.

---

## Phase 2 — Complete the publishing surface

### T2.1 · Instagram publishing 🟠 · M
**Why:** `services/publishing.py:168` — `_publish_instagram` is not implemented, but Instagram is a headline platform in the UI (`PLATFORM_COLORS` includes it) and marketing copy.
**Files:** `backend/src/agency/services/publishing.py`, `backend/src/agency/services/image_generation.py` (media hand-off), `backend/tests/test_publishing.py` (create).
**Do:** implement the Graph API two-step container → publish flow. Instagram **requires** a public media URL, so wire the fal.ai-generated image (or an S3-uploaded asset) as the media source. If no media is available, fail with a clear actionable error — do not silently skip.
**Acceptance:** an approved image+caption piece publishes to a connected IG business account and returns the post id; a caption-only piece returns a specific "Instagram requires media" error.
**Depends on:** T0.1 · **Conflicts:** T2.3 (same file).

### T2.2 · Instagram metrics 🟡 · S
**Why:** `services/platform_metrics.py:304` returns `_unavailable("Instagram metrics not implemented")`.
**Files:** `backend/src/agency/services/platform_metrics.py`, tests.
**Do:** implement the Graph API `/{ig-media-id}/insights` pull mapped onto the normalized dict. Keep the never-fabricate contract from the module docstring.
**Acceptance:** a published IG post returns live impressions/reach/engagement; metrics the API does not expose are omitted, not zeroed.
**Depends on:** T2.1, T1.1 · **Conflicts:** T1.1.

**⚠️ Three bugs found in `platform_metrics.py` during T1.1 (reported, deliberately not fixed — this task owns the file). Fix these as part of T2.2:**
1. **`_to_int` fabricates zeros, violating the module's own docstring.** `_to_int(None)` returns `0`. In `fetch_twitter_metrics`, `public_metrics` keys are read as `_to_int(public.get("like_count"))` — if X returns the key as `null` or omits it while the parent object exists, a hard **`0` is recorded as a measurement** instead of the field being omitted. Same pattern in the LinkedIn and Facebook fetchers. The `in`-membership guards only protect `impressions`/`clicks`, not `likes`/`shares`/`replies`/`quotes`. Fix: `_to_int` returns `None` on missing input and the key is dropped. **This is the exact failure mode the whole Phase 1 exists to eliminate, hiding inside the module that was supposed to be the fix.**
2. **LinkedIn metrics are unreachable in practice — no LinkedIn ROI number can currently exist.** `fetch_linkedin_metrics(..., org_urn=page_id)` only calls `organizationalEntityShareStatistics` when `org_urn.startswith("urn:li:organization")`. The only value the app can pass is `PlatformAccount.account_handle`, a handle — **no column anywhere stores the org URN.** So LinkedIn always reports impressions/clicks/shares/reach as not-provided. Needs a schema + OAuth-side field before LinkedIn analytics are possible at all.
3. `fetch_post_metrics` tests `if not access_token` *before* decryption, so a ciphertext decrypting to an empty string reaches the platform call instead of returning unavailable.

### T2.4 · Unique constraint on `analytics_snapshot` 🟡 · S — discovered 260817
**Why:** `db/init.sql` (~line 167) has **no unique constraint on `(content_id, date)`**. T1.1's upsert is therefore SELECT-then-update and race-prone if two refreshes for the same post overlap. The single scheduler plus a per-day guard makes this unlikely today, but a partial unique index makes double-measurement impossible rather than merely improbable.
**Files:** `db/init.sql`, `backend/src/agency/models/tables.py`, `backend/src/agency/services/analytics_fetcher.py` (switch to a real upsert).
**Acceptance:** concurrent refreshes for one post produce exactly one row per day.
**Depends on:** T1.1 · **Conflicts:** schema tasks.

### T2.3 · Token refresh + per-platform rate limits 🟠 · M
**Why:** OAuth tokens expire and there is no refresh path; publish/metric calls have generic retries but no per-platform rate-limit handling. First long-lived customer breaks silently.
**Files:** `backend/src/agency/routers/oauth.py`, `backend/src/agency/services/publishing.py`, `backend/src/agency/services/platform_metrics.py`, `backend/src/agency/services/scheduler.py`.
**Do:** store refresh tokens (encrypted via existing `utils/encryption`), refresh on 401 and retry once, mark `PlatformAccount.status = "expired"` when refresh fails, and surface that in Settings. Respect `429` + `Retry-After` per platform with backoff.
**Acceptance:** an expired token is transparently refreshed on the next publish; an unrefreshable account flips to `expired` and the Settings page shows a reconnect prompt.
**Depends on:** T2.1 · **Conflicts:** T2.1, T2.2, T1.1.

---

## Phase 3 — Ship the built-but-invisible features (highest demo ROI)

> These backends **already work**. They have no UI, so they are invisible in a demo. Mostly frontend work — highly parallelizable, low risk.

### T3.1 · Client portal frontend 🟠 · M
**Why:** `routers/portal.py` serves campaigns, content, and client-side content review over `GET/PATCH /api/v1/portal/{org_slug}/...` gated on `WhiteLabel.portal_enabled` — and there is **no frontend for it at all**. This is the single biggest built-but-invisible feature, and it is the white-label wedge for the agency ICP.
**Files:** `frontend/src/app/portal/[orgSlug]/page.tsx` + subroutes (create), `frontend/middleware.ts` (portal routes must be public), `frontend/src/lib/api.ts` (unauthenticated portal client).
**Do:** build a branded, unauthenticated client-facing view: campaign list, content cards, approve/request-changes actions hitting `PATCH /portal/{org_slug}/content/{content_id}`. Pull colors/logo from the white-label branding payload. Add portal paths to the public matcher in `middleware.ts` (currently only `/`, `/sign-in`, `/sign-up`, `/api/webhooks/*` are public).
**Acceptance:** with `portal_enabled`, `/portal/{slug}` renders org-branded content and a client can approve a piece without signing in; with the flag off, it 403s cleanly.
**Depends on:** — · **Conflicts:** T3.2–T3.7 all touch `frontend/src/lib/api.ts` — **serialize the api.ts edits or assign one agent to add all Phase-3 client methods first (T3.0)**.

### T3.0 · (Prerequisite) Expose remaining endpoints in the API client 🟡 · S
**Files:** `frontend/src/lib/api.ts` only.
**Do:** the client already has `getCrossLearning`, `runCompetitiveScan`, `generateImage`, `createAutonomousCampaign`, `generateOutreach`, `createVideoScript`, `getAuditLogs`, `generateVariants`, `getContentSuggestions`, `getBetaMetrics`, `generateReport`, `getReportPeriods`, comments methods — **none of which any component calls**. Verify each against the live route signature, fix drift, and add the missing ones (portal, webhooks config, white-label, marketplace fork/publish, public API key scopes).
**Acceptance:** every mounted `/api/v1` route has a typed client method or a documented reason it does not.
**Run this alone, first in Phase 3.** After it lands, T3.1–T3.7 are safely parallel.

### T3.2 · Reports UI 🟠 · S
**Why:** `routers/reports.py` (`POST/GET /reports/clients/{client_id}`) + `services/reporting.py` work; nothing calls them.
**Files:** `frontend/src/app/(dashboard)/clients/[id]/page.tsx`, new report view component.
**Do:** add a Reports tab on the client detail page — period picker, generate, list past reports, render. Must show ⚠️ for metrics that come back unavailable (post-T1.1 the data is real).
**Acceptance:** generating a report for a seeded client renders real content and no fabricated numbers.
**Depends on:** T3.0, T1.1.

### T3.3 · Autonomous operator + competitive intel UI 🟠 · M
**Why:** `POST /campaigns/autonomous` and `POST /competitive/clients/{id}/scan` are real entry points with no UI. The autonomous operator is the most impressive demo asset in the repo.
**Files:** `frontend/src/app/(dashboard)/campaigns/new/page.tsx` (autonomous mode toggle), new `frontend/src/app/(dashboard)/clients/[id]` intel tab.
**Do:** autonomous mode = objective + cadence → launch, then reuse `LiveAgentDashboard` for streaming. Competitive scan = trigger + findings list with `source_url` per finding.
**Acceptance:** both flows are reachable from nav in under 3 clicks and stream/render results.
**Depends on:** T3.0, T1.5 (intel half).

### T3.4 · Video script + outreach UI 🟡 · S
**Why:** `POST /content/video-script` and `POST /acquisition/outreach` are implemented and invisible.
**Files:** `frontend/src/app/(dashboard)/content/page.tsx`, new outreach page under `(dashboard)`.
**Acceptance:** both generate and persist from the UI.
**Depends on:** T3.0.

### T3.5 · Comments / collaboration UI 🟡 · S
**Why:** `routers/comments.py` (add/list/delete on content) is fully built, `ContentComment` table exists, no UI. This is the "team review" story.
**Files:** `frontend/src/app/(dashboard)/content/page.tsx`, campaign detail content tab.
**Acceptance:** a comment thread renders on a content piece, posts, and deletes with correct author attribution.
**Depends on:** T3.0.

### T3.6 · Content variants + suggestions in the library 🟡 · S
**Why:** `POST /content/{id}/variants` (A/B) and `GET /content/suggestions` exist and are unreachable from the UI.
**Files:** `frontend/src/app/(dashboard)/content/page.tsx`.
**Acceptance:** generate-variants produces side-by-side A/B copy; suggestions render on the library empty/idle state.
**Depends on:** T3.0 · **Conflicts:** T3.4, T3.5 (same file) — assign all three content-page tasks to one agent, or serialize.

### T3.7 · Admin surfaces: audit log, webhooks, beta metrics, white-label 🟡 · M
**Why:** `routers/audit.py`, `webhooks_config.py`, `product_analytics.py` (`GET /beta-metrics`), and white-label branding all lack UI. Beta metrics are the beta-program instrument (`docs/beta-testing-plan.md`) and currently unreadable without curl.
**Files:** new `frontend/src/app/(dashboard)/admin/` routes or tabs on `settings/page.tsx`.
**Do:** audit log table w/ filters; webhook registration + delivery history (post-T1.3); beta-metrics funnel + feature-adoption view; white-label branding editor incl. `portal_enabled` toggle (feeds T3.1).
**Acceptance:** each surface reads live data; the funnel view respects `AGENT_FUNNEL_ORDER`.
**Depends on:** T3.0, T1.3 (webhooks half).

---

## Phase 4 — Hardening

### T4.1 · Broaden test coverage 🟠 · L
**Why:** 66 tests across `test_agents/test_graph.py`, `test_billing`, `test_quota`, `test_tenancy`, `test_health`, `test_llm_provider`, `test_product_analytics` — for ~90 endpoints and 23 services. Billing/quota/tenancy are ✅ covered (the 260701 P0-2 item is largely done). The uncovered risk is now publishing, OAuth, portal, scheduler, and the agent nodes.
**Files:** `backend/tests/` (new files per area).
**Do:** add `test_publishing.py`, `test_oauth.py`, `test_portal.py`, `test_scheduler.py`, `test_agents/test_nodes.py`. Mock all outbound HTTP. Include a portal tenant-isolation test (portal routes are unauthenticated — prove org A's slug cannot read org B's content).
**Acceptance:** ≥60% coverage on `services/`; portal isolation test exists and denies.
**Depends on:** Phases 1–2 (test what's real).

### T4.2 · Observability + user-visible failures 🟠 · M
**Why:** pipeline failures are hard to diagnose in prod and the SSE dashboard has no explicit failure state beyond a generic error close.
**Files:** `backend/src/agency/main.py`, `backend/src/agency/routers/campaigns.py`, `frontend/src/components/agents/live-agent-dashboard.tsx`.
**Do:** Sentry (or equivalent) init; structured error events on every agent node failure; SSE emits a typed `agent_failed` event with the node name; the dashboard renders which agent failed and why, with a retry action.
**Acceptance:** a forced failure in the Content node shows "Content Writer failed: <reason>" in the UI and produces a logged/Sentry event.
**Depends on:** —

### T4.3 · Team invites: signed links, not temp passwords 🟠 · M
**Why:** `routers/team.py:46-47` — invites issue a temp password, and no email is sent unless AgentMail is configured. Two explicit TODOs.
**Files:** `backend/src/agency/routers/team.py`, `backend/src/agency/services/team.py`, `db/init.sql` + `tables.py` (invite table), `frontend/src/app/(dashboard)/team/page.tsx`.
**Do:** signed, expiring invite tokens; org-branded AgentMail template; pending-invite state in the UI; resend + revoke.
**Acceptance:** invite → email link → accept → user joins with the assigned role; the link is single-use and expires.
**Depends on:** — · **Conflicts:** T1.3, T1.4 (schema).

### T4.4 · CI coverage gate + deploy job 🟡 · S
**Why:** `.github/workflows/ci.yml` has no coverage threshold and **no deploy job** — deploys are manual.
**Files:** `.github/workflows/ci.yml`.
**Do:** fail CI under the T4.1 threshold; add a gated `fly deploy` job on `main` (manual approval or tag-triggered), keeping Vercel on its Git integration.
**Acceptance:** a coverage drop fails CI; a tagged commit deploys the backend.
**Depends on:** T4.1.

---

## Phase 5 — Positioning (non-engineering, run in parallel from day 1)

- **T5.1** Confirm ICP: small agencies via white-label (makes T3.1 the flagship) vs self-serve solo marketers. Everything in Phase 3's priority order hinges on this.
- **T5.2** Recruit 3–5 design partners → real logos/quotes to replace the placeholder block on the landing page (T1.6).
- **T5.3** Decide payment rail: the code is Stripe end-to-end with verified webhook signatures (✅ the 260701 P0-3 item is done). If Razorpay is intended for India, that is a new Phase-2-sized workstream — scope it explicitly or drop it.

---

## Already done since the 260701 audit (do not re-scope)

- ✅ Stripe webhook signature verification — `routers/billing.py:77` uses `stripe.Webhook.construct_event`.
- ⚠️ **NOT done — corrected 260817.** Billing / quota / tenancy test *files* exist (`backend/tests/test_billing.py`, `test_quota.py`, `test_tenancy.py`) but **none of them run**: they import `create_org`, `create_subscription`, `auth_header_for` etc. from `tests.conftest`, which only defines `anyio_backend`, `client`, `auth_headers`. They fail at **collection**, which aborts the entire pytest suite before any test executes. The 260701 P0-2 item is therefore still open, and the Stripe-signature verification below is unguarded by any running regression test. → **T0.3**.
- ✅ Real metric-fetching code written (`services/platform_metrics.py`) — **but unwired**, see T1.1.
- ✅ Fabricated testimonials removed from the landing page (placeholder-logo block remains → T1.6).
- ✅ Multi-provider LLM chain with fallbacks + `GET /health/llm` introspection.

## Recommended sequencing

| Weeks | Run |
|---|---|
| 0 | T0.1, T0.2 (parallel) |
| 1–2 | T1.1, T1.2, T1.3, T1.4 (parallel; serialize the two schema tasks) |
| 2–3 | T1.5, then T1.6 alone; T3.0 in parallel |
| 3–4 | Phase 3 fan-out — T3.1…T3.7 (parallel after T3.0; content-page tasks to one agent) |
| 4–5 | T2.1 → T2.2 → T2.3 (serial, same files) |
| 5–6 | T4.1, T4.2, T4.3, T4.4 |

**Fastest path to a stronger demo:** T0.1 → T3.0 → T3.1 (client portal) + T3.3 (autonomous operator). Those three add the most visible capability without touching the pipeline.
**Fastest path to a sellable product:** Phase 1 in full — nothing else matters if the analytics are zeros.

## Open questions

1. ICP confirmed as white-label agencies? Decides whether T3.1 is P0 or P2.
2. Which LLM providers are keyed on Fly prod? (`GET /api/v1/health/llm`, authenticated.) T0.1 assumes at least one.
3. Does Neon have `vector` enabled on your plan? Blocks T1.4's approach.
4. Stripe or Razorpay for launch? T5.3.
5. Do you have Meta app review approval for IG Content Publishing? Without it T2.1 cannot be demoed on a real account.
6. Is `docs/campaignforge-hardening-backlog.md` retired by this doc, or should both live?
