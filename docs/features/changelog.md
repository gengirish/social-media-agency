# Feature Changelog

Chronological record of feature changes. Newest first.

---

## 260923 — Cadence full parity

Every Cadence Crew prototype screen now has a CampaignForge route (branch `feat/cadence-parity`; plan and screen map in [`docs/cadence-parity-plan-260923.md`](../cadence-parity-plan-260923.md)). Where Cadence simulated something — OAuth popups, a seeded inbox, browser-side LLM calls, sending — this does it for real or says it is unavailable. Nav order stays Setup, Create, Posts (not Cadence's Setup, Posts, Create).

> **Deploy order:** run by hand on Neon, in order, *before* the backend deploy — `db/migrations/260923_creative_asset.sql`, `260923_amplify_asset_source.sql` (FK to `creative_asset`), `260923_inbox.sql`. Otherwise `/assets`, every Create screen, `/amplify/*` and `/inbox` fail with `UndefinedTable` / `UndefinedColumn`. New optional env vars: `LINKEDIN_INBOX_SCOPE`, `LINKEDIN_API_VERSION` (added to both `.env.example` files).

### Foundation
- **Added**: active client — top-nav `ClientSwitcher` (Cadence's product switcher) backed by `GET /clients/overview` (real per-client setup progress and queue counts); every Create / Posts / Inbox / Insights screen scopes to it.
- **Added**: `/welcome` (adaptive onboarding, then a welcome-back hub; the logo links here), public `/legal` (privacy, terms, AI notice), dashboard footer, keyboard shortcuts `1`–`6` (nav groups) and `?` (help), last-visited sub-tab per group, ambient glows and Cadence motion keyframes.
- **Added**: campaign focus — `PUT/DELETE /clients/{id}/campaign-focus` (`client.settings.campaign_focus`), shown by `CampaignIndicator`, fed to every generator except the PRFAQ.
- **Added**: `creative_asset` table + `/assets` CRUD — stored output of the Create screens (closed `ASSET_KINDS`).
- **Changed**: `services/generation_quota.py` and `services/brand_context.py` extracted from Amplify; every generator now shares one quota (1 generation per successful call), one tenant-scoped client lookup and one brand prompt block.
- **Added**: UI primitives `ErrorBanner`, `ConfirmDialog`, `undoToast` (8 s), `SearchInput`, `PlatformFilterRow`, `CampaignIndicator`.
- **Changed**: nav regrouped — **Setup** (Profile, Clients, Accounts) · **Create** (Campaigns, Content, Email, Launch, Amplify, Ads, Templates) · **Posts** (Queue, Calendar) · **Inbox** · **Insights** · **Settings**.

### Setup
- **Added**: `/setup/profile` — intake (real website scan via Magic Brief, coached audience/differentiator answers, fixed tone register), then Campaign, Brand Voice (generate → edit → approve) and Strategy Lens (saved as an asset). Endpoints `/setup/{client_id}/profile`, `/profile/evaluate-answer`, `/brand-voice/generate`, `/brand-voice`, `/strategy-lens`. Merges column by column; never wipes fields it did not mention.
- **Added**: `/setup/accounts` (moved from `/settings?tab=platforms`, which still resolves) with `GET /setup/{client_id}/accounts`, a scope-listing consent dialog and real provider redirects.
- **Changed**: OAuth — signed `state` (HS256, 15 min, bound to org + platform + client, key **derived** from `JWT_SECRET` so it can never verify as a login token); **PKCE for X** (verifier in `sessionStorage`, HTTP Basic token exchange); LinkedIn requests `LINKEDIN_INBOX_SCOPE` on top of its publishing scopes when set; new in-app return page `app/(dashboard)/api/oauth/[platform]/callback`.

### Posts
- **Added**: `routers/post_studio.py` — `POST /content/generate`, `POST /content` (manual), `POST /content/{id}/regenerate`, `POST /content/{id}/creative-brief`, `DELETE /content/{id}` (409 `published_locked` for published), `GET /post-studio/channels`. Everything created or rewritten is Pending; a draft may carry a *planned* day in `scheduled_at` that the scheduler ignores. Generations are not charged if the caller disconnected.
- **Changed**: `GET /publishing/calendar` gains `client_id` and `include_pending`; items include `hashtags`.
- **Changed**: Queue rebuilt as Cadence's list — sidebar (client card, channels, usage, stats), generate posts, regenerate, creative brief, autosaving Pending edits, bulk approve/publish/delete, delete with undo, run report. Calendar — month/week, drag reschedule gated on approval, keyboard reschedule, add your own post, fill with AI, an honest "This week" panel.

### Create
- **Added**: `/create/content` — niche scan, blog post (keyword memory, AI-search pack, blog-from-gap), comparison page, video script; comparison/scan grounded in Exa research or explicitly marked unavailable.
- **Added**: `/create/email` — 5 lifecycle campaign types; drafts only, nothing is sent.
- **Added**: `/create/launch` — product launch kit, community kit, partnership outreach, and the PRFAQ stress-test (brain tier, stored at `client.settings.prfaq`, ignores the campaign focus; launch kits record `prfaq_addressed`).
- **Added**: `/create/ads` — Google RSA / Meta copy on the ad-copy tier with code-enforced guardrails (`services/ad_guardrails.py`: limits, trademark and personal-attribute risks) and advisory moderation that fails open visibly. Copy and structure only.
- **Changed**: Amplify accepts `source_asset_id` (blog post, comparison page, niche scan, video script, launch kit) — "From Create" source; recorded on `repurpose_pack.source_asset_id` and each committed atom.

### Inbox
- **Added**: `/inbox` — live X mentions and (with `LINKEDIN_INBOX_SCOPE`) LinkedIn comments on CampaignForge-published posts; nothing seeded. Explicit per-account status (`ok`, `not_connected`, `needs_reconnect`, `api_access_denied`, `rate_limited`, `unsupported`, `error`); DMs marked unavailable. Read/handled state in the new `inbox_item_state` table. Reply suggestions (worker tier, message fenced as untrusted). `POST /inbox/reply` posts for real only on a confirmed human click, only to an item in that account's fetched inbox, after moderation (override recorded), and writes `audit_log` — the first caller of `log_action`.

### Insights & Settings
- **Added**: `GET /insights/summary` — per-client funnel, publish/moderation rates, content quality signal, engagement and recommendations, every ratio gated on n ≥ 3 with thresholds shown. `POST /insights/advocacy` — review request / case study / proof line citing only server-supplied counts.
- **Added**: `/workspace/activity` (activity log derived from real rows), `/workspace/export` (client JSON export, no tokens), `/workspace/posting-prefs` (voice register + cadence, fed to every generator). Settings gains per-client tabs: Client profile, Connected accounts, Posting preferences, Plan & usage, Activity log, Export.
- **Changed**: the approval gate records moderation refusals (`moderation_flagged` product event) and pre-approval edits (`metadata.edited_before_approval`) so the quality signal has real data. New server-authored events: `moderation_flagged`, `advocacy_generated`.

### Not replicated
- Cadence's **Reset workspace data** (destructive; a workspace holds many clients), simulated OAuth popups, seeded inbox data.

### Known gaps found while documenting
- `routers/audit.py`'s empty-state reason ("no route writes audit entries") is stale now that Inbox replies are audited.
- OAuth callback verifies `state` only when it is sent; account handles are still the `{platform}_user` placeholder.
- `services/oauth_state.py`'s docstring says it signs with `JWT_SECRET`; the code uses the derived key.
- Amplify's quota hint still says "packs left this period" although the pool is now shared by every generator.
- The workspace export's Amplify packs omit `source_asset_id`.

Tests: `test_foundation.py`, `test_setup_profile.py`, `test_post_studio.py`, `test_create_content.py`, `test_create_email_launch.py`, `test_ad_guardrails.py`, `test_create_ads.py`, `test_inbox.py`, `test_insights_settings.py`; E2E `navigation.spec.ts` asserts the H1 of every new route.

---

## 260922 — Edit, archive and restore clients

- **Added**: client editing: `PATCH /clients/{id}` (partial) and `GET`/`PUT /clients/{id}/brand-profile` (upsert, partial on update). Until now a client's details and brand voice could be set only at creation, and `POST .../brand-profile` failed on a second call. The client page has an **Edit client** form covering both, plus an **About** card (description, website, email) it did not show before.
- **Added**: archive / restore: `POST /clients/{id}/archive[?unschedule=true]`, `POST /clients/{id}/restore`, `GET /clients?archived=true`. Soft delete on the existing `client.is_active`; nothing is removed. Archive refuses with 409 `has_scheduled_posts` while posts are scheduled, unless `unschedule=true`, which returns them to `approved`.
- **Changed**: schedule, publish-now and the scheduler refuse an archived client's posts (409 `client_archived`; the scheduler marks the post `failed`). With the archive rule above, nothing can go live on an archived client's accounts.
- **Changed**: `/clients` has Active / Archived tabs, and the whole client tile opens the detail page (previously only the name was a link). Campaigns and the Queue resolve client names from active + archived clients, so an archived client's posts keep their label.
- Analytics: `client-edit`, `client-archive`, `client-restore`. Tests: `tests/test_client_edit.py`.
- **Fixed**: the scheduler's connected-account lookup did not filter on `org_id` — the same gap closed in `publish_now` on 260817. An account row owned by another tenant but carrying this client's id could have been used to post. Not reachable via the API since the OAuth fix, but the scheduler posts unattended, so it now matches `publish_now`: org-scoped, newest account wins (duplicates used to raise). Tests: `tests/test_scheduler_publish.py`.

---

## 260921 — Magic Brief refuses internal URLs (SSRF)

`POST /api/v1/magic-brief` fetched whatever URL a signed-in user gave it, from inside Fly, following redirects — so `localhost`, the `fdaa::/16` private network or `169.254.169.254` were all reachable, directly or via a public page that redirects there. The fetch now goes through the new `services/url_safety.py`: http/https on ports 80/443 only, every resolved address must be public, redirects are followed by hand and each hop re-checked, bodies are capped at 2 MB. A refused URL returns 400 with a readable reason and never reaches the LLM. Tests: `tests/test_url_safety.py`.

Known gap: DNS rebinding is not closed. `webhook_dispatcher` and `slack_integration` still POST to user-configured URLs unguarded.

---

## 260921 — Read website on the Clients form

**The website-reading AI now lives on `/clients`.** `POST /api/v1/magic-brief` already extracted a brand profile from a URL, but only `/campaigns/new/magic-brief` called it — adding a client by hand meant typing everything and never capturing a brand voice. The New Client form now has a **Read website** button that drafts brand name, industry and description and previews voice and target audience. Nothing saves until the user presses Create Client, which also stores the extracted brand profile.

By default a read only fills empty fields or fields the previous read filled, so typed values survive a re-read; a **Replace details I've already typed** checkbox lets it overwrite them.

**Removed:** the `/campaigns/new/magic-brief` page, its sessionStorage hand-off banner on `/campaigns/new`, and `e2e/magic-brief.spec.ts` (replaced by an LLM-gated test in `e2e/clients.spec.ts`). Analytics: `magic-brief-client-create` is gone; `client-website-read` is new, and `client-create` carries `from_website_read`.

---

## 260921 — Cadence Port: Design System, Approval Gate, Queue, Amplify

Ports the *design and flow* of the Cadence Crew prototype (not its code) — plan and open decisions in [`docs/cadence-port-plan-260921.md`](../cadence-port-plan-260921.md). Phases 0–5 shipped; phase 6 (authenticated client portal) is not started.

### Approval gate (phase 2) — behaviour change

Publishing posts to live X/LinkedIn/Facebook accounts, and until now nothing stood between a draft and that: `PATCH /content/{id}` accepted any status string, `schedule` and `publish` accepted any piece, and approve set `approved` unconditionally. Now (plan §4):

- **`POST /content/{id}/approve` moderates first** (`services/moderation.py`, brain tier). Issues → 409 `moderation_flagged`; `?override=true` approves anyway and records `override_by`/`at` in `metadata.moderation`. Only `draft`/`rejected` can be approved (409 `invalid_status`). LLM failure **fails open** as `moderation.status = "unavailable"` with a `moderation_unavailable` log; the character-limit and excluded-vocabulary checks are code-level and still flag without the LLM.
- **Schedule and publish-now accept only `approved`/`scheduled`** → otherwise 409 `not_approved`. This includes `published`: the old idempotent 200 for an already-published piece is now a 409.
- **`PATCH /content/{id}`** can set `status` only to `draft`/`rejected`; editing body/hashtags of approved or scheduled content resets it to `draft`.
- **Portal approve** runs the same moderation, never with override.

**Behaviour change:** anything scripted to schedule or publish drafts now gets 409s. A publish that failed leaves the piece `failed`; to retry, PATCH it to `draft` and re-approve (the UI has no retry action). A `published` piece cannot change status (409 `published_locked`), so it cannot be reopened and posted twice. Scheduling Instagram/TikTok returns 409 `platform_unavailable`.

### Design system + IA (phases 1, 5)

- **Added**: Cadence tokens in `tailwind.config.ts` — every colour a CSS variable, light on `:root`, dark on `.dark`; `slate`/`white`/`indigo` and 12 status hues remapped so existing pages theme without a rewrite; semantic `canvas`/`panel`/`ink`/`muted`/`line`/`accent`/`on-accent`. Inter / Space Grotesk / IBM Plex Mono via `next/font`.
- **Added**: light/dark themes — OS preference by default, toggle in the nav/landing/auth screens, stored in `localStorage` (`cf-theme`), applied before first paint by `THEME_INIT_SCRIPT`. Clerk widgets themed via `lib/clerk-appearance.ts`. AA focus ring.
- **Added**: `components/ui/*` primitives (Button, Panel, PageHeader, SectionCard, StatCard, EmptyState/Notice, Field, SegmentedTabs, StatusBadge, CampaignStatusBadge, QuotaHint, AuthCanvas).
- **Changed**: left sidebar → sticky top nav (`components/layout/app-nav.tsx`, data in `lib/navigation.ts`) with groups Setup · Posts · Create · Insights · Settings and sub-tabs. Routes unchanged; Setup › Accounts is `/settings?tab=platforms`, and Settings tabs now live in `?tab=`.
- **Changed**: every dashboard page, the landing page (now a Server Component; placeholder logos/testimonials removed) and sign-in/up restyled.
- **Changed**: `draft` is labelled **Pending** everywhere in the UI. DB value unchanged.

### Posts › Queue (phase 3)

- **Changed**: `/content` is now the Queue (H1 "Queue", was "Content Library"): status tabs Pending · Approved · Scheduled · Published · Failed with counts, client/platform filters, moderation-aware approve with "Approve anyway", schedule picker (the first UI to call `POST /publishing/{id}/schedule` outside the calendar), publish-now confirm, failed-publish reason, Amplify deep link. Components in `components/posts/*`.
- **Removed**: the Repurpose dialog and Suggestions tab from `/content`.
- **Not built**: bulk select, delete and undo — there is no content `DELETE` endpoint. `rejected` posts have no tab.
- **Changed**: Calendar restyled; drag-to-reschedule kept.

### Amplify (phase 4)

- **Added**: `POST /amplify/preview`, `POST /amplify/{pack_id}/commit`, `GET /amplify/packs` (`routers/amplify.py`) — one source → up to 8 drafts on distinct angles from a closed taxonomy; preview saves nothing, commit writes kept atoms as Pending drafts only. Worker tier at 0.8 (`agents/amplify.py`); pure helpers in `services/repurpose.py`. The prompt now reads brand `example_posts`, previously unused.
- **Added**: `repurpose_pack` table; `subscription.generations_used` / `generations_limit`. **Run `db/migrations/260921_amplify.sql` on Neon before deploying the backend.**
- **Added**: generation quota — 1 pack = 1 generation; `PLAN_CONFIG` limits free 10 / starter 50 / growth 250 / agency 9999; 402 `generation_quota_exceeded`; reset on `invoice.paid`; failed generations charge nothing. Reported by `GET /billing/subscription`.
- **Added**: server-authored product events `amplify_pack_generated`, `amplify_pack_committed`; frontend `trackFeature("amplify")`.
- **Added**: `/amplify` screen (`components/amplify/*`) under Create — form, cancel, review grid, pack history, `?source=` deep link.
- `POST /content/{id}/repurpose` stays for API compatibility; the UI no longer calls it.

### Other

- **Fixed**: pipeline failures are now logged (`campaign_pipeline_failed`, `campaign_mark_failed_error`) instead of only being streamed.
- **Docs**: `websocket.md` — `step_start`/`step_update` are declared but never emitted by the backend; one consumer per stream queue. `api-endpoints.md` — `GET /content` filters on `content_status`, not `status`. Counts: 86 endpoints / 25 routers / 27 service modules / 22 tables.

**Known gaps, not fixed here:** quota check-then-increment race; Cancel on Amplify does not refund a generation the server finished; Free orgs never get `invoice.paid`, so their `posts_used` and `generations_used` never reset; Amplify output quality not yet eyeballed on a live LLM; the Approve button on the campaign detail page does not handle the new 409; landing and in-app plan copy disagree for Free.

---

## 260818 — Groq Provider + Production LLM Activation

**`groq` added as a seventh LLM provider.** It is OpenAI-compatible but had no home here, so a `GROQ_API_KEY` had nowhere to go. Registering it took **two** edits, not one: a `ProviderSpec` *and* an entry in `DEFAULT_PROVIDER_ORDER`. `_configured_order()` filters names against that tuple, so a provider with settings and a spec but no entry there is dropped from the order silently — no error, no log, it simply never gets picked. A test now asserts groq is selectable by explicit order, which is what fails if a future provider is added the same half-way.

Two Groq specifics, both documented in `.env.example`:

- Its OpenAI-compatible surface is under **`/openai/v1`**, not `/v1` — the usual base-URL shape 404s every call.
- It retires model ids faster than the other gateways, and a stale id surfaces as a 404 that reads exactly like a bad key. Change `GROQ_MODEL` before suspecting the key.

Placed last in the default order so no existing deployment's primary provider changes.

**Production LLM chain is live.** `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, and `GROQ_API_KEY` are all set on Fly. Verified by resolving the chain *inside* the running machine and issuing a real `invoke()` — not by reading secret names, which only prove a value exists:

| Tier | Primary | Fallbacks |
|---|---|---|
| brain / worker | `anthropic` · `claude-sonnet-5` | google → openrouter → groq |
| ad_copy / lite | `anthropic` · `claude-haiku-4-5` | google → openrouter → groq |

**Docs corrected against the code**, several of which had drifted:

- The tier count was documented as **three**; there are **four** — `lite` (`get_lite_llm()`) serves SEO keyword extraction, content repurposing, and A/B variants. It is for work that transforms text it is handed rather than deciding anything.
- `services.md` and `integrations.md` listed **retired** Anthropic defaults (`claude-sonnet-4-20250514`, `claude-3-5-haiku-20241022`); the code had already moved to `claude-sonnet-5` / `claude-haiku-4-5`.
- Provider counts and the default order string updated in `CLAUDE.md`, `services.md`, `integrations.md`, and `README.md`.

**Still unset in production:** `EXA_API_KEY` (trends and competitive intel stay dark) and `TOKEN_ENCRYPTION_KEY` — the latter falls back to a built-in dev key, so OAuth tokens at rest are effectively unencrypted in prod. Silent, and it only bites once real users connect real social accounts.

---

## 260818 — AgentMail Turned On: `alerts@intelliforge.tech`

**The AgentMail integration existed on paper and sent nothing.** A key, two org columns, and one inline SDK block in `routers/team.py` guarded by `if settings.agentmail_api_key and org.agentmail_inbox_id`. Nothing in the codebase ever *wrote* `agentmail_inbox_id`, so the second condition was false for every org that has ever existed and the send path was unreachable.

**New `services/email_service.py`** is now the single outbound path. `send_email()` resolves a sender — the org's own `agentmail_inbox_id` when set, otherwise a shared inbox from `AGENTMAIL_FROM_EMAIL` (default `alerts@intelliforge.tech`) — and get-or-creates it once per process. It uses `AsyncAgentMail`, so a send does not block the event loop.

**It never raises and never lies.** Every failure mode — no API key, no usable inbox, an AgentMail 5xx — returns `SendResult(sent=False, reason=...)`. A notification that fails must not fail the request that triggered it, and the caller must not be able to report success by accident. `POST /api/v1/team/invite` still returns `email_sent: bool`, now sourced from that result.

**The frontend was deciding success by string-matching backend copy** — `res.message?.includes("Invitation email sent")` — because `email_sent` was missing from `TeamInviteResponse` in `lib/api.ts`. Field added, string-match replaced with the boolean.

**`agentmail` floor raised `>=0.2.0` → `>=0.4.12`.** The installed SDK takes `inboxes.create(request=CreateInboxRequest(...))`; the keyword form both the mirrored `agency-agentmail` skill and the old floor implied raises `TypeError`. The skill is corrected in `.claude/` and `.cursor/`.

**Verified against the live account, not by inspection:** `intelliforge.tech` reports `VERIFIED`, `alerts@intelliforge.tech` already exists, and a real message sent through `send_email()` returned `sent=True`.

Ten new tests in `tests/test_email_service.py` cover the no-key path, the no-sender path, the org-inbox override, payload construction (unset optionals must be absent, not `None` — the SDK serializes an explicit `None`), and outage degradation.

**Not sending in production yet:** `AGENTMAIL_API_KEY` still has to be set as a Fly secret on `campaignforge-api`.

Suite: 214 passing.

---

## 260818 — Schema Catch-Up: init.sql Was Wrong and Production Was Behind It

**Production was missing four tables and two columns that `models/tables.py` declares.** SQLAlchemy names every mapped column in its `SELECT`, so one absent column takes out an entire route rather than degrading: the client portal returned 500 on `white_label.portal_enabled`, and every notifications route failed on a `notification` table that has never existed anywhere.

**Two of the gaps were in `db/init.sql` itself**, so a fresh database would also have been wrong:

- `notification` was declared in `models/tables.py` and never in `init.sql` at all.
- `white_label` never gained `portal_enabled` or `email_from_name`.

Both fixed. An audit of all 21 models against `init.sql` now reports zero missing tables and zero missing columns in either direction.

**New:** `db/migrations/260818_schema_catchup.sql` brings already-provisioned databases up to date — the two `white_label` columns, `notification`, and the `webhook` / `webhook_delivery` pair that shipped in `init.sql` with T1.3 but never reached Neon. `knowledge_embedding` is included behind the same pgvector guard `init.sql` uses.

**Verified against throwaway Postgres containers, not by inspection:**

| Case | Result |
|---|---|
| Fresh DB + new `init.sql` | clean, 20 tables (21 with pgvector) |
| Migration re-run on a current DB | clean no-op |
| Production simulated at 17 tables + migration | 20 tables, 219/219 non-pgvector model columns present |
| Same on `pgvector/pgvector:pg16` | 21 tables, `knowledge_embedding` + HNSW cosine index |

**Applied to Neon.** Model-vs-database diff now reports zero drift. The portal went from 500 to a correct `403 Portal not enabled`; notifications returns 401 rather than 500.

**pgvector is now enabled on Neon** — the guarded `CREATE EXTENSION IF NOT EXISTS vector` succeeded, answering a long-standing open question about whether the plan supports it. `knowledge_embedding` exists with its index; running `scripts/index_knowledge_base.py` is all that stands between the repo and semantic RAG.

**Process rule, now documented in `docs/features/database-schema.md` and `CLAUDE.md`:** a schema change takes **three** edits — `init.sql`, `tables.py`, and a dated script in `db/migrations/`. `init.sql` only ever runs against an empty database, so skipping the third means the change passes CI and silently never reaches production.

Suite: 204 passing.

---

## 260817 — Tenant Isolation Sweep (T1.7) + Frontend Build Gate (T0.5)

**Security — six routers were not enforcing `org_id`.** There is no row-level security in this database, so each missing filter was the isolation boundary itself.

- `routers/oauth.py` — `oauth_callback` trusted the request-body `client_id` and attached a `PlatformAccount` to it without checking the client belonged to the caller's org. Now resolved against `org_id` *before* the token exchange, with a 400 for a malformed id (it previously raised a 500 out of the handler).
- `routers/publishing.py` — `publish_now` selected `PlatformAccount` on `client_id`+`platform`+`status` with no `org_id`. Combined with the above this was live, not theoretical: an attacker could insert an account row carrying a victim's `client_id`, and the victim's publish would either 500 permanently (`scalar_one_or_none` on two rows) or post their content using the attacker's token. Now org-scoped and ordered `created_at DESC` with `.first()`, since one org may legitimately hold several accounts per client+platform.
- `routers/comments.py` — `add_comment` did not verify `content_id` belonged to the caller's org.
- `routers/notifications.py` — `mark_read` filtered `user_id` but not `org_id`.
- `routers/reports.py` — `list_reports` accepted `client_id` and checked nothing.
- `routers/portal.py` — `_resolve_org` fell back to non-unique `domain` and `name` columns on an **unauthenticated** route.

**Bugs found while writing the tests:** `routers/comments.py` and `routers/notifications.py` were entirely non-functional — both did `user.id` on the value from `get_current_user`, which returns the JWT payload **dict** in both auth modes. Every route in both files returned 500. New `get_current_user_id` dependency in `dependencies.py`; `comments.py` now resolves the author's display name from the `users` table instead of reading a `full_name` key the payload never had.

**Schema:** `organization.slug` (`VARCHAR(64) UNIQUE`, nullable) added to `db/init.sql`, `models/tables.py`, `db/seed.sql`. New `backend/src/agency/utils/slug.py` generates slugs on both org-creation paths (local signup, Clerk auto-provision). **`db/migrations/260817_org_slug.sql` must be run by hand on existing databases** — `init.sql` only executes on a fresh one. This is the first entry in a new `db/migrations/` directory.

**Also:** `services/billing.py` `_handle_invoice_paid` no longer reports `usage_reset` when no subscription matched the Stripe customer; it returns `{"status": "ignored", "reason": "no_subscription_for_customer"}` and logs a warning.

**Tests:** `backend/tests/test_tenancy_routers.py` — 16 cases, each verified to fail when its own filter is deleted. Suite 181 → **197 passing**.

**Frontend (T0.5):** `typescript.ignoreBuildErrors` and `eslint.ignoreDuringBuilds` removed from `next.config.mjs`. `next build` now type-checks and lints; a planted type error fails it with exit 1. Nothing needed fixing — T0.4's lint pass had already cleared the codebase.

---

## 260817 — Documentation Reconciliation

Docs-only pass. No application code changed. Every count re-derived from source rather than carried forward.

- **Fixed**: Endpoint total was 86 across 21 routers; actual is **82 across 24 routers**. The per-router tables in `api-endpoints.md` were already correct — only the footer and index were wrong
- **Fixed**: `services.md` plan limits contradicted `billing.md`. `services.md` claimed free 2 clients/30 posts, starter 5/100, growth 15/500 — all wrong. `PLAN_CONFIG` is 1/30, 3/200, 10/1000, unlimited. `billing.md` was right
- **Fixed**: `database-schema.md` header said 17 tables while listing 18; actual is **18**
- **Fixed**: Counts across the index — services 21 → **23**, frontend pages 19 → **17**, agent nodes 11 → **9 graph nodes** (7 LLM agents + `human_review` + `compile_output`), integrations 5 → **7**
- **Fixed**: Next.js 14 → **15.5**, React 19, Clerk 7 in `frontend-pages.md` and root `README.md`
- **Fixed**: Root `README.md` project structure was badly stale — claimed 10 routers/36 endpoints, 8 services, 15 tables, 15 pages, 8 agent nodes, Gemini 2.0 Flash
- **Fixed**: `services.md` described `_decrypt_token` as a passthrough stub; it now performs real decryption
- **Added**: `[STUB]` status label and a **Feature Honesty** table in the index, marking every feature whose route works but whose data is placeholder — analytics metrics, trends, RAG, Instagram publish, Instagram metrics (hardening backlog P0-4)
- **Added**: `services.md` entry for `services/platform_metrics.py` — real X/LinkedIn/Facebook fetchers, written but **imported by nothing**; documents the `unavailable`-not-zeros contract that integration must honour
- **Added**: `billing.md` section documenting Stripe webhook signature verification as implemented (raw body + `construct_event`, 503 when unconfigured, 400 on missing/invalid signature) — P0-3 is satisfied in code
- **Added**: `auth-and-rbac.md` middleware stack table and an explicit warning that there is **no row-level security** — isolation depends entirely on every query filtering `org_id`
- **Added**: `frontend-components.md` entries for `AnalyticsTracker` and `lib/analytics.ts`, both previously undocumented
- **Added**: `integrations.md` entries for fal.ai image generation (verified live — real call to `queue.fal.run/fal-ai/flux/schnell`) and Slack; LLM table corrected from 3 providers to **6**, reframed as per-tier fallback chains rather than per-agent assignment
- **Added**: `integrations.md` note that `EXA_API_KEY` is configured but read by no service
- **Added**: `billing.md` note that `STRIPE_PRICE_STARTER` / `_GROWTH` / `_AGENCY` are read by `config.py` but absent from `.env.example`
- **Added**: `workers.md` notes on `_mark_campaign_failed` and the silent `MemorySaver` checkpointer fallback
- **Changed**: `frontend-pages.md` root `/` was documented as an auth redirect; it is a ~541-line marketing landing page. Its placeholder logos and testimonials are self-labelled "Placeholder" in the UI, but the "Trusted by teams who ship campaigns weekly" heading still asserts traction that does not exist (P1-1)
- **Note**: `websocket.md` already described SSE correctly. The filename is the only WebSocket artefact left; added a header note rather than renaming

## 260729 — Multi-Provider LLM Chain

- **Added**: Six LLM providers — `anthropic` and `google` via native SDKs, plus `openai`, `nvidia` (NIM), `openrouter`, and `bonsai` as OpenAI-compatible endpoints through `ChatOpenAI(base_url=...)`. No new dependencies
- **Added**: Runtime failover — the primary provider for a tier attaches every other configured provider via LangChain `.with_fallbacks()`, so a transient gateway 503 no longer fails a campaign
- **Added**: `LLM_PROVIDER_ORDER`, `LLM_{TIER}_PROVIDER` (pins a tier, disabling its fallbacks), `LLM_{TIER}_MODEL` (primary only — model ids are provider-specific)
- **Added**: `GET /api/v1/health/llm` — resolved provider, model, and fallback chain per tier; never returns key material
- **Added**: `GEMINI_API_KEY` accepted as an alias for `GOOGLE_API_KEY`
- **Changed**: Default Gemini model `gemini-2.0-flash` → `gemini-2.5-flash`. 2.0-flash returns HTTP 429 (quota exceeded) on current free-tier keys
- **Changed**: NVIDIA NIM default model is `deepseek-ai/deepseek-v4-flash`; `meta/llama-4-maverick-17b-128e-instruct` reached end of life 2026-07-27 and returns HTTP 410
- **Fixed**: With no provider key set, the old code built a client with an empty API key and died inside the first agent. `get_llm()` now raises immediately, naming the variables to set
- **Fixed**: `GET /api/v1/health/db` always returned 500 — SQLAlchemy 2.x rejects a bare `"SELECT 1"` string; now wrapped in `text()`

## 260728 — Product Analytics for Beta Metrics

- **Added**: `product_event` table + `ProductEvent` model — usage event stream, separate from `audit_log` (compliance) — with indexes on org/name/user/campaign/session
- **Added**: `services/product_analytics.py` — event capture (`track`, `track_detached`) and every metric in `docs/beta-testing-plan.md` §7: time-to-first-campaign, campaign completion/failure rate, agent step drop-off funnel, feature adoption, session duration, D1/D7/D14 return rate, errors by endpoint
- **Added**: `POST /api/v1/events` — batched browser ingest, allowlisted to four client-writable event names so a client cannot inflate pipeline counts; client timestamps clamped to server now
- **Added**: `GET /api/v1/beta-metrics` — §7 dashboard, always org-scoped (cross-tenant rollup is not exposed over HTTP)
- **Added**: `RequestMetricsMiddleware` — in-memory request/error counters for true error rates, plus persisted 4xx/5xx events (401/404 skipped as noise)
- **Added**: Frontend `lib/analytics.ts` + `AnalyticsTracker` mounted in the dashboard layout — session lifecycle, page views, `trackFeature()` on campaign create, client create, magic-brief client create, and content publish
- **Fixed**: A crashed pipeline left its campaign stuck in `running` forever. `_mark_campaign_failed` now moves campaign and workflow to `failed` and records the failure, so the failure-rate metric reflects reality

## 260328 — 40-Feature YC Implementation (Phases 1-4)

### Phase 1: "Make Them Pay"
- **Added**: Stripe production wiring — configurable Price IDs via env vars, campaign quota enforcement (402 on limit)
- **Added**: Settings backend — GET/PATCH org settings, platform accounts listing
- **Added**: Calendar drag-and-drop — HTML5 DnD rescheduling, week view toggle, platform color coding
- **Added**: One-click repurpose — POST /content/{id}/repurpose for platform-adapted variants
- **Added**: Client reports — POST/GET /reports/clients/{id} with period-based report generation
- **Added**: OAuth connect flow — GET/POST /oauth/{platform}/authorize|callback for X/LinkedIn/Meta
- **Added**: Publishing enhancements — retry logic (3 attempts), token decryption stub

### Phase 2: "Make Them Stay"
- **Added**: Analytics agent wired into LangGraph pipeline (compile_output → analytics → END)
- **Added**: Performance feedback loop — analytics_fetcher service, GET /content/{id}/analytics
- **Added**: Campaign templates — GET/POST /templates/{id}, launch from template
- **Added**: Content A/B variants — POST /content/{id}/variants with variant grouping
- **Added**: Comment threads — full CRUD on content comments
- **Added**: Notification system — model, service, router, NotificationsBell component in header
- **Added**: Content recycling — GET /content/suggestions for top performers
- **Added**: Trend intelligence — GET /campaigns/trends, platform-specific trending topics

### Phase 3: "Make It Defensible"
- **Added**: Brand intelligence dashboard — GET /brand-analytics/clients/{id}/intelligence
- **Added**: Cross-campaign learning — GET /brand-analytics/cross-learning, industry benchmarks
- **Added**: RAG knowledge base — keyword retrieval from 171 marketing skills, wired into strategy agent
- **Added**: Multi-language content — target_languages in CampaignState, content writer language adaptation
- **Added**: Visual content generation — POST /content/{id}/generate-image via fal.ai
- **Added**: White-label portal — portal_enabled, GET/PATCH /portal/{org_slug}/...
- **Added**: Template marketplace — marketplace listing, fork, publish endpoints
- **Added**: Slack bot — /integrations/slack/events + /commands
- **Added**: REST API — API key auth middleware, X-API-Key header, /public/* routes
- **Added**: Webhooks — register/list/delete webhook config
- **Added**: Competitive intelligence — POST /competitive/clients/{id}/scan

### Phase 4: "Moonshots"
- **Added**: Autonomous campaign operator — POST /campaigns/autonomous, goal-driven weekly cycles
- **Added**: Client acquisition engine — POST /acquisition/outreach, 3-email sequences
- **Added**: Bid optimization service — LLM-based ad performance analysis
- **Added**: Video/podcast script agent — POST /content/video-script (TikTok/YouTube/Reels/Podcast)
- **Added**: Enterprise audit log — AuditLog model, log_action service, GET /audit

### Infrastructure
- **New files**: ~20 backend modules (routers, services, agents), 4 frontend pages/components
- **Modified**: ~20 existing files
- **New DB tables**: Notification, AuditLog
- **New env vars**: 10 (OAuth keys, fal.ai, Slack, Exa)
- **Route count**: 38 → 83 endpoints
- **Service count**: 8 → 20

## 260324 — End-to-End Multi-Agent Pipeline Fixes

- **Fixed**: SSE stream auth — accepts JWT via `?token=` query param for EventSource compatibility
- **Added**: AgentRun tracking — inserts DB row per agent node completion during campaign pipeline
- **Added**: Human review UI — approve/revise buttons in LiveAgentDashboard with PATCH to backend
- **Added**: Brand learning wiring — `update_brand_learnings()` called on campaign completion
- **Changed**: Analytics page — replaced "Coming Soon" with real KPI dashboard (stats, content pipeline, campaign status, agent metrics)
- **Changed**: Settings page — replaced static cards with tabbed UI (General, Platforms, API Keys, Notifications)
- **Changed**: Agent stream client — uses Clerk token parameter instead of localStorage
- **Fixed**: CI pipeline — removed `continue-on-error: true` so failures are caught
- **Changed**: Team invite — honest response message + best-effort AgentMail email
- **Added**: Full feature documentation — all 10 feature doc files created from codebase scan

## 260324 — Clerk Authentication Integration

- **Added**: Clerk JWT verification (RS256 + JWKS) in backend `get_current_user`
- **Added**: Auto-provisioning of users/orgs on first Clerk login
- **Added**: `ClerkTokenSync` component to wire Clerk tokens into API client
- **Added**: Clerk middleware for frontend route protection
- **Added**: E2E test auth via Clerk sign-in tokens (bypasses instance-level MFA)
- **Changed**: `get_org_id` fallback to user dict for Clerk sessions

## 260324 — Feature Documentation Initialized

- **Added**: `feature-docs` skill — Living documentation system
- **Added**: `docs/features/` directory — Central location for all feature documentation
