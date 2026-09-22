# Frontend Pages
<!-- verified: 260921 -->

Next.js 15 (`^15.5.14`) + React 19 App Router, Clerk `^7.0.6`. All dashboard routes protected by Clerk middleware — only `/`, `/sign-in`, `/sign-up`, and `/api/webhooks/*` are public.

Every page uses the Cadence design system (260921): CSS-variable Tailwind tokens with light and dark themes, Inter / Space Grotesk / IBM Plex Mono, and the `components/ui/*` primitives. See [frontend-components.md](frontend-components.md#design-system).

## Layout Hierarchy

```
RootLayout (server) — src/app/layout.tsx
├── <head>: THEME_INIT_SCRIPT (sets .dark before first paint)
├── next/font: Inter (--font-sans), Space Grotesk (--font-display), IBM Plex Mono (--font-mono)
├── ClerkProvider (amber primary; fallback redirect /campaigns) + ClerkTokenSync + ThemedToaster
├── /            — landing page (no dashboard chrome)
├── /sign-in, /sign-up — AuthCanvas: themed Clerk widget (no dashboard chrome)
└── DashboardLayout (client) — src/app/(dashboard)/layout.tsx
    ├── AnalyticsTracker
    ├── AppNav (sticky top bar): brand + breadcrumb, 5 group pills, sub-tabs,
    │   ThemeToggle, NotificationsBell, Clerk UserButton, mobile "Menu" drawer
    └── <main key={pathname}> (max-w-7xl, fade-up on route change)
```

The **left sidebar is gone** (260921). It listed 9 flat links; navigation is now the grouped top bar below. AppNav is rendered inside a `Suspense` boundary because it reads `?tab=` via `useSearchParams`; the fallback renders the same bar path-only.

## Navigation (IA)

Defined as data in `src/lib/navigation.ts` (`NAV_GROUPS`) and resolved by `resolveNav(pathname, queryTab)`. Routes did not move — only the grouping is new — so E2E URL checks still hold.

| Group | Sub-tabs → route |
|---|---|
| **Setup** | Clients `/clients` · Accounts `/settings?tab=platforms` |
| **Posts** | Queue `/content` · Calendar `/calendar` |
| **Create** | Campaigns `/campaigns` · Templates `/templates` · Amplify `/amplify` |
| **Insights** | Analytics `/analytics` |
| **Settings** | Workspace `/settings` · Team `/team` · Billing `/pricing` |

- A group pill links to its first tab. Sub-tabs render only when the active group has more than one.
- `/settings?tab=platforms` resolves to **Setup › Accounts**, not Settings › Workspace: a tab with a matching `queryTab` outranks a path-only match, and a longer path outranks a shorter one.
- The breadcrumb reads `CAMPAIGNFORGE/<TAB>`. The brand links to `/campaigns`.
- Not in the nav: `/campaigns/new`, `/campaigns/[id]`, `/clients/[id]` (reached from their parent pages; they resolve to the parent's tab by path prefix).

## Pages

### Root `/` — Marketing Landing Page
**File**: `src/app/page.tsx` | **Server Component**
Public marketing site in the Cadence look. Static markup with two client islands: `AuthCta` (session-aware buttons) and `ThemeToggle`. Sections: hero, How it works, the 7-agent pipeline, features, pricing (monthly only — no annual toggle, because there are no annual Stripe prices), closing CTA.

The placeholder logo strip and testimonials flagged in the 260817 stub audit are **gone**.

> Pricing on this page is hardcoded separately from `PLAN_CONFIG` and must be kept in sync by hand. It lists Free as "1 client / 30 posts / mo", while the in-app `/pricing` page lists "1 client / 5 campaigns / mo" — see [billing.md](billing.md#plan-tiers).

### Sign In `/sign-in/[[...sign-in]]` · Sign Up `/sign-up/[[...sign-up]]`
**Files**: `src/app/sign-in/[[...sign-in]]/page.tsx`, `src/app/sign-up/[[...sign-up]]/page.tsx` | **Server** → `<AuthCanvas mode=… />` (client)
Brand bar with theme toggle, Clerk `<SignIn />` / `<SignUp />` themed per light/dark via `clerkVariables(theme)`.

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
**File**: `src/app/(dashboard)/content/page.tsx` | **Client** | components in `src/components/posts/*`
H1 is **"Queue"** (was "Content Library"; `e2e/navigation.spec.ts` updated). Every post waits here for a person.

- **Status tabs** (`QueueTabs`): Pending (`draft`) · Approved · Scheduled · Published · Failed, each with a count fetched per status (`GET /content?content_status=…&per_page=1`, reading `total`). A count that failed to load shows "–", never a guess. The Failed count is highlighted when non-zero.
- **Filters**: client and platform (server-side); free-text search over title, body, hashtags and client name (client-side, **current page only** — the page says so when results are paginated). 50 per page.
- **Pending card**: Edit (title/body/hashtags) and **Approve**. Approve calls `POST /content/{id}/approve`; a 409 `moderation_flagged` opens `ModerationWarning` with the issues, where editing is primary and **Approve anyway** (`?override=true`) is secondary. Toasts distinguish passed / override recorded / moderation unavailable.
- **Approved / Scheduled cards**: Edit, **Schedule** / **Reschedule** (`ScheduleDialog`, local time → UTC ISO; `POST /publishing/{id}/schedule`), **Publish now** (`PublishConfirm`, then `POST /publishing/{id}/publish`). Editing body/hashtags server-side resets the post to Pending. Scheduled cards past their time show an "overdue" badge. For Instagram and TikTok (no publisher) Schedule and Publish now are disabled with the reason shown (`lib/platforms.ts`).
- **Published cards**: published time + link to the live post when `metadata_.post_url` exists.
- **Failed cards**: the platform's `metadata_.publish_error`, or "The platform did not return a reason." **No retry action** — the only path back is `PATCH` to `draft` and re-approve, which the UI does not offer.
- Every card has an **Amplify** link → `/amplify?source=<id>`.
- Empty states per tab; Pending's links to Start a campaign / Amplify a post.
- Not built (were in the port plan): bulk select, delete, undo-delete. There is no content `DELETE` endpoint. `rejected` posts (portal rejections) have no tab and do not appear anywhere in the Queue. The old **Repurpose** dialog and **Suggestions** tab are removed.
- `trackFeature`: `post-approve`, `post-schedule`, `post-reschedule`, `content-publish`.

### Calendar `/calendar` — Posts › Calendar
**File**: `src/app/(dashboard)/calendar/page.tsx` | **Client**
H1 "Content Calendar". Month grid / week view via `date-fns`, **drag-and-drop rescheduling** (HTML5 DnD → `POST /publishing/{id}/schedule`), platform colour chips (`components/posts/platform.ts`), `StatusBadge`, detail dialog. Restyled 260921. Every entry is draggable, including published ones; dropping a published post gets the gate's 409 `not_approved` and an error toast.

### Amplify `/amplify` — Create › Amplify
**File**: `src/app/(dashboard)/amplify/page.tsx` | **Client** | components in `src/components/amplify/*` | new 260921
One source → up to 8 angle-distinct drafts. Backend: [api-endpoints.md › Amplify](api-endpoints.md#amplify).

1. **Form** (`AmplifyForm`): client → source (one of the client's content pieces, or pasted text ≤20,000 chars) → platforms (X/Twitter, LinkedIn, Instagram, Facebook, TikTok; default X + LinkedIn) → number of drafts (1–8) → **Generate**. `QuotaHint` shows "N packs left this period" from `/billing/subscription`; Generate is disabled when the quota is exhausted.
2. **Cancel** aborts the request via `AbortController` (the server may still finish and charge the generation).
3. **Review** (`AtomReview` / `AtomCard`): one card per draft with angle chip, platform, char count vs limit, and duplicate warning; drop/restore each; **Add N to queue** commits the rest as Pending, then a toast offers "Open queue".
4. **History** (`PackHistory`): recent packs with source, client, platforms, generated vs committed counts.

- `?source=<content_id>` deep link (from Queue cards) preselects the client and source.
- 402 → quota-blocked state; 404/422/502 → inline error. 409 on commit → "This pack is already in the queue".
- `trackFeature("amplify", {drafts})` on commit.

### Analytics `/analytics` — Insights › Analytics
**File**: `src/app/(dashboard)/analytics/page.tsx` | **Client**
`SegmentedTabs`: **Overview**, **Trends**, **Benchmarks**. Overview: KPI `StatCard`s, content pipeline, campaign status, agent metrics, platform insights. Unavailable data renders as a `Notice` or `EmptyState`, never as zeros.

### Settings `/settings` — Settings › Workspace (and Setup › Accounts)
**File**: `src/app/(dashboard)/settings/page.tsx` | **Client**
Tabs held in the URL as `?tab=` (`general` — no param — `platforms`, `api-keys`, `notifications`), updated with `router.replace`. Wrapped in `Suspense` for `useSearchParams`.
- **General**: org name, domain/settings, save
- **Platforms** (= Setup › Accounts): connection status for X, LinkedIn, Instagram, Facebook, with the reason publishing is unavailable where it is
- **API Keys**: create/delete keys with prefix display
- **Notifications**: "Not available yet" notice

### Templates `/templates` — Create › Templates
**File**: `src/app/(dashboard)/templates/page.tsx` | **Client**
H1 "Campaign Templates". Category filter, template cards, **Use Template** launch flow.

### Pricing `/pricing` — Settings › Billing
**File**: `src/app/(dashboard)/pricing/page.tsx` | **Client**
4-tier pricing display, current plan badge, upgrade via Stripe Checkout. Plan copy is hardcoded in the page.

### Team `/team` — Settings › Team
**File**: `src/app/(dashboard)/team/page.tsx` | **Client**
Member list with role badges, invite form (email + role), amber banner that roles are labels, not restrictions.

**Total: 16 page files.** `/amplify` was added and `/campaigns/new/magic-brief` removed 260921; the dead `src/app/(dashboard)/page.tsx` (a second `/`) was removed 260818, so there is no in-app dashboard-overview page — `components/dashboard-content.tsx` is no longer imported anywhere.
