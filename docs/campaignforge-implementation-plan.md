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
- **Green bar, corrected 260817 (second pass):** `ruff check src/ tests/` is now down to **1** finding (`SIM222` in `services/llm_provider.py`) after the lint-config change described in the status section — but `mypy src/agency/ --ignore-missing-imports` still reports **413 errors in 61 files**, almost all `no-untyped-def` / `type-arg` on FastAPI handlers. So the achievable bar per agent is: **clean on the files you touched, and zero new violations repo-wide.** Note that adding a *correct* annotation to previously-unannotated code can itself add a mypy finding — `user: dict` earns `type-arg`. Write `dict[str, Any]`. Do not ask an agent to fix the baseline as a side quest — that is T4.5, and it needs re-scoping.
- `pytest tests/ -v` must pass **in full**. It does as of 260817: **197 passed, 0 errors**. Any agent reporting a subset run is reporting a regression, not a constraint.
- **Schema changes need three edits, not two** (no Alembic in this repo): `db/init.sql`, `backend/src/agency/models/tables.py`, **and** a dated forward-only script in `db/migrations/`. `init.sql` runs only on a fresh database, so without the third file the change reaches local dev and CI, passes review, and silently never lands in Neon prod — which is exactly how four tables and two columns went missing in production until 260818.
- **Data reliability is non-negotiable:** no fabricated metrics. Unavailable data returns an explicit unavailable/`⚠️ NOT AVAILABLE` state, never zeros or invented numbers (`.cursor/workflows/data-reliability-rules.md`).

Legend — Effort: **S** ≤1d · **M** 2–4d · **L** 1–2wk. Impact: 🔴 blocker · 🟠 high · 🟡 medium.

---

## Status — 260817 (revised)

**Phase 0 complete. Phase 1 complete except T1.6.** Verified by running the gates directly, not from agent reports:

| Metric | 260701 baseline | Previously reported | Actual now |
|---|---|---|---|
| Tests passing | 39 (suite aborted at collection) | 172 | **197, 0 errors** |
| ruff `src/ tests/` | 286 | 291 | **1** (see below) |
| mypy `src/agency/` | 427 / 66 files | 410 / 61 | **413 / 61** |

⚠️ **The ruff number moved for a reason unrelated to T1.7, and the working tree is not stable.** `backend/pyproject.toml` gained `[tool.ruff.lint.per-file-ignores]` (E501 on the ten prompt-heavy agent/service modules) and `flake8-bugbear.extend-immutable-calls` (FastAPI `Depends`/`Query`/`Body`/… so B008 stops firing on the DI idiom) **during** this pass, by an edit outside it. That is what took 291 → 1; the one remaining finding is `SIM222` in `services/llm_provider.py`, untouched here. The change looks right — B008 alone was 217 of 294 findings — but it means **T4.5 (fix the ruff baseline) is now largely done and should be re-scoped before anyone picks it up.** Several other files (`services/platform_metrics.py`, `frontend/src/app/page.tsx`) also changed concurrently, so re-measure before trusting any number in this table.

Done: T0.1 · T0.2 · T0.3 · T0.4 · **T0.5** · T1.1 · T1.2 · T1.3 · T1.4 · T1.5 · **T1.7**. Remaining in Phase 1: **T1.6** (stub audit sweep — run last, alone).

Corrections applied to this document on 260817, second pass:

- **"Phase 0 complete" was false when written** — T0.5 was open and absent from the Done list. It is now genuinely done (see T0.5).
- T1.7 was filed under the Phase 0 heading, beneath an empty `Bugs found by the newly-live tests` header. Moved to Phase 1 where it belongs.
- **T1.7-old deleted.** It was marked superseded but remained a complete, valid-looking task block — a hazard in a document whose whole premise is verbatim copy-paste hand-off.
- T2.3 and T2.4 reordered into numeric order.
- Counts corrected: **24 routers · 24 services** (this doc said 23 services; `CLAUDE.md` said 23 routers / 21 modules and has been fixed).
- `backend/tests/test_content_batching.py` exists and passes but was never in this plan — folded into the T1.x record below.

**Operator actions — status as of 260818:**
1. ⬜ Create `backend/.env` from `backend/.env.example` (nothing runs locally without it). Note `extra="forbid"` — one unknown key aborts startup, and blank ≠ unset. **T0.1's acceptance is still unverified**: the example file shipped, but no `.env` has ever been created, so the boot path it describes has not been executed once.
2. ✅ **pgvector is enabled on Neon** — `SELECT extname FROM pg_extension` now returns `vector`, and `knowledge_embedding` exists with its HNSW cosine index. Enabled as a side effect of `db/migrations/260818_schema_catchup.sql`, whose guarded `CREATE EXTENSION IF NOT EXISTS vector` succeeded. **This answers open question 3: Neon does support it on this plan.**
3. ⬜ Run `cd backend && python scripts/index_knowledge_base.py` — deliberately not wired into startup. **Now the only thing between the repo and working semantic RAG**, since the table and extension are in place; until it runs, retrieval is keyword mode and labels itself as such.
4. ⬜ Set `EXA_API_KEY` — gates **both** trends and competitive intel; without it both correctly return unavailable rather than inventing data.
5. ✅ `db/migrations/260817_org_slug.sql` applied to Neon. All 35 orgs backfilled, zero duplicate slugs, unique constraint in place. Seven orgs shared the name "E2E Test Org" — the row-number de-duplication in the backfill is what kept the constraint from failing.
6. ✅ `db/migrations/260818_schema_catchup.sql` applied to Neon. Closed four missing tables and two missing columns; a model-vs-database diff now reports zero drift in both directions.
7. ✅ **LLM providers are live on Fly prod.** `anthropic`, `google`, `openrouter`, and `groq` are all keyed. Verified by resolving the chain inside the machine, not from the secret names: every tier serves `anthropic` primary (`claude-sonnet-5` for brain/worker, `claude-haiku-4-5` for ad_copy/lite) with `google → openrouter → groq` attached as fallbacks, and a real `invoke()` through the chain returned. **Production can run a campaign end-to-end.**
8. ⬜ **`CORS_ORIGINS` was wrong until 260818** and took the app down in the browser while every server-side signal stayed green. It is correct now, with the canonical domain first (that first entry also builds OAuth redirect URIs). `main.py` logs the resolved list as `cors_allowed_origins` at boot — check it before debugging any CORS report.
9. ⬜ **Still unset in prod:** `EXA_API_KEY` (trends + competitive intel stay dark), `TOKEN_ENCRYPTION_KEY` (**OAuth tokens at rest fall back to a built-in dev key — effectively unencrypted in production**), and the Stripe keys (no checkout). The `TOKEN_ENCRYPTION_KEY` gap is the sharpest of the three: it is silent, and it only matters once real users connect real social accounts.

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
**✅ DONE 260817** — both flags removed; `next build` now runs its "Linting and checking validity of types" phase. Nothing needed fixing, because T0.4's lint pass had already cleared the codebase. Gate proven: a `const x: number = 'string'` planted in `src/lib/api.ts` fails the build with `Type error: Type 'string' is not assignable to type 'number'` and exit 1; reverted after.
**Note for whoever hits it next:** clean builds are **intermittently** flaky on this repo with `InvariantError: Expected clientReferenceManifest to be defined` on `/(dashboard)/page` — one failure in four local runs, unrelated to these flags (it reproduces with them on). It is the same Next 15 route-group bug the `vercel.json` workaround patches after the fact, which is no help when the build dies *during* prerender. If CI goes red on that string, re-run before investigating. The `tsc --noEmit` CI step is kept even though `next build` now type-checks: it fails in seconds rather than after a full compile, and covers `e2e/` and config files the build never traces.

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

### T1.7 · Tenant-isolation sweep — 6 routers violated the `org_id` rule 🔴 · M — ✅ DONE 260817
**Why:** the project rule is "every org-scoped query must filter on `org_id`" precisely because **there is no row-level security in this database**. Six routers broke it, found by T0.3's newly-live tests and T3.0's enumeration of all routes.

**Severity was originally mis-ranked. Corrected, with the reasoning, because the ranking is the useful artefact:**

1. 🔴 **`routers/oauth.py` + `routers/publishing.py` — one chained exploit, not two independent gaps.** `oauth_callback` took `client_id` from the request body and attached a `PlatformAccount` to it without checking the client belonged to `org_id`. `publish_now` then selected `PlatformAccount` on `client_id`+`platform`+`status` with **no `org_id` filter**. The original entry rated the second 🟠 and called it "not exploitable today" — that is only true in isolation. Chained: an attacker inserts an account row carrying a victim org's `client_id`, and the victim's next publish either **500s permanently** (two rows reach `scalar_one_or_none()` → `MultipleResultsFound`) or, if the victim has no account connected for that platform, **publishes the victim's content using the attacker's token, to the attacker's social account**. Both halves had to be fixed together; a single-agent hand-off of the 🟠 alone would have left the exploit live.
2. 🟠 (was 🔴) **`routers/comments.py`** — `add_comment` never verified `content_id` belonged to the caller's org. Real, but not a cross-tenant *read*: the row is stamped with the caller's `org_id` and `list_comments` already filtered on it, so the victim could never see the injected comment. It is foreign-key pollution that becomes a leak the first time a query joins comments by `content_id` alone.
3. 🟠 **`routers/portal.py`** — `_resolve_org` fell back to `Organization.name == org_slug` via `scalar_one_or_none()`. `name` is not unique, so two orgs sharing a name 500'd the entire portal, and a name could shadow another org's slug on an **unauthenticated** route. Correctly rated; it blocked T3.1.
4. 🟡 → **not a finding.** `routers/notifications.py` `mark_read` filtered `user_id` but not `org_id`. A user belongs to exactly one org, so `user_id` is strictly narrower than `org_id`. Filter added for consistency, but it defended nothing.
5. 🟡 → **not a security finding.** `routers/reports.py` `list_reports` returns a fixed list of *available report periods* — no client data — so there was nothing to leak. The `client_id` check was added only so probing cannot confirm whether an id exists in another tenant.

**Two further defects found while writing the tests, neither in the original entry:**
- 🔴 **`comments.py` and `notifications.py` were entirely non-functional.** `get_current_user` returns the **JWT payload dict** in both the Clerk and local paths, but both routers did `user.id` on it — `AttributeError` → 500 on every route in both files. `comments.py` also read `user.full_name`, a key the payload has never contained. Neither router had a single test, so this survived to `main`. Fixed by adding `get_current_user_id` to `dependencies.py`; this blocks T3.5, which is built entirely on the comments router.
- `oauth_callback` called `UUID(client_id_fk)` unguarded — a malformed body field raised straight out of the handler as a 500 rather than a 400.

**Also fixed:** `services/billing.py` `_handle_invoice_paid` returned `{"status": "usage_reset"}` even when no subscription matched the Stripe customer. Now returns `{"status": "ignored", "reason": "no_subscription_for_customer"}` and logs a warning.

**Schema change:** `organization.slug` (`VARCHAR(64) UNIQUE`, nullable) added to `db/init.sql`, `models/tables.py` and `db/seed.sql`; slug generation wired into both org-creation paths (`routers/auth.py` signup, `dependencies.py` Clerk auto-provision) via new `utils/slug.py`. Null slug = no portal, which is the fail-closed default. **`db/migrations/260817_org_slug.sql` must be run by hand on Neon** — see operator action 5. This is the first file in `db/migrations/`; the repo previously had nowhere to put a change that `init.sql` alone cannot deliver to an existing database.

**Acceptance — met.** All six routers org-scoped; portal resolves on the unique slug only; unmatched-webhook case distinguishable; **16 new tests in `backend/tests/test_tenancy_routers.py`, every one verified red when its own filter is deleted** (each of the six filters was removed in turn, the matching test run, and the file restored). Suite 181 → 197 passing, ruff clean on all touched files, mypy unchanged at its 413 baseline.
**Not covered — for T4.1:** these tests prove the **denials**. There is still no success-path test for `oauth_callback` or `publish_now` (both need outbound HTTP mocked), so "the fix does not break the happy path" rests on the denial tests plus the `test_comment_on_own_content_succeeds` / `test_report_periods_for_own_client` pair, not on the two routes that matter most.
**Depends on:** T0.3 (done) · **Unblocks:** T3.1 (portal), T3.5 (comments).

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

### T2.3 · Token refresh + per-platform rate limits 🟠 · M
**Why:** OAuth tokens expire and there is no refresh path; publish/metric calls have generic retries but no per-platform rate-limit handling. First long-lived customer breaks silently.
**Files:** `backend/src/agency/routers/oauth.py`, `backend/src/agency/services/publishing.py`, `backend/src/agency/services/platform_metrics.py`, `backend/src/agency/services/scheduler.py`.
**Do:** store refresh tokens (encrypted via existing `utils/encryption`), refresh on 401 and retry once, mark `PlatformAccount.status = "expired"` when refresh fails, and surface that in Settings. Respect `429` + `Retry-After` per platform with backoff.
**Acceptance:** an expired token is transparently refreshed on the next publish; an unrefreshable account flips to `expired` and the Settings page shows a reconnect prompt.
**Note (T1.7):** `oauth_callback` now validates `client_id` against `org_id` **before** the token exchange, and `publish_now` selects `PlatformAccount` with `.order_by(created_at.desc()).first()` rather than `scalar_one_or_none()` — an org may legitimately hold several accounts per client+platform. Preserve both when reworking this path, and add `org_id` to any new account lookup you introduce.
**Depends on:** T2.1 · **Conflicts:** T2.1, T2.2, T1.1.

### T2.4 · Unique constraint on `analytics_snapshot` 🟡 · S — discovered 260817
**Why:** `db/init.sql` (~line 167) has **no unique constraint on `(content_id, date)`**. T1.1's upsert is therefore SELECT-then-update and race-prone if two refreshes for the same post overlap. The single scheduler plus a per-day guard makes this unlikely today, but a partial unique index makes double-measurement impossible rather than merely improbable.
**Files:** `db/init.sql`, `backend/src/agency/models/tables.py`, `backend/src/agency/services/analytics_fetcher.py` (switch to a real upsert), plus a dated script in `db/migrations/` (T1.7 established the directory — `init.sql` alone never reaches an existing database).
**Acceptance:** concurrent refreshes for one post produce exactly one row per day.
**Depends on:** T1.1 · **Conflicts:** schema tasks.

---

## Phase 3 — Ship the built-but-invisible features (highest demo ROI)

> These backends **already work**. They have no UI, so they are invisible in a demo. Mostly frontend work — highly parallelizable, low risk.

### T3.0 · (Prerequisite) Expose remaining endpoints in the API client 🟡 · S
**Files:** `frontend/src/lib/api.ts` only.
**Do:** the client already has `getCrossLearning`, `runCompetitiveScan`, `generateImage`, `createAutonomousCampaign`, `generateOutreach`, `createVideoScript`, `getAuditLogs`, `generateVariants`, `getContentSuggestions`, `getBetaMetrics`, `generateReport`, `getReportPeriods`, comments methods — **none of which any component calls**. Verify each against the live route signature, fix drift, and add the missing ones (portal, webhooks config, white-label, marketplace fork/publish, public API key scopes).
**Acceptance:** every mounted `/api/v1` route has a typed client method or a documented reason it does not.
**Run this alone, first in Phase 3.** After it lands, T3.1–T3.7 are safely parallel.

### T3.1 · Client portal frontend 🟠 · M
**Why:** `routers/portal.py` serves campaigns, content, and client-side content review over `GET/PATCH /api/v1/portal/{org_slug}/...` gated on `WhiteLabel.portal_enabled` — and there is **no frontend for it at all**. This is the single biggest built-but-invisible feature, and it is the white-label wedge for the agency ICP.
**Files:** `frontend/src/app/portal/[orgSlug]/page.tsx` + subroutes (create), `frontend/middleware.ts` (portal routes must be public), `frontend/src/lib/api.ts` (unauthenticated portal client).
**Do:** build a branded, unauthenticated client-facing view: campaign list, content cards, approve/request-changes actions hitting `PATCH /portal/{org_slug}/content/{content_id}`. Pull colors/logo from the white-label branding payload. Add portal paths to the public matcher in `middleware.ts` (currently only `/`, `/sign-in`, `/sign-up`, `/api/webhooks/*` are public).
**Unblocked by T1.7 — read this before starting.** `{org_slug}` is now `Organization.slug`, a **unique** column, and nothing else: the old `domain` → `name` fallback is gone. Consequences for this task: (a) an org with a null slug has no portal and must 404, which is intended, so do not add a name-based fallback in the UI; (b) `db/migrations/260817_org_slug.sql` has to have been run on whatever database you test against or every slug 404s; (c) the white-label editor in T3.7 needs a slug field, since orgs created before the migration are backfilled from `name` and agencies will want to change that. Portal isolation is covered by `test_tenancy_routers.py::test_portal_content_does_not_leak_across_orgs` — extend it rather than starting a new file.
**Acceptance:** with `portal_enabled`, `/portal/{slug}` renders org-branded content and a client can approve a piece without signing in; with the flag off, it 403s cleanly.
**Depends on:** T3.0 · **Conflicts:** T3.2–T3.7 all touch `frontend/src/lib/api.ts` — **serialize the api.ts edits or assign one agent to add all Phase-3 client methods first (T3.0)**.

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
**Note:** "fully built" was wrong until T1.7. Every route in that router 500'd on `user.id` (`get_current_user` returns a dict, not an ORM `User`), so this task would have failed on its first request. Fixed, and covered by `test_tenancy_routers.py::test_comment_on_own_content_succeeds`. The response now resolves `user_name` from the `users` table and falls back to the token email.
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
**Why:** 197 tests for 82 endpoints and 24 services. Billing/quota/tenancy are ✅ covered, and T1.7 added per-router tenancy coverage for oauth, publishing, comments, notifications, reports and portal. The uncovered risk is now the **happy paths** of publishing and OAuth (T1.7's tests only prove the denials), plus the scheduler and the agent nodes.
**Files:** `backend/tests/` (new files per area).
**Do:** add `test_publishing.py`, `test_oauth.py`, `test_scheduler.py`, `test_agents/test_nodes.py`. Mock all outbound HTTP. Extend `test_tenancy_routers.py` rather than starting a third tenancy file. **Every router touched must get at least one success-path test** — T1.7 found that `comments.py` and `notifications.py` had 500'd on every request since they were written, purely because nothing ever called them.
**Acceptance:** ≥60% coverage on `services/`; each router has both a denial and a success test.
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
- ✅ **Now genuinely done (was ⚠️).** Billing / quota / tenancy tests run and pass — T0.3 built the fixture contract they expected. The earlier ⚠️ note stands as the record of why "test files exist" is not the same claim as "tests run": all three aborted at **collection**, taking the whole suite with them.
- ✅ Real metric-fetching code written (`services/platform_metrics.py`) and **wired** by T1.1 — its three internal bugs are owned by T2.2.
- ✅ Fabricated testimonials removed from the landing page. The placeholder-logo block on `frontend/src/app/page.tsx` is **also already gone** (verified 260817) — T1.6 inherits only the audit, not that deletion.
- ✅ Multi-provider LLM chain with fallbacks + `GET /health/llm` introspection.
- ✅ Tenant isolation across all six offending routers, with red/green-proven tests — T1.7.
- ➕ **Not in this plan, but shipped:** `backend/tests/test_content_batching.py`. Untracked work outside the task list is how the count drift in the status table happened; add a task block before starting work, even a retrospective one.

## Recommended sequencing

Struck through where complete. Remaining work only:

| Weeks | Run |
|---|---|
| ~~0~~ | ~~T0.1, T0.2~~ · T0.5 ✅ |
| ~~1–2~~ | ~~T1.1–T1.4~~ · T1.7 ✅ |
| **now** | **T1.6 alone** (stub sweep — closes Phase 1), **T3.0 in parallel** (different files, no conflict) |
| next | Phase 3 fan-out — T3.1…T3.7 (parallel after T3.0; assign all three content-page tasks to one agent) |
| then | T2.1 → T2.2 → T2.3 → T2.4 (serial, same files) |
| then | T4.1, T4.2, T4.3, T4.4 |

**Fastest path to a stronger demo:** T3.0 → T3.1 (client portal) + T3.3 (autonomous operator). T1.7 removed the blocker under T3.1, so the portal is now the shortest route to visible capability — provided the Neon migration is run first.
**Fastest path to a sellable product:** finish Phase 1 — only T1.6 is left, and it is the task that decides whether anything still "looks real and isn't."

## Open questions

1. ICP confirmed as white-label agencies? Decides whether T3.1 is P0 or P2. **Now the most expensive open question in the doc** — T1.7 cleared the portal's blocker, so this is the only thing standing between the agency wedge and being built.
2. ~~Which LLM providers are keyed on Fly prod?~~ **Answered 260818: `anthropic`, `google`, `openrouter`, `groq`.** Anthropic is primary on every tier, the other three are the fallback chain. `GET /api/v1/health/llm` reports this without exposing key material.
3. ~~Does Neon have `vector` enabled on your plan?~~ **Answered 260818: yes, and it is now enabled** — `knowledge_embedding` exists with its HNSW index. Remaining step is running `scripts/index_knowledge_base.py` (operator action 3).
4. Stripe or Razorpay for launch? T5.3.
5. Do you have Meta app review approval for IG Content Publishing? Without it T2.1 cannot be demoed on a real account.
6. ~~Is `docs/campaignforge-hardening-backlog.md` retired by this doc?~~ **Answered by inspection: the file still exists.** Recommendation — delete it. Every live item has been carried into a task block here, and two documents describing the same backlog is exactly how the 427-vs-413 and 23-vs-24 style drift started. Retained only if you want the 260701 audit as a historical record, in which case stamp it `SUPERSEDED — see campaignforge-implementation-plan.md` at the top.
7. **New:** `organization.slug` is backfilled from `name`, so existing orgs get slugs like `campaignforge-demo`. Should agencies be able to edit their portal slug (T3.7's white-label editor), and is a slug change allowed to break existing portal links customers have already been sent?
