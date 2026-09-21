# Cadence Crew → CampaignForge port plan (260921)

## Status (260921)

**Phases 0–5 shipped** on `feat/cadence-integration`. **Phase 6** (authenticated client portal) is **pending scoping** — nothing built. What shipped is documented in `docs/features/` (changelog entry 260921).

Where the build differs from the plan below:

- **Accounts** tab is `/settings?tab=platforms`, not `/settings#accounts`; Settings tabs moved into `?tab=`.
- **Amplify commit** is `POST /amplify/{pack_id}/commit` with `{atoms}` only — client, source and platforms come from the `repurpose_pack` row written by preview, not from the request. A third endpoint, `GET /amplify/packs`, backs the history list.
- **Migration** is `db/migrations/260921_amplify.sql` (one file for the table and the quota columns).
- **Queue** shipped without bulk select, delete, or undo-delete (no `DELETE` endpoint exists); sonner undo toasts were not built.
- **Amplify deep link** is on Queue cards only — campaign detail content cards have none.
- `drip_schedule()` is built and tested but **not wired** into the schedule picker, even as a suggestion.

### Open decisions

1. **Failed-publish retry path.** A `failed` post has no action in the Queue. The only API path is `PATCH status=draft` → re-approve (re-moderates) → schedule/publish. Decide: a Retry button over that path, a dedicated retry endpoint, or leave it.
2. ~~**Published posts can be reopened via PATCH.**~~ **Fixed 260921:** a `published` piece can no longer change status (409 `published_locked`). Scheduling Instagram/TikTok is now refused server-side too (409 `platform_unavailable`), not only in the UI.
3. **No content DELETE endpoint.** The Queue has no delete or undo; drafts can only be rejected (and `rejected` has no Queue tab, so rejected posts vanish from the UI).
4. **Magic Brief is unlinked in the UI.** `/campaigns/new/magic-brief` works and was restyled, but nothing links to it. Link it from New Campaign / Clients, or retire it.
5. **Landing vs in-app plan copy.** Landing Free card says "30 posts / mo"; in-app `/pricing` says "5 campaigns / mo". Both are real `PLAN_CONFIG` values, but pick one headline allowance per tier. Neither surface mentions the Amplify pack allowance.
6. **Quota race.** Amplify checks `generations_used < limit` and increments later in a separate statement; concurrent previews at the boundary can overshoot. Options: conditional `UPDATE … WHERE generations_used < limit RETURNING`, or a row lock. Related: Cancel in the UI does not stop the server, so a finished generation is still charged; Free orgs never receive `invoice.paid`, so their counters never reset.
7. **Amplify output quality not yet eyeballed on a live LLM.** Tests stub the model; structural guards (angles, char limits, duplicate warnings) are covered, blandness is not. Needs a review pass on real generations before it is sold.

---

Source: `cadence-crew-handoff.zip` — a single-file React prototype (`code.jsx`, ~8.2k lines,
browser-side LLM calls, localStorage state) plus `CREW_AMPLIFY_SPEC.md` and `CREW_CONTEXT_PACK.md`.

Scope approved: **visual design system, app structure/IA, Amplify repurposing, dev rules.**

We port the *design and the flow*, not the code. Cadence has no backend, so every agent it has
must be rebuilt as a FastAPI service + LangGraph/LLM-tier call here. Its localStorage state,
simulated OAuth and direct browser→Anthropic calls are **not** ported — CampaignForge already
has the real versions of all three.

---

## 1. What changes, in one table

| Cadence concept | CampaignForge today | After port |
|---|---|---|
| Dark navy glass + amber accent, Space Grotesk / Inter / Plex Mono | Light slate/indigo, system font | Cadence palette as CSS-variable Tailwind tokens, fonts via `next/font` |
| Sticky top nav, 6 groups, sub-tabs | Left sidebar, 9 flat links | Top nav with 5 groups + sub-tabs (§3) |
| Every draft → **Pending** → moderation → approve | `draft` → approve (no check) → schedule/publish from *any* status | Moderation runs on approve; schedule/publish **require** `approved` (§4) |
| Amplify: 1 asset → ≤8 angle-distinct drafts | `/content/{id}/repurpose`: 1 per platform, lite tier, no brand voice, no angles | New Amplify agent + preview/commit endpoints + screen (§5) |
| Undo toast, QuotaHint, CampaignIndicator chip | Confirm/none, no usage UI | sonner undo toasts, usage hint from `/billing/subscription` |
| Non-negotiable rules | Data-reliability rule only (marketing layer) | Product rules section in `CLAUDE.md` (§6) |

## 2. Explicitly NOT ported

- **Inbox** — no mentions/DM data source exists. Building the screen would mean faking data (Cadence rule #1). Revisit once a real listening integration exists.
- **Email / Launch / Ads / Niche Scan / Brand Voice / Strategy Lens agents** — separate features, not "the flow". Ads already exists as `ad_copy`. Can be ported one at a time later.
- **Keyboard shortcuts `1`–`6`, product switcher** — the switcher's equivalent is client selection; shortcuts are a cheap follow-up.
- **Drip-scheduling of Amplify packs** — deferred in Cadence's own spec; `drip_schedule()` is built and tested but only wired as a *suggestion* in the schedule picker.

## 3. Information architecture

Routes stay where they are (E2E `navigation.spec.ts` asserts URL + H1 per page), only the nav regroups.
One new route: `/amplify`.

| Group | Sub-tabs → existing route |
|---|---|
| **Setup** | Clients `/clients` · Accounts `/settings#accounts` |
| **Posts** | Queue `/content` · Calendar `/calendar` |
| **Create** | Campaigns `/campaigns` · Templates `/templates` · Amplify `/amplify` (new) |
| **Insights** | Analytics `/analytics` |
| **Settings** | Workspace `/settings` · Team `/team` · Billing `/pricing` |

`/content` becomes **Posts → Queue**: status tabs *Pending · Approved · Scheduled · Published · Failed*,
bulk select, approve-with-moderation, schedule picker (the first UI that calls `scheduleContent` —
none does today), undo-delete. H1 changes from "Content Library" → update `navigation.spec.ts` in the same PR.

## 4. Approval gate (backend) — the load-bearing change

Cadence rule 3: *moderation runs before approval, always*. Here publishing is **real** (X, LinkedIn,
Facebook), so an ungated path posts to a client's live account.

- Keep `draft` as the DB value; the UI labels it **Pending**. No status rename migration.
- New `services/moderation.py::moderate_content(piece, brand_context)` — `get_brain_llm()` judgement
  (same tier as QA/Brand), returns `{issues: [...]}`. **Fails open** on LLM error but records
  `metadata.moderation = {status: "unavailable"}` so it's visible, not silent.
- `POST /content/{id}/approve` runs moderation first. Issues → `409` with the issues; the UI shows
  them and offers *Approve anyway* (`?override=true`), recorded in `metadata.moderation.override_by`.
- `schedule_content` and `publish_now` reject anything not `approved` (or `scheduled`, for reschedule/publish-now).
- `PATCH /content/{id}` can no longer set `status` to `approved`/`scheduled`/`published` —
  only the dedicated endpoints can. (Today any string is accepted.)
- Portal approve (`routers/portal.py`) goes through the same moderation call.
- Tests in `test_tenancy_routers.py` style: each gate verified to fail when removed.

## 5. Amplify

**Backend**
- `agents/amplify.py` — `get_worker_llm(0.8)` (angle quality *is* the judgement, so not `lite`).
  Prompt reads `BrandContext` (voice, vocab include/exclude, **example_posts** — currently unused anywhere)
  plus campaign brief when the source belongs to a campaign.
- `services/repurpose.py` — pure helpers, fully unit-tested:
  `REPURPOSE_ANGLES` (hook, how-to, contrarian, story, data-point, question, behind-the-scenes, listicle),
  `is_angle_duplicate(candidate, recent)`, `drip_schedule(atoms, start, per_week)`,
  platform char limits.
- `POST /api/v1/amplify/preview` `{client_id, source_content_id | source_text, platforms[], max_atoms≤8}`
  → atoms `[{platform, angle, title, body, hashtags, duplicate_warning}]`. **Nothing is saved.**
  `client_id` and `source_content_id` resolved against `org_id` (CLAUDE.md tenancy rule).
- `POST /api/v1/amplify/commit` `{client_id, source_content_id?, atoms[]}` → rows as `status="draft"`,
  `metadata={source_id, angle, amplify_pack_id}`. Cap 8 server-side.
- Existing `/content/{id}/repurpose` stays (API compat) — the UI stops calling it.

**Frontend** — `/amplify`: pick client → pick source (content item or pasted text) → platforms →
Generate (QuotaHint, cancel via AbortController) → review grid, drop atoms → **Add to queue** → lands on Posts → Queue / Pending.
"Amplify" button on every Queue card and campaign content card deep-links with `?source=<id>`.

## 6. Dev rules → CLAUDE.md

A "Product rules" section, adapted (publishing is real here, unlike Cadence):
1. Never imply a capability that isn't real (Instagram/TikTok publish, image-gen, inbox).
2. Humans have final say — no path auto-approves or auto-publishes.
3. Moderation before approval, on every path that creates a post (AI, manual, portal, Amplify).
4. No invented numbers — real data or an explicit empty state.
5. LLM access only through the four tier getters.
6. Before presenting: `ruff` + `mypy` + `pytest`, `npm run lint` + `npm run build`.

## 7. Phases (each its own PR on a feature branch)

| # | Phase | Size | Risk |
|---|---|---|---|
| 0 | CLAUDE.md product rules | S | none |
| 1 | Design tokens, fonts, `components/ui` primitives (Panel, Button, Eyebrow, SubNavTabs, StatusBadge, QuotaHint), dark shell + top nav/sub-tabs, Clerk dark appearance | M | every page sits in the dark shell with light-styled bodies until phase 5 |
| 2 | Approval gate backend + tests (§4) | M | **behaviour change**: anything scripted to schedule drafts starts getting 409s |
| 3 | Posts → Queue page + calendar restyle + schedule picker | M | |
| 4 | Amplify backend + tests, then Amplify UI + deep-link buttons | L | output blandness — needs an eyeball pass on real generations, tests won't catch it |
| 5 | Restyle remaining pages (campaigns, clients, analytics, settings, team, pricing, templates, magic brief, landing) | L | visual regressions; E2E H1 checks only |

Phase 1 and 2 are independent and can go in parallel.

## Decisions (260921)

- **Amplify counts against a quota.** New `subscription.generations_used` / `generations_limit`
  (per `PLAN_CONFIG` tier, reset alongside `posts_used` on `invoice.paid`). 1 pack = 1 generation.
  `402` when exhausted. QuotaHint reads it from `/billing/subscription`.
- **Landing page gets the new look** — added to phase 5.
- **Dark and light themes.** Tokens are CSS variables with a `.dark` set; `class` strategy,
  follows OS by default, toggle in the top nav, persisted in `localStorage` (per-viewer convenience only).
- **Pack history table.** New `repurpose_pack` (id, org_id, client_id, source_content_id NULL,
  source_text, platforms JSONB, atom_count, committed_count, created_by, created_at) — `db/init.sql`
  + `tables.py` + `db/migrations/2609xx_repurpose_pack.sql`. Committed atoms carry
  `metadata.amplify_pack_id` → FK-by-convention. History list on the Amplify screen.
- **Client portal requires login.** Replaces the unauthenticated `/portal/{org_slug}` approve path.
  New phase 6 (below) — needs its own scoping; it touches Clerk, roles, and tenancy.

## Phase 6 — authenticated client portal (to scope)

- Client reviewers sign in via Clerk and are linked to exactly one `client` (new `client_reviewer`
  role or `client_user` table: user_id, client_id, org_id).
- Reviewers see only their client's Pending items; approve/reject goes through the same
  moderation gate, recorded with the reviewer's user id. No moderation override for reviewers.
- The unauthenticated `PATCH /portal/{org_slug}/content/{id}` is removed (keep read-only GET
  behind a flag, or remove too — decide at scoping).
- Open: invite flow (AgentMail invite like team invites?), and whether reviewers count against seat limits.
