# Frontend Pages
<!-- verified: 260328 -->

Next.js 14 App Router. All dashboard routes protected by Clerk middleware.

## Layout Hierarchy

```
RootLayout (server)
├── ClerkProvider + ClerkTokenSync + Toaster
├── /sign-in, /sign-up — Clerk hosted UI (no dashboard chrome)
└── DashboardLayout (client)
    ├── Sidebar: nav links, UserButton, mobile hamburger
    ├── Header: breadcrumb area
    └── <main>{children}</main>
```

## Pages

### Root `/`
**File**: `src/app/page.tsx` | **Client**
Clerk auth check → redirect to `/campaigns` (signed in) or `/sign-in`.

### Sign In `/sign-in/[[...sign-in]]`
**File**: `src/app/sign-in/[[...sign-in]]/page.tsx` | **Server**
Centered Clerk `<SignIn />` on gradient.

### Sign Up `/sign-up/[[...sign-up]]`
**File**: `src/app/sign-up/[[...sign-up]]/page.tsx` | **Server**
Centered Clerk `<SignUp />` on gradient.

### Dashboard Overview `/`
**File**: `src/app/(dashboard)/page.tsx` | **Server**
Renders `<DashboardContent />` — 6 KPI stat cards from `api.getStats()`.

### Campaigns `/campaigns`
**File**: `src/app/(dashboard)/campaigns/page.tsx` | **Client**
Campaign list with status badges. Links to detail and `/campaigns/new`.

### New Campaign `/campaigns/new`
**File**: `src/app/(dashboard)/campaigns/new/page.tsx` | **Client**
3-step wizard: Brief → Channels/Budget → Review. Accepts Magic Brief from sessionStorage. Calls `api.createCampaign()` then navigates to detail.

### Magic Brief `/campaigns/new/magic-brief`
**File**: `src/app/(dashboard)/campaigns/new/magic-brief/page.tsx` | **Client**
URL input → `api.extractBrand()` → displays brand profile → "Use This Profile" saves to sessionStorage and redirects to campaign wizard.

### Campaign Detail `/campaigns/[id]`
**File**: `src/app/(dashboard)/campaigns/[id]/page.tsx` | **Client**
Two tabs:
- **Live Agents**: `<LiveAgentDashboard />` — SSE pipeline progress, review buttons
- **Content**: List of generated pieces, approve drafts

### Clients `/clients`
**File**: `src/app/(dashboard)/clients/page.tsx` | **Client**
Client list + inline "Add Client" form. `api.getClients()` / `api.createClient()`.

### Client Detail `/clients/[id]`
**File**: `src/app/(dashboard)/clients/[id]/page.tsx` | **Client**
Brand intelligence dashboard: KPIs, platform breakdown, brand voice, top content.

### Content `/content`
**File**: `src/app/(dashboard)/content/page.tsx` | **Client**
Content library with status filter. **Publish Now** and **Repurpose** actions. Approve drafts inline. **Suggestions** tab for recycling top performers.

### Calendar `/calendar`
**File**: `src/app/(dashboard)/calendar/page.tsx` | **Client**
Month grid via `date-fns`. **Drag-and-drop** rescheduling (HTML5 DnD), **week view** toggle, **platform color coding**. Shows scheduled/published content. Modal detail view.

### Analytics `/analytics`
**File**: `src/app/(dashboard)/analytics/page.tsx` | **Client**
Real analytics dashboard with **tabs**: **Overview**, **Trends**, **Benchmarks**. Overview includes KPI cards, content pipeline, campaign status, agent metrics, platform insights.

### Settings `/settings`
**File**: `src/app/(dashboard)/settings/page.tsx` | **Client**
Tabbed UI wired to the **backend API** for org **settings**, **API keys**, and **platform accounts**:
- **General**: Org name, domain/settings from API, save
- **Platforms**: Connection status for X, LinkedIn, Instagram, Facebook
- **API Keys**: Create/delete keys with prefix display
- **Notifications**: Toggle preferences (campaign complete, review ready, publish success, weekly digest)

### Templates `/templates`
**File**: `src/app/(dashboard)/templates/page.tsx` | **Client**
Campaign template marketplace. Category filter, template cards, **Use Template** launch flow.

### Pricing `/pricing`
**File**: `src/app/(dashboard)/pricing/page.tsx` | **Client**
4-tier pricing display. Current plan badge. Upgrade via Stripe Checkout.

### Team `/team`
**File**: `src/app/(dashboard)/team/page.tsx` | **Client**
Member list with role badges. Invite form (email + role).

**Total: 17 page files** (including dashboard, auth, campaigns, clients detail, templates, and nested routes)
