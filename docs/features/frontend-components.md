# Frontend Components
<!-- verified: 260923 -->

Components in `frontend/src/components/` — app-level components, the `ui/` design-system primitives, and feature folders (`layout/`, `posts/`, `amplify/`, `clients/`, `setup/`, `create-content/`, `create-kits/`, `ads/`, `inbox/`, `insights/`, `settings/`, `agents/`, `landing/`) — plus modules in `frontend/src/lib/`.

## Design System
**Status**: [LIVE] — ported from Cadence Crew 260921 (`docs/cadence-port-plan-260921.md`)

### Tokens — `tailwind.config.ts`

Every colour is a CSS variable holding bare `R G B` channels (`--c-<name>-<shade>`), emitted by a Tailwind plugin under `:root` (light) and `.dark` (dark), so opacity modifiers like `bg-white/80` keep working. `darkMode: "class"`.

- **Remapped palettes.** Existing pages were written in `slate`, `white` and `indigo`; rather than rewrite them, those are redefined: `slate` → navy-tinted neutral ramp (inverted in dark), `white` → the panel surface, `indigo` → the accent (deep ochre in light so white-on-`indigo-600` clears 4.5:1; amber `#F2C14E` in dark). `brand` aliases `indigo`.
- **Status hues** (`emerald`, `green`, `red`, `rose`, `amber`, `yellow`, `orange`, `blue`, `sky`, `purple`, `violet`, `teal`) keep Tailwind defaults in light and get tinted-panel variants in dark. Hues outside this list (e.g. `pink`) are **not** remapped and will not adapt to dark mode.
- **Semantic names — prefer these in new code:** `canvas` (page background), `panel` (surface), `ink` (text), `muted` (secondary text), `line` (borders), `accent` / `accent-text` (amber; text-safe variant), `on-accent` (text on amber).
- **Fonts:** `font-sans` Inter (`--font-sans`), `font-display` Space Grotesk (`--font-display`), `font-mono` IBM Plex Mono (`--font-mono`), loaded with `next/font/google` in `app/layout.tsx`.
- **Extras:** `shadow-soft`, `shadow-glow`; animations `pulse-dot`, `logo-spin`, `screen-in`. <!-- verified: 260923 --> Cadence motion keyframes added 260923: `breathe`, `pop-in`, `chip-in`, `popup-in`, `slide-out`, `dot-pulse`, `ring-pulse`, `draw-in` (the `Eyebrow` rule now draws in), `bar-load`, `count-up`, `shimmer`, `scanline`, `blob-1` / `blob-2` (the dashboard's ambient glows), `grid-drift`. All collapse under `prefers-reduced-motion`.

### Global styles — `app/globals.css`

`body` uses `bg-canvas text-ink`; `.app-shell` headings use the display face; `:focus-visible` is a 2px `indigo-500` outline (ochre in light, amber in dark — WCAG 2.2 focus appearance); `.app-canvas` (faint 32px grid + two glows), `.glass`, `.press-scale`; all animation/transition durations collapse under `prefers-reduced-motion: reduce`.

### Theme — `lib/theme.ts` + `components/theme.tsx`

- `THEME_STORAGE_KEY = "cf-theme"`. With nothing stored, the OS `prefers-color-scheme` wins. Stored in `localStorage` (per-viewer convenience only; storage errors are swallowed).
- `THEME_INIT_SCRIPT` — inline in `<head>` of the root layout; sets `.dark` on `<html>` before first paint so dark-mode viewers never see a light flash (`<html suppressHydrationWarning>`).
- `currentTheme()`, `applyTheme(theme)`.
- `useTheme()` — live theme via a `MutationObserver` on `<html class>`.
- `ThemeToggle` — moon/sun button; the icon is chosen by CSS (`dark:`), not state, so it is correct before hydration. In the top nav, the landing page and the auth screens.
- `ThemedToaster` — sonner `<Toaster richColors position="top-right">` following the theme; mounted in the root layout.

### Clerk appearance — `lib/clerk-appearance.ts`

`clerkVariables(theme)` returns Clerk `appearance.variables` as literal hex per theme (Clerk resolves colours in JS, so CSS variables are unreliable), setting both current and legacy variable names. Used by `UserButton` in the nav and by `AuthCanvas`. The root `ClerkProvider` sets only the amber primary.

## UI Primitives — `components/ui/`
**Status**: [LIVE]

| Component | File | Notes |
|---|---|---|
| `Button`, `buttonVariants` | `button.tsx` | `cva`; variants `primary` (amber gradient + glow on hover), `secondary`, `ghost`, `danger`; sizes `sm`, `md`. `buttonVariants` styles `Link`s |
| `Panel` | `panel.tsx` | Frosted glass card; `dashed` for placeholders |
| `Eyebrow` | `panel.tsx` | Small label with an amber rule |
| `PageHeader` | `panel.tsx` | Eyebrow + display-face H1 + description + actions |
| `SectionCard` | `section-card.tsx` | Glass panel with eyebrow/heading/description/actions; `delay` staggers the entrance |
| `StatCard` | `stat-card.tsx` | Display numeral over a label. Pass only real numbers; "—" renders muted |
| `EmptyState` | `empty-state.tsx` | Dashed "nothing here yet" — never fake rows |
| `LoadingState` | `empty-state.tsx` | Spinner + optional mono caption |
| `Notice` | `empty-state.tsx` | Inline callout, tones `warning` / `danger` / `info` — for limits and unavailable features |
| `Field`, `Input`, `Textarea`, `Select`, `controlClass` | `field.tsx` | Label over a recessed control with an amber focus ring |
| `SegmentedTabs`, `Tag` | `tabs.tsx` | In-page view switcher as plain buttons with `aria-pressed` (not an ARIA tablist — E2E locates them by role `button`); `Tag` is a mono chip |
| `StatusBadge`, `statusLabel` | `status-badge.tsx` | `content_piece.status` → label: `draft` → **Pending**, plus Approved, Scheduled, Published, Failed, Rejected |
| `CampaignStatusBadge` | `campaign-status.tsx` | `campaign.status` (planning, running — pulsing dot, completed, paused, failed) |
| `QuotaHint` | `quota-hint.tsx` | "N left …" beside a generate button; renders nothing when `used`/`limit` are unknown; amber when ≤10% left, red at 0 |
| `AuthCanvas` | `auth-canvas.tsx` | Sign-in/up screen: brand bar, theme toggle, themed Clerk `<SignIn />`/`<SignUp />` |
| `ErrorBanner` | `feedback.tsx` | [LIVE] 260923. Inline error with an optional retry button (`onRetry`, `retryLabel`) |
| `ConfirmDialog` | `feedback.tsx` | [LIVE] 260923. Destructive confirm on `PostDialog`; for actions that cannot be undone |
| `undoToast(message, onUndo, onExpire?)` | `feedback.tsx` | [LIVE] 260923. Sonner toast with Cadence's 8-second undo window. The caller runs the real action in `onExpire` — Cadence prefers undo over confirm-everywhere for reversible actions |
| `SearchInput` | `search-input.tsx` | [LIVE] 260923. Compact mono search box with a clear button |
| `PlatformFilterRow` | `platform-filter.tsx` | [LIVE] 260923. Cadence's "Channel" filter chips. Pass only platforms with data behind them (e.g. connected accounts) |
| `CampaignIndicator` | `campaign-indicator.tsx` | [LIVE] 260923. "Campaign active: …" line above generate controls, from the active client's `campaign_focus`, with an Edit link to `/setup/profile#campaign`. Renders nothing when no focus is set. Props `{editable?}` |

## AppNav
**Status**: [LIVE]
**File**: `components/layout/app-nav.tsx` · data in `lib/navigation.ts`

Sticky top bar replacing the old sidebar. Props `{pathname, queryTab, lastVisited?}` (supplied by the dashboard layout so it can render inside and outside a `Suspense` boundary). Logo (→ `/welcome`) + `CAMPAIGNFORGE/<TAB>` breadcrumb, `ClientSwitcher`, six group pills (`lg+`) that return to the group's last-visited tab, sub-tabs for the active group, `ThemeToggle`, `NotificationsBell`, Clerk `UserButton`; below `lg`, a "Menu" button opens a drawer with every group and tab. Groups and resolution rules: [frontend-pages.md › Navigation](frontend-pages.md#navigation-ia).

## Shell — `components/layout/`
**Status**: [LIVE]
<!-- verified: 260923 -->

| Component | File | Notes |
|---|---|---|
| `ClientSwitcher` | `client-switcher.tsx` | Cadence's product switcher, mapped onto clients. Lists active clients with real status lines from `/clients/overview` (profile, accounts, pending/scheduled counts); switch, add a client, archive (via `ConfirmDialog`). Esc / outside-click close |
| `KeyboardShortcuts` | `shell-extras.tsx` | `1`–`6` → nav group (last-visited tab), `?` → shortcut dialog. Ignored while typing, with Ctrl/Cmd/Alt, or with any `[role=dialog]` open |
| `useLastVisited(pathname, queryTab)` | `shell-extras.tsx` | Records the current tab per group in `sessionStorage` (`cf-last-visited`); storage errors fall back to first tabs |
| `AppFooter` | `shell-extras.tsx` | Legal links (`/legal?tab=…`) and "Keyboard shortcuts (?)" |

## Posts — `components/posts/`
**Status**: [LIVE] — used by the Queue (`/content`) and, for `platform.ts`, the Calendar

| Component | File | Notes |
|---|---|---|
| `PostCard`, `PostAction`, `PostEdit` | `post-card.tsx` | One queue item: client, platform chip, `StatusBadge`, body/hashtags, inline edit; actions by status (Pending: edit + approve; Approved/Scheduled: edit, schedule/reschedule, publish now); overdue badge; publish error on Failed; published link; Amplify link `/amplify?source=<id>` |
| `QueueTabs`, `QUEUE_TABS` | `queue-tabs.tsx` | Pending · Approved · Scheduled · Published · Failed with counts; `null` count renders "–" |
| `ModerationWarning` | `moderation-warning.tsx` | Shown on 409 `moderation_flagged`: lists issues; Edit is primary, "Approve anyway" (override, recorded server-side) is secondary |
| `ScheduleDialog` | `schedule-dialog.tsx` | Date + time in the viewer's zone, sent as UTC ISO |
| `PublishConfirm` | `publish-confirm.tsx` | One confirmation before posting to a live account |
| `PostDialog` | `dialog.tsx` | Radix dialog shell (focus trap, Esc); closing is blocked while `busy` |
| `QUEUE_PLATFORMS`, `platformLabel`, `platformTone` | `platform.ts` | Platform names/colours shared with the Calendar; only dark-mode-remapped hues |
| `GeneratePostsModal` | `generate-posts-modal.tsx` | [LIVE] 260923. Platforms + context note → one Pending draft per platform; Cancel |
| `AddPostModal` | `add-post-modal.tsx` | [LIVE] 260923. Calendar "Add your own post" → Pending draft with a planned day |
| `EventModal` | `event-modal.tsx` | [LIVE] 260923. Calendar post details: read, edit, keyboard-accessible Reschedule |
| `UsageMeter`, `MiniStat`, `AccountChip`, `ClientProfileCard` | `queue-sidebar.tsx` | [LIVE] 260923. Queue sidebar: generations meter, real stat cards, channel chips, client card |

<!-- verified: 260923 --> `PostCard` (260923) adds `PostAction` values `regenerate` and `brief`, a creative-brief panel, selection for bulk actions, and the edit split: Pending edits autosave to the server; Approved/Scheduled edits are held in `localStorage` (`readLocalEdit`) until "Save & send back to Pending".

## Clients — `components/clients/`
**Status**: [LIVE] — used by `/clients/[id]`
<!-- verified: 260922 -->

| Component | File | Notes |
|---|---|---|
| `EditClientForm` | `edit-client-form.tsx` | Props `{client, profile, onCancel, onSaved(client, profile)}`. Two `SectionCard`s: client details (name, industry, website, email, description) and brand voice (voice, target audience, competitor differentiation, words to use / avoid as comma-separated lists, emoji policy `none`/`minimal`/`moderate`/`heavy`, style rules one per line). "Words to avoid" is the `vocabulary_exclude` list moderation flags on. |

## Amplify — `components/amplify/`
**Status**: [LIVE] — used by `/amplify`

| Component | File | Notes |
|---|---|---|
| `AmplifyForm`, `SourceMode` | `amplify-form.tsx` | Client, source (`SourceMode` `content` \| `asset` \| `text` — a queue post, a saved Create-screen asset "From Create", or pasted text), platforms, draft count, Generate/Cancel, `QuotaHint` |
| `AtomReview` | `atom-review.tsx` | Review grid; drop/restore atoms; "Add N to queue" commits the rest as Pending |
| `AtomCard`, `AngleChip` | `atom-card.tsx` | One draft: angle, platform, `char_count / char_limit`, duplicate warning, drop toggle |
| `PackHistory` | `pack-history.tsx` | Recent packs: source, client, platforms, generated vs queued |
| `ANGLE_LABELS`, `angleLabel`, `platformLabel` | `labels.ts` | Display names |

## Setup — `components/setup/`
**Status**: [LIVE] — used by `/setup/profile`, `/setup/accounts`, Settings, the OAuth callback page
<!-- verified: 260923 -->

| Component | File | Notes |
|---|---|---|
| `Intake`, `isLikelyUrl` | `intake.tsx` | URL scan (real `POST /magic-brief`), audience + differentiator questions with coaching, fixed tone register, Approve |
| `CampaignSection` | `campaign-section.tsx` | Set / clear the campaign focus (`#campaign` anchor) |
| `BrandVoiceSection` | `brand-voice-section.tsx` | Generate a draft guide (1 generation, not saved), edit, approve |
| `StrategyLensPanel` | `strategy-lens-panel.tsx` | Run the strategy lens panel; shows the latest `strategy_lens` asset |
| `ConnectedAccounts`, `platformName`, `useConnectedToast` | `connected-accounts.tsx` | Per-platform connect (consent dialog listing requested scopes, PKCE for X, full-page redirect) and disconnect (confirm) |
| `ActiveClientGate` | `client-state.tsx` | Loading / no-client / error states before a client-scoped screen renders |
| `useGenerationQuota` | `use-generation-quota.ts` | Reads `generations_used` / `generations_limit` from `/billing/subscription` |

## Create — `components/create-content/`, `create-kits/`, `ads/`
**Status**: [LIVE]
<!-- verified: 260923 -->

| Component | File | Notes |
|---|---|---|
| `BlogCard`, `ComparisonCard`, `NicheScanCard`, `VideoScriptCard` | `create-content/cards.tsx` | Saved Content assets: copy, Markdown export, delete with undo; blog AI-search optimisation; scan → blog from gap; web-research status |
| `useGenerationQuota`, `useKitAssets`, `useGenerator`, `useCopied`, `matchesSearch` | `create-kits/kit-shared.tsx` | Shared hooks for the Email / Launch screens (asset list per kind, generate with Cancel, copy feedback) |
| `ClientGate`, `GenerateButton`, `CancelLink`, `QuotaFor`, `GenerateBanner`, `Block`, `CopyButton`, `KitCard`, `AccentBadge`, `ListEmpty` | `create-kits/kit-shared.tsx` | Shared UI for kit screens; `GenerateBanner` distinguishes quota / brand-profile-required / error failures |
| `EmailCampaignCard`, `emailCopyText`, `senderName`, `campaignTypeLabel` | `create-kits/email-card.tsx` | Inbox preview / raw toggle, A/B subjects, segment + timing |
| `LaunchKitCard`, `CommunityKitCard`, `OutreachPitchCard` (+ `*CopyText`) | `create-kits/launch-cards.tsx` | Expandable kit cards; `PH_TAGLINE_LIMIT = 60` |
| `PrfaqPanel` | `create-kits/prfaq-panel.tsx` | Run / re-run the PRFAQ stress-test; shows the stored critique |
| `AdSetCard` | `ads/ad-set-card.tsx` | Google / Meta asset rows with char counts vs limits, trademark / personal-attribute / moderation blocks, copy all, delete with undo |

## Inbox — `components/inbox/`
**Status**: [LIVE] — used by `/inbox`
<!-- verified: 260923 -->

| Component | File | Notes |
|---|---|---|
| `AccountBanners` | `account-banners.tsx` | One banner per account whose status is not `ok`, with the platform's reason and a Setup › Accounts link |
| `InboxListItem`, `PlatformGlyph`, `TYPE_META`, `shortAgo` | `inbox-list-item.tsx` | List row: type, platform, author, excerpt, unread / handled state |
| `InboxDetail` | `inbox-detail.tsx` | Message, suggest-a-reply (Cancel, Regenerate, escalation flag), editable reply, confirm-before-send, moderation issues with Send anyway, Copy reply where sending is unavailable |

## Insights — `components/insights/`
**Status**: [LIVE] — used by `/analytics`
<!-- verified: 260923 -->

| Component | File | Notes |
|---|---|---|
| `CadenceInsights`, `RealDataBadge` | `cadence-insights.tsx` | `GET /insights/summary` rendered: funnel, platforms, publish / moderation rates, quality signal, engagement, recommendations, "How this works" thresholds. Insufficient data shown as such |
| `AdvocacyPanel` | `advocacy-panel.tsx` | Generate customer-advocacy material from real counts; saved `advocacy` assets |
| `InsightBar`, `UsageMeter` | `bars.tsx` | Bars and usage meters (no invented values) |

## Settings — `components/settings/`
**Status**: [LIVE] — used by `/settings`
<!-- verified: 260923 -->

`ProfileTab`, `AccountsTab`, `PostingTab`, `PlanTab`, `ActivityTab`, `ExportTab` in `cadence-settings.tsx` — the per-client Cadence tabs (see [frontend-pages.md › Settings](frontend-pages.md#settings-settings--settings--workspace)).

## DashboardContent
**Status**: [DEPRECATED] — not imported anywhere
**File**: `components/dashboard-content.tsx`

Six KPI cards from `api.getStats()`. Its only consumer, `src/app/(dashboard)/page.tsx`, was removed 260818; it was restyled 260921 but has no route. Delete or re-mount.

## NotificationsBell
**Status**: [LIVE]
**File**: `components/notifications-bell.tsx`

Bell in the top nav with unread count badge and dropdown panel. Fetches once on mount and again when the panel opens — **no polling** (the old 30s poll re-fetched a list that cannot change, since nothing calls `create_notification()`). Mark read / mark all read. Restyled 260921.

## ClerkTokenSync
**Status**: [LIVE]
**File**: `components/clerk-token-sync.tsx`

Registers Clerk's `getToken()` function with the API client via `setClerkTokenGetter()`. Mounted in root layout. No visual output.

## AnalyticsTracker
**Status**: [LIVE]
**File**: `components/analytics-tracker.tsx`

Mounted in the dashboard layout. Emits product-analytics events — session lifecycle (`session_started`, `session_ended`) and `page_view` — to `POST /api/v1/events` via `lib/analytics.ts`. No visual output.

Only the four `CLIENT_WRITABLE_EVENTS` are accepted by the backend; pipeline, error and Amplify pack events are server-authored so a client cannot inflate them.

## LiveAgentDashboard
**Status**: [LIVE]
**File**: `components/agents/live-agent-dashboard.tsx`

Real-time agent pipeline visualization for campaign execution. Restyled 260921.

### Props
- `campaignId: string` — Campaign to stream
- `onComplete?: () => void` — Callback when pipeline finishes
- `onWaitingHuman?: () => void` — Callback when review needed

### Features
- Connects to SSE stream via `connectAgentStream()` with Clerk token
- 7 agent cards with status indicators (pending → running → complete/error/waiting)
- Progress bar (0–100%)
- **Human review panel**: Appears when pipeline pauses at `human_review` node
  - "Approve & Continue" — sends `{decision: "approved"}` via PATCH
  - "Request Revisions" — sends `{decision: "revise_content"}` via PATCH
  - Verifies response before updating local state
- Activity log showing timestamped agent events

### Agent Pipeline Display

| Agent | Icon | Description |
|-------|------|-------------|
| Orchestrator | Brain | Parsing brief & planning |
| Strategy | Target | Campaign strategy |
| SEO Research | Search | Keywords & optimization |
| Content Writer | PenTool | Creating content |
| Ad Copy | Megaphone | Ad variants |
| Human Review | UserCheck | Awaiting approval |
| QA / Brand | Shield | Quality check |

## AuthCta
**Status**: [LIVE]
**File**: `components/landing/auth-cta.tsx`

Session-aware CTA buttons on the landing page (one of its two client islands).

## Library Modules

### `lib/api.ts`
API client singleton. Uses `NEXT_PUBLIC_API_URL` (default `http://localhost:8001`). Clerk token injected via `setClerkTokenGetter()`. Covers backend endpoints (dashboard, content, campaigns, integrations, notifications, portal helpers, etc.). Added 260921:
- `postsApi` — `list` (filter param is `content_status`; `status` is silently ignored), `count(status, filters)` (reads `total` with `per_page=1`), `approve(id, override)`, `edit`.
- `apiErrorCode(err)` / `moderationIssues(err)` — read structured `detail.code` / `issues` from an `ApiError`.
- `amplifyApi` — `preview(data, signal)`, `commit(packId, atoms)`, `packs(clientId?)`; `AMPLIFY_ANGLES`, `AMPLIFY_MAX_ATOMS`, `AMPLIFY_PLATFORMS`; `isGenerationQuotaError(err)` (402).
- `SubscriptionInfo` gains optional `generations_used` / `generations_limit` (declaration merge).

Added 260922:
- `getClients(page, archived = false)`; `getClientsForLookup()` returns active + archived (100 each) for name lookups on Campaigns and the Queue, so an archived client's posts keep their client name. Not for pickers.
- `updateClient(id, data)` (`UpdateClientRequest`), `archiveClient(id, unschedule?)`, `restoreClient(id)`.
- `getBrandProfile(clientId)` / `saveBrandProfile(clientId, data)` → `SavedBrandProfile`.

### `lib/navigation.ts`
`NAV_GROUPS` (the IA as data; group order = shortcut order), `STANDALONE_TITLES` (`/welcome`, `/legal`) and `resolveNav(pathname, queryTab)`. Pure, no React. `NavIconName` gains `inbox` (260923).

### `lib/active-client.tsx`
<!-- verified: 260923 -->
`ActiveClientProvider` + `useActiveClient()` → `{clients, active, activeId, setActiveId, loading, error, refresh}`; `clientLabel(client)`. Backed by `GET /clients/overview`. The id persists in `localStorage` (`cf-active-client`) and is re-validated against the org's clients on each load.

### Parity API modules (260923)
<!-- verified: 260923 -->
Thin typed wrappers over `lib/api.ts`'s `request`, one per feature:

| Module | Wraps |
|---|---|
| `lib/api-foundation.ts` | `foundationApi` — `/clients/overview`, campaign focus, `/assets` list/get/rename/delete; `ClientOverview`, `AssetKind`, `CreativeAsset<P>` |
| `lib/api-setup.ts` | `setupApi` — `/setup/{id}/*`, `/magic-brief`, OAuth authorize/callback/disconnect; `createPkce(platform)` (S256, verifier in `sessionStorage`), `takePkceVerifier`, `clientIdFromState` (reads the `cid` claim without verifying — the server verifies) |
| `lib/api-posts.ts` | `postStudioApi` — generate, manual post, regenerate, creative brief, delete, channels, client-scoped calendar (`include_pending=true`); `PLATFORM_LIMITS`, `renderedLength`, `isOverdue`, `randomPostTime` |
| `lib/api-create-content.ts` | `createContentApi` — `/create/content/*`; payload types; `draftMarkdown`, `exportFilename`, `collectRepurposeSources` (Amplify "From Create"), `findSimilarScan` |
| `lib/api-create-kits.ts` | `createKitsApi` — `/create/email/generate`, `/create/launch/*`; `EMAIL_CAMPAIGN_TYPES`, `isBrandProfileRequired`, `copyText` |
| `lib/api-ads.ts` | `adsApi` — `/create/ads/spec`, `/create/ads/generate`; `AD_ROW_LIMITS`, `adSetText` |
| `lib/api-inbox.ts` | `inboxApi` — `/inbox`, item state, suggest-reply, reply |
| `lib/api-insights.ts` | `insightsApi` — `/insights/*`, `/workspace/*`; `VOICE_OPTIONS`, `CADENCE_OPTIONS`, `timeAgo` |

### `lib/platforms.ts`
`UNAVAILABLE_PUBLISH_PLATFORMS` (Instagram, TikTok), `publishUnavailableReason(platform)`, `canPublish(platform)`. Since 260921 the Queue disables **Schedule and Publish now** for these platforms (a scheduled post would only fail later) and shows the reason; Amplify atom cards flag them as manual-publish. The backend schedule endpoint does not block them — this is UI-only.

### `lib/theme.ts` · `lib/clerk-appearance.ts`
See [Design System](#design-system).

### `lib/agent-stream.ts`
`connectAgentStream(campaignId, token, onEvent, onError?)` — Opens EventSource to SSE endpoint with JWT in query param. Returns teardown function.

### `lib/analytics.ts`
Product-analytics client. Batches events to `POST /api/v1/events` (max 50 per request). `trackFeature("kebab-name")` is the call to add at the point of success for any new flow that should appear in the adoption table. Currently fired for: `campaign-create`, `client-create` (with `from_website_read`), `client-website-read`, `content-publish`, `post-approve`, `post-schedule`, `post-reschedule`, `amplify`; <!-- verified: 260923 --> added 260923: `post-generate`, `post-regenerate`, `creative-brief`, `post-delete`, `post-bulk-approve`, `post-bulk-publish`, `run-report-download`, `calendar-add-post`, `calendar-fill`, `brand-profile-approved`, `brand-voice`, `strategy-lens`, `campaign-focus`, `connect-account`, `create-content`, `ai-seo`, `create-email`, `prfaq-stress-test`, `ads`, `inbox-suggest-reply`, `inbox-reply`, `customer-advocacy`, `settings-export`.

### `lib/utils.ts`
`cn(...inputs)` — `clsx` + `tailwind-merge` for class name composition.
