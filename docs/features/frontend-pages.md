# Frontend Pages
<!-- verified: 260923 -->

Next.js 15 (`^15.5.14`) + React 19 App Router, Clerk `^7.0.6`. All dashboard routes protected by Clerk middleware — only `/`, `/sign-in`, `/sign-up`, `/legal` (260923) and `/api/webhooks/*` are public.

**Cadence full parity (260923).** Every Cadence Crew prototype screen now has a CampaignForge route — plan and screen map in [`docs/cadence-parity-plan-260923.md`](../cadence-parity-plan-260923.md). Where Cadence simulated something (OAuth popups, seeded inbox, browser-side LLM calls, sending), these pages do it for real or say it is unavailable.

Every page uses the Cadence design system (260921): CSS-variable Tailwind tokens with light and dark themes, Inter / Space Grotesk / IBM Plex Mono, and the `components/ui/*` primitives. See [frontend-components.md](frontend-components.md#design-system).

## Layout Hierarchy

```
RootLayout (server) — src/app/layout.tsx
├── <head>: THEME_INIT_SCRIPT (sets .dark before first paint)
├── next/font: Inter (--font-sans), Space Grotesk (--font-display), IBM Plex Mono (--font-mono)
├── ClerkProvider (amber primary; fallback redirect /campaigns) + ClerkTokenSync + ThemedToaster
├── /            — landing page (no dashboard chrome)
├── /sign-in, /sign-up — AuthCanvas: themed Clerk widget (no dashboard chrome)
├── /legal       — public Privacy / Terms / AI notice (no dashboard chrome)
└── DashboardLayout (client) — src/app/(dashboard)/layout.tsx
    └── ActiveClientProvider (lib/active-client.tsx)
        ├── ambient drifting glows (aria-hidden, fixed, behind everything)
        ├── AnalyticsTracker
        ├── AppNav (sticky top bar): logo → /welcome, breadcrumb, ClientSwitcher,
        │   6 group pills, sub-tabs, ThemeToggle, NotificationsBell, UserButton,
        │   mobile "Menu" drawer
        ├── KeyboardShortcuts (1–6 → group, ? → help dialog)
        ├── <main key={pathname}> (max-w-7xl, fade-up on route change)
        └── AppFooter (legal links, "Keyboard shortcuts (?)")
```

<!-- verified: 260923 -->
**Active client.** `ActiveClientProvider` loads `GET /clients/overview` and holds the active client — CampaignForge's version of Cadence's product switcher. Every Create / Posts / Inbox / Insights screen and the client-scoped Settings tabs read `useActiveClient()`; screens call `refresh()` after anything that changes a client's counts. The chosen id is kept in `localStorage` (`cf-active-client`) as a convenience only and re-validated against the org's clients on every load, so a stale or foreign id falls back silently.

**Shell behaviours** (`components/layout/shell-extras.tsx`): number keys `1`–`6` jump to the nav groups in order (Setup, Create, Posts, Inbox, Insights, Settings) and `?` opens the shortcut list — both disabled while typing, with a modifier key held, or with any dialog open. A group pill returns to the last sub-tab visited in that group (`sessionStorage` `cf-last-visited`, per tab).

The **left sidebar is gone** (260921). It listed 9 flat links; navigation is now the grouped top bar below. AppNav is rendered inside a `Suspense` boundary because it reads `?tab=` via `useSearchParams`; the fallback renders the same bar path-only.

## Navigation (IA)

Defined as data in `src/lib/navigation.ts` (`NAV_GROUPS`) and resolved by `resolveNav(pathname, queryTab)`. Routes did not move — only the grouping is new — so E2E URL checks still hold.

<!-- verified: 260923 -->

| # | Group | Sub-tabs → route |
|---|---|---|
| 1 | **Setup** | Profile `/setup/profile` · Clients `/clients` · Accounts `/setup/accounts` |
| 2 | **Create** | Campaigns `/campaigns` · Content `/create/content` · Email `/create/email` · Launch `/create/launch` · Amplify `/amplify` · Ads `/create/ads` · Templates `/templates` |
| 3 | **Posts** | Queue `/content` · Calendar `/calendar` |
| 4 | **Inbox** | Inbox `/inbox` |
| 5 | **Insights** | Analytics `/analytics` |
| 6 | **Settings** | Workspace `/settings` · Team `/team` · Billing `/pricing` |

- Group order is also the keyboard-shortcut order. It deliberately differs from Cadence's (Setup, Posts, Create): Create comes before Posts because the Queue is empty until something has been created (commit 70a67a9).
- A group pill links to the last-visited tab in that group, else its first tab. Sub-tabs render only when the active group has more than one.
- Setup › Accounts moved from `/settings?tab=platforms` to its own route `/setup/accounts` (260923). `/settings?tab=platforms` still works — it now resolves to the Settings **Accounts** tab, which links to Setup › Accounts.
- The breadcrumb reads `CAMPAIGNFORGE/<TAB>`; `STANDALONE_TITLES` gives `/welcome` and `/legal` a title outside the groups. The logo links to `/welcome` (was `/campaigns`).
- Not in the nav: `/welcome`, `/campaigns/new`, `/campaigns/[id]`, `/clients/[id]`, the OAuth callback page (reached from their parent pages or flows; nested routes resolve to the parent's tab by path prefix).

## Pages

### Root `/` — Marketing Landing Page
**File**: `src/app/page.tsx` | **Server Component**
Public marketing site in the Cadence look. Static markup with two client islands: `AuthCta` (session-aware buttons) and `ThemeToggle`. Sections: hero, How it works, the 7-agent pipeline, features, pricing (monthly only — no annual toggle, because there are no annual Stripe prices), closing CTA.

The placeholder logo strip and testimonials flagged in the 260817 stub audit are **gone**.

> Pricing on this page is hardcoded separately from `PLAN_CONFIG` and must be kept in sync by hand. It lists Free as "1 client / 30 posts / mo", while the in-app `/pricing` page lists "1 client / 5 campaigns / mo" — see [billing.md](billing.md#plan-tiers).

### Sign In `/sign-in/[[...sign-in]]` · Sign Up `/sign-up/[[...sign-up]]`
**Files**: `src/app/sign-in/[[...sign-in]]/page.tsx`, `src/app/sign-up/[[...sign-up]]/page.tsx` | **Server** → `<AuthCanvas mode=… />` (client)
Brand bar with theme toggle, Clerk `<SignIn />` / `<SignUp />` themed per light/dark via `clerkVariables(theme)`.

### Welcome `/welcome` — logo target
**File**: `src/app/(dashboard)/welcome/page.tsx` | **Client** | [LIVE] <!-- verified: 260923 -->
Cadence's Welcome for the **active client**, from `GET /clients/overview` (real counts only). Until its three steps are done it is adaptive onboarding — **Set up the brand profile** → **Connect social accounts** → **Generate your first post** — each with its CTA and a done state; the last two stay locked until the brand profile is done. Afterwards it is a welcome-back hub linking to Posts, Create and Insights. No clients → prompt to add one; load failure → error with retry. Not in the nav; the top-bar logo links here.

### Legal `/legal` — public
**File**: `src/app/legal/page.tsx` | **Client** | [LIVE] <!-- verified: 260923 -->
Privacy Policy, Terms and AI notice as tabs (`?tab=privacy|terms|ai`). Public in `middleware.ts`, linked from the dashboard footer. Static copy; describes the product as it is (OAuth tokens held, X/LinkedIn/Facebook connections, no model training on customer data).

### Setup › Profile `/setup/profile`
**File**: `src/app/(dashboard)/setup/profile/page.tsx` | **Client** | components `components/setup/*` · API `lib/api-setup.ts` | [LIVE] <!-- verified: 260923 -->
H1 "Brand profile". Cadence's IntakeScreen for the active client:
1. **Intake** (`Intake`): website URL → real scan via `POST /magic-brief` (SSRF-guarded), then the audience and differentiator questions with push-back coaching (`POST /setup/{id}/profile/evaluate-answer` — advisory, never blocks), and a tone register chosen from four fixed options (never AI-prefilled). **Approve** → `PUT /setup/{id}/profile` (`brand-profile-approved`).
2. After approval, embedded sections: **Campaign** (`CampaignSection`, the campaign focus — `campaign-focus`), **Brand Voice** (`BrandVoiceSection`: generate a draft guide, edit it, approve — `brand-voice`), **Strategy Lens** (`StrategyLensPanel`: run the panel, saved as a `strategy_lens` asset — `strategy-lens`). Generate buttons show the remaining generation quota.

### Setup › Accounts `/setup/accounts`
**File**: `src/app/(dashboard)/setup/accounts/page.tsx` · `components/setup/connected-accounts.tsx` | **Client** | [LIVE] <!-- verified: 260923 -->
H1 "Connected accounts". The active client's connected accounts (`GET /setup/{id}/accounts`) and a Connect button per platform (X, LinkedIn, Facebook). Connect opens a consent dialog listing the scopes this server actually requests, then redirects to the provider (for X, a PKCE challenge is generated first). Disconnect asks for confirmation. Platforms whose app credentials are unset say so. `?connected=<platform>` on return shows a success toast (`connect-account`). Replaces Cadence's simulated OAuth popup and the old `/settings?tab=platforms` screen.

### OAuth return `/api/oauth/[platform]/callback`
**File**: `src/app/(dashboard)/api/oauth/[platform]/callback/page.tsx` | **Client** | [LIVE] <!-- verified: 260923 -->
Where X / LinkedIn / Facebook send the user back. A **page** (inside the dashboard route group, so signed-in), not an API route — it must sit at exactly `{first CORS_ORIGINS entry}/api/oauth/{platform}/callback`, which is the `redirect_uri` the backend builds. Reads `code` + `state`, takes the client id from the (signed) state, takes the PKCE verifier from `sessionStorage` (X), posts all of it once to `POST /oauth/{platform}/callback` (a code is single-use; a ref guards double exchange), makes that client active and redirects to `/setup/accounts?connected=<platform>`. Provider denial, a missing code/state or a failed exchange show an `ErrorBanner` with a way back.

### Create › Content `/create/content`
**File**: `src/app/(dashboard)/create/content/page.tsx` · cards `components/create-content/cards.tsx` · API `lib/api-create-content.ts` | **Client** | [LIVE] <!-- verified: 260923 -->
H1 "Content". Cadence's ContentScreen: mode toggle **Niche scan** · **Blog post** · **Comparison page** · **Video script**, each generating one saved `creative_asset` for the active client (Cancel, quota hint, brand-profile gate). Niche scan warns about a similar earlier scan and offers **Write a blog from this gap**; blog posts show keyword-memory chips and offer **Optimise for AI search** (adds an AI-SEO pack); comparison pages and scans say whether live web research was available. Saved list with search, copy, Markdown export and delete with undo. Nothing here enters the post queue — Amplify is the route from a saved piece to Pending posts. Analytics `create-content`, `ai-seo`.

### Create › Email `/create/email`
**File**: `src/app/(dashboard)/create/email/page.tsx` · `components/create-kits/email-card.tsx`, `kit-shared.tsx` · API `lib/api-create-kits.ts` | **Client** | [LIVE] <!-- verified: 260923 -->
H1 "Email". Pick a lifecycle type (Welcome (Day 0), Onboarding nudge, Re-engagement, Product update, Milestone) → `POST /create/email/generate`. Cards render an inbox preview with a raw toggle, A/B subject lines, and segment + timing tiles; copy, search, soft delete with undo. `CampaignIndicator`, quota hint, Cancel, brand-profile gate. **Drafts only — nothing is sent** (`create-email`).

### Create › Launch `/create/launch`
**File**: `src/app/(dashboard)/create/launch/page.tsx` · `components/create-kits/launch-cards.tsx`, `prfaq-panel.tsx` | **Client** | [LIVE] <!-- verified: 260923 -->
H1 "Launch". Toggle **Product launch** · **Community kit** · **Partnership outreach**, each → `POST /create/launch/generate`. Product launch carries the **PRFAQ stress-test** panel (`PrfaqPanel`): run / re-run it (`POST /create/launch/prfaq`, stored per client in `client.settings.prfaq`, `prfaq-stress-test`); launch kits generated afterwards address its weak spot and say so. Expandable cards, copy, search, delete with undo. Drafts only — nothing is submitted to Product Hunt, press lists or communities.

### Create › Ads `/create/ads`
**File**: `src/app/(dashboard)/create/ads/page.tsx` · `components/ads/ad-set-card.tsx` · API `lib/api-ads.ts` | **Client** | [LIVE] <!-- verified: 260923 -->
H1 "Ads". Google / Meta toggle → `POST /create/ads/generate`. `AdSetCard` shows per-asset character counts against the limits from `GET /create/ads/spec`, trademark and personal-attribute warnings, advisory moderation (or an explicit "moderation unavailable" note), copy all, delete with undo; search and quota hint. A prominent notice says it is **copy and structure only** — no ad account, no campaign creation, no spend, no predicted CTR/CPC/ROAS (`ads`).

### Inbox `/inbox`
**File**: `src/app/(dashboard)/inbox/page.tsx` · components `components/inbox/*` · API `lib/api-inbox.ts` | **Client** | [LIVE] <!-- verified: 260923 -->
H1 "Inbox". Cadence's InboxScreen on **real data** for the active client: a 360px list + detail grid, type chips (Mentions, Comments; DMs marked unavailable with the reason), a channel filter offering only platforms with a connected account, unread filter, Refresh. `AccountBanners` show each account's status (`needs_reconnect`, `api_access_denied`, `rate_limited`, …) with a link to Setup › Accounts, and empty states say *why* there is nothing. Read / handled state is saved server-side (`PATCH /inbox/items/state`). **Suggest a reply** (Cancel, Regenerate, escalation flag, quota hint) fills an editable draft (`inbox-suggest-reply`); **Send** opens a confirm dialog, then `POST /inbox/reply` — moderation flags show the issues with **Send anyway** (recorded) (`inbox-reply`). Where replying is unavailable, **Copy reply** instead.

### Campaigns `/campaigns` — Create › Campaigns
**File**: `src/app/(dashboard)/campaigns/page.tsx` | **Client**
Campaign list with `CampaignStatusBadge`. Links to detail and `/campaigns/new`. Empty state when there are none. This is the post-sign-in landing route.

### New Campaign `/campaigns/new`
**File**: `src/app/(dashboard)/campaigns/new/page.tsx` | **Client**
3-step wizard: Brief → Channels/Budget → Review. Calls `api.createCampaign()` then navigates to detail.

### Campaign Detail `/campaigns/[id]`
**File**: `src/app/(dashboard)/campaigns/[id]/page.tsx` | **Client**
`SegmentedTabs`:
- **Live Agents**: `<LiveAgentDashboard />` — SSE pipeline progress, review buttons
- **Content**: generated pieces with `StatusBadge`; **Approve** on `draft` pieces calls `api.approveContent()`

> The Approve button here has no error handling: a 409 `moderation_flagged` (or any error) is an unhandled rejection — no toast, no moderation issues shown, no override path. Use the Queue to approve. There is no Amplify deep link on these cards.

### Clients `/clients` — Setup › Clients
**File**: `src/app/(dashboard)/clients/page.tsx` | **Client**
Client list + "New Client" `SectionCard` form. `api.getClients()` / `api.createClient()`. **Read website** calls `api.extractBrand()` (`POST /magic-brief`) to draft brand name, industry and description — only into empty or previously-read fields unless "Replace details I've already typed" is ticked — and previews voice + audience. On create, that profile is saved via `api.createBrandProfile()`; a profile failure warns but keeps the client.
- **Active / Archived** `SegmentedTabs` switch `api.getClients(1, archived)`.
- The **whole tile** opens `/clients/[id]`: the brand-name `Link` is stretched over the card (`after:absolute after:inset-0`), so it is still a single link for keyboard and screen readers.

### Client Detail `/clients/[id]`
**File**: `src/app/(dashboard)/clients/[id]/page.tsx` | **Client**
<!-- verified: 260922 -->
Brand intelligence dashboard: KPIs (`StatCard`), platform breakdown, brand voice, top content. Loads `getClientIntelligence`, `getClient` and `getBrandProfile` (404 → no profile) in parallel.
- **About** card: description, website (external link), contact email (`mailto:`).
- **Edit client** swaps the About card for `EditClientForm` (details + brand voice). Saves with `api.updateClient()`, then `api.saveBrandProfile()` only when a profile exists or a brand field changed, so editing details never creates an empty profile. Analytics: `client-edit`.
- **Archive** (`window.confirm`) → `api.archiveClient()`. On 409 `has_scheduled_posts` a second confirm offers to unschedule them (kept approved) and retries with `unschedule=true`; then redirects to `/clients`. Analytics: `client-archive` (with `unscheduled` count).
- Archived clients show a banner with **Restore** (`api.restoreClient()`, analytics `client-restore`).

### Queue `/content` — Posts › Queue
**File**: `src/app/(dashboard)/content/page.tsx` | **Client** | components in `src/components/posts/*` · API `lib/api-posts.ts`
<!-- verified: 260923 -->
H1 is **"Queue"**. Every post waits here for a person. Rebuilt 260923 as Cadence's Posts › List, scoped to the **active client**.

- **Layout**: two columns — the post list, and a sidebar (`queue-sidebar.tsx`) with the client's profile card, channel chips (connected or not, from `GET /post-studio/channels`), a generations `UsageMeter` and real stat cards (`MiniStat`).
- **Status tabs** (`QueueTabs`): Pending (`draft`) · Approved · Scheduled · Published · Failed, each with a count fetched per status (`GET /content?content_status=…&per_page=1`). A count that failed to load shows "–", never a guess.
- **Filters**: platform (`PlatformFilterRow`) and free-text search (`SearchInput`) over title, body and hashtags.
- **Generate posts** (`GeneratePostsModal`): one or more platforms + optional context note (≤280) → one `POST /content/generate` per platform, each a Pending draft costing 1 generation. Cancel aborts; the server discards a result whose caller has gone and charges nothing. After a run, **Download report** saves a plain-text run report (`run-report-download`).
- **Pending card**: inline edit that **autosaves** (debounced `PATCH`, a draft stays a draft); **Regenerate** in place (`POST /content/{id}/regenerate`); **Creative brief** for a designer (`POST /content/{id}/creative-brief`, shown on the card — no image is generated); **Approve** → `POST /content/{id}/approve`, where a 409 `moderation_flagged` opens `ModerationWarning` (edit primary, **Approve anyway** secondary).
- **Approved / Scheduled cards**: edits are **not** autosaved — saving text sends the post back to Pending, so the edit is held on this device (`localStorage`) until an explicit "Save & send back to Pending". **Schedule** / **Reschedule** (`ScheduleDialog`), **Publish now** (`PublishConfirm`). Overdue scheduled posts get an overdue label. Instagram/TikTok: Schedule and Publish now disabled with the reason (`lib/platforms.ts`).
- **Published cards**: published time + link to the live post when `metadata_.post_url` exists. Cannot be deleted (server 409 `published_locked`).
- **Failed cards**: the platform's `metadata_.publish_error`, or "The platform did not return a reason." Still **no retry action**.
- **Bulk actions** on selected posts: approve (one moderation pass per post — a bulk click never skips the check), publish (one confirmation for the batch), delete.
- **Delete** (`DELETE /content/{id}`) — single or bulk — with an 8-second **undo** toast; the request is only sent when the undo window closes.
- Every card keeps its **Amplify** link → `/amplify?source=<id>`.
- `rejected` posts (portal rejections) still have no tab.
- `trackFeature`: `post-approve`, `post-schedule`, `post-reschedule`, `content-publish`, `post-generate`, `post-regenerate`, `creative-brief`, `post-delete`, `post-bulk-approve`, `post-bulk-publish`, `run-report-download`.

### Calendar `/calendar` — Posts › Calendar
**File**: `src/app/(dashboard)/calendar/page.tsx` | **Client** | `components/posts/event-modal.tsx`, `add-post-modal.tsx`
<!-- verified: 260923 -->
H1 "Content Calendar". Month and week views (`date-fns`), scoped to the active client or all clients. Loads `GET /publishing/calendar?client_id=&include_pending=true`, so Pending/Approved posts with a planned day and Failed posts appear alongside Scheduled and Published ones.

- **Drag to reschedule, with approval gating**: a Pending post cannot be dropped onto a day (toast: approve it in the Queue first); an Approved post opens `ScheduleDialog` to confirm the exact time and the live-publish warning; a Scheduled post is rescheduled in place; drops into the past and onto unavailable platforms are refused client-side.
- **Keyboard path**: every post opens `EventModal` (read, edit, **Reschedule**) — drag-and-drop has no keyboard equivalent on its own.
- **Add your own post** (`AddPostModal`) → `POST /content` with `planned_for`: a Pending draft, never scheduled (`calendar-add-post`).
- **Fill {month|week} with AI**: one Pending draft per chosen platform, each planned on the next empty upcoming day at a random time; 1 generation each; Cancel stops the run (`calendar-fill`).
- **This week** panel: what is actually planned from the queue plus the client's campaign focus — replaces Cadence's hard-coded "Weekly strategy".
- A planned day on a draft is only a plan: nothing publishes until the post is approved and scheduled.

### Amplify `/amplify` — Create › Amplify
**File**: `src/app/(dashboard)/amplify/page.tsx` | **Client** | components in `src/components/amplify/*` | new 260921
One source → up to 8 angle-distinct drafts. Backend: [api-endpoints.md › Amplify](api-endpoints.md#amplify).

1. **Form** (`AmplifyForm`): client → source (one of the client's content pieces, **a saved Create-screen asset** — "From Create": blog posts, comparison pages, niche scans, launch kits, video scripts — or pasted text ≤20,000 chars) → platforms (X/Twitter, LinkedIn, Instagram, Facebook, TikTok; default X + LinkedIn) → number of drafts (1–8) → **Generate**. `QuotaHint` shows "N packs left this period" from `/billing/subscription`; Generate is disabled when the quota is exhausted.
2. **Cancel** aborts the request via `AbortController` (the server may still finish and charge the generation).
3. **Review** (`AtomReview` / `AtomCard`): one card per draft with angle chip, platform, char count vs limit, and duplicate warning; drop/restore each; **Add N to queue** commits the rest as Pending, then a toast offers "Open queue".
4. **History** (`PackHistory`): recent packs with source, client, platforms, generated vs committed counts.

- `?source=<content_id>` deep link (from Queue cards) preselects the client and source.
- 402 → quota-blocked state; 404/422/502 → inline error. 409 on commit → "This pack is already in the queue".
- `trackFeature("amplify", {drafts})` on commit.

### Analytics `/analytics` — Insights › Analytics
**File**: `src/app/(dashboard)/analytics/page.tsx` | **Client**
`SegmentedTabs`: **Overview**, **Trends**, **Benchmarks**. Unavailable data renders as a `Notice` or `EmptyState`, never as zeros.

<!-- verified: 260923 -->
**Overview** now opens with Cadence's Insights for the **active client** (`CadenceInsights`, from `GET /insights/summary`): real-data badge, pipeline funnel, per-platform counts, publish success, moderation clean rate, the Content Quality Signal (kept / edited / flagged per platform), engagement where platforms returned metrics, recommendations, and a **How this works** explainer listing every threshold and how much data each still needs. Ratios under 3 samples say "not enough data", never a number. Below it, **Customer advocacy** (`AdvocacyPanel`, `POST /insights/advocacy`) drafts a review request, case-study outline and proof line citing only real counts (analytics `customer-advocacy`). The workspace KPI cards, content pipeline, campaign status and agent metrics follow. With no client, an empty state links to Add a client.

### Settings `/settings` — Settings › Workspace
**File**: `src/app/(dashboard)/settings/page.tsx` · Cadence tabs in `components/settings/cadence-settings.tsx` | **Client**
<!-- verified: 260923 -->
Tabs held in the URL as `?tab=` (no param = `profile`), updated with `router.replace`; `?tab=platforms` is an alias for `accounts`. Wrapped in `Suspense` for `useSearchParams`.

Cadence tabs, per **active client**:
- **Client profile** (`profile`): client details and brand-profile status, with links to edit the client and the brand profile
- **Connected accounts** (`accounts`): summary + link to Setup › Accounts (the real OAuth screen; not duplicated)
- **Posting preferences** (`posting`): voice register (4 Cadence options) and cadence (3 / 5 / 7 / 14 posts a week) → `PUT /workspace/posting-prefs`; fed to every generator
- **Plan & usage** (`plan`): AI generations and published posts used vs limit, with an upgrade link (workspace-wide)
- **Activity log** (`activity`): last 50 events derived from real rows (`GET /workspace/activity`)
- **Export** (`export`): download everything stored for the client as JSON (`GET /workspace/export`; analytics `settings-export`)

Workspace-wide tabs that predate the port:
- **General**: org name, domain/settings, save
- **API Keys**: create/delete keys with prefix display
- **Notifications**: "Not available yet" notice

Not replicated from Cadence: **Reset workspace data** (destructive, and a workspace here holds many clients).

### Templates `/templates` — Create › Templates
**File**: `src/app/(dashboard)/templates/page.tsx` | **Client**
H1 "Campaign Templates". Category filter, template cards, **Use Template** launch flow.

### Pricing `/pricing` — Settings › Billing
**File**: `src/app/(dashboard)/pricing/page.tsx` | **Client**
4-tier pricing display, current plan badge, upgrade via Stripe Checkout. Plan copy is hardcoded in the page.

### Team `/team` — Settings › Team
**File**: `src/app/(dashboard)/team/page.tsx` | **Client**
Member list with role badges, invite form (email + role), amber banner that roles are labels, not restrictions.

**Total: 26 page files** (260923). Added 260923: `/welcome`, `/legal`, `/setup/profile`, `/setup/accounts`, `/create/content`, `/create/email`, `/create/launch`, `/create/ads`, `/inbox`, `/api/oauth/[platform]/callback`. `/amplify` was added and `/campaigns/new/magic-brief` removed 260921; the dead `src/app/(dashboard)/page.tsx` (a second `/`) was removed 260818, so there is no in-app dashboard-overview page — `components/dashboard-content.tsx` is no longer imported anywhere.
