# Cadence Crew → CampaignForge: full UI/UX parity (260923)

Follows [cadence-port-plan-260921.md](cadence-port-plan-260921.md), which ported the design system, nav,
approval gate, Queue and Amplify and deliberately left the rest out. This pass replicates **every**
prototype screen. Branch: `feat/cadence-parity` (integration), one `parity/<phase>` branch per phase.

## Decisions (260923, user)

1. **Scope: exact replication** of every Cadence screen and interaction, including the ones the
   260921 plan excluded (Inbox, Email, Launch, Ads, Content, Welcome, Intake, shortcuts, switcher).
2. **Inbox is built on real X / LinkedIn data**, not seed data. Where an API tier or scope blocks
   access, the UI says so per account.
3. **Product switcher = client switcher.** The active client (top nav, persisted per viewer)
   scopes every Create / Posts / Insights screen, as Cadence scopes to the active product.
4. **Phased branches**, integrated on `feat/cadence-parity`.

Product rules in `CLAUDE.md` still win over pixel parity: where Cadence simulates something
(OAuth, localStorage state, browser-side LLM calls, sending), CampaignForge does it for real or
states that it is unavailable.

## Screen map

| Cadence | CampaignForge route | Phase |
|---|---|---|
| Welcome (logo) | `/welcome` | foundation |
| Product switcher | top-nav client switcher | foundation |
| Shortcuts `1`–`6`, `?`; footer; Legal | shell + `/legal` (public) | foundation |
| Setup › Product Profile (intake, Campaign, Brand Voice, Strategy Lens) | `/setup/profile` | setup |
| Setup › Connected Accounts | `/setup/accounts` | setup |
| Posts › List | `/content` (Queue) | posts |
| Posts › Calendar | `/calendar` | posts |
| Create › Content (blog, comparison, video script, niche scan, AI-SEO) | `/create/content` | content |
| Create › Email | `/create/email` | email-launch |
| Create › Launch (kit + PRFAQ, community, outreach) | `/create/launch` | email-launch |
| Create › Amplify | `/amplify` (+ asset sources) | content |
| Create › Ads (Google / Meta) | `/create/ads` | ads |
| Inbox | `/inbox` | inbox |
| Insights (+ quality signal, advocacy) | `/analytics` | insights-settings |
| Settings (prefs, usage, activity log, export) | `/settings` | insights-settings |

Kept from CampaignForge and not in Cadence: Campaigns (the agent pipeline), Templates, Team,
Billing, client list/detail, API keys, webhooks, white label, portal.

Nav order stays **Setup, Create, Posts** (commit 70a67a9) rather than Cadence's Setup, Posts, Create;
shortcuts follow the nav order.

## Foundation (shipped on `feat/cadence-parity`)

- `GET /clients/overview` — per-client setup progress and queue counts (switcher + Welcome).
- `PUT/DELETE /clients/{id}/campaign-focus` — Cadence's "Campaign", read by every generator via
  `services/brand_context.py::brand_prompt_block`.
- `creative_asset` table + `/assets` CRUD — stored output of the Create screens
  (migration `db/migrations/260923_creative_asset.sql`, run by hand on Neon).
- `services/generation_quota.py`, `services/brand_context.py` — extracted from Amplify so every
  generator shares quota, tenant-scoped client lookup and brand voice.
- UI primitives: ErrorBanner, ConfirmDialog, undoToast, SearchInput, PlatformFilterRow,
  CampaignIndicator; Cadence motion keyframes; ambient glows.

## Deliberately not replicated

- Cadence's **Reset workspace data** — destructive, and a workspace here holds many clients.
- **Simulated OAuth popups** — replaced by the real provider redirect.
- **Seed inbox data** — replaced by real API data or an explicit per-account status.
