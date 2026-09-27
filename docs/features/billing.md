# Billing
<!-- verified: 260923 -->

## Stripe Integration
**Status**: [LIVE]
**File**: `backend/src/agency/services/billing.py`

### Plan Tiers

Source of truth is `PLAN_CONFIG` in `services/billing.py`. Price IDs come from `STRIPE_PRICE_STARTER` / `_GROWTH` / `_AGENCY` with `price_*` string fallbacks.

| Tier | Monthly Price | Clients | Posts/mo | Campaigns/mo | Amplify packs/period | Target |
|------|--------------|---------|----------|--------------|----------------------|--------|
| Free | $0 | 1 | 30 | 5 | 10 | Trial users — no publishing |
| Starter | $49 | 3 | 200 | 20 | 50 | Solo marketers |
| Growth | $149 | 10 | 1000 | Unlimited | 250 | Growing teams |
| Agency | $399 | Unlimited | Unlimited | Unlimited | Unlimited | Agencies |

"Unlimited" is stored as a large sentinel integer (`999` clients, `99999` posts, `9999` campaigns, `9999` generations), not null — quota checks are plain integer comparisons.

> **Plan copy is not consistent across surfaces.** The landing page (`src/app/page.tsx`) lists Free as "1 client / 30 posts / mo"; the in-app pricing page (`src/app/(dashboard)/pricing/page.tsx`) lists it as "1 client / 5 campaigns / mo / No publishing". Both numbers exist in `PLAN_CONFIG`, but a visitor sees two different headline allowances. Neither page mentions the Amplify allowance. Open decision — see `docs/cadence-port-plan-260921.md`.

### Workspace profile (pricing shaping)

**Status**: [LIVE] (260925)
**Column**: `organization.workspace_profile` — `product_owner` | `freelancer` | `organization`, nullable.
**Config**: `WORKSPACE_PROFILES` in `services/billing.py`.

How a workspace describes itself, chosen on `/pricing`. It decides **which of the four
tiers above are offered, in what order, and which one is marked "Best for you"** —
nothing else.

| Profile | Tiers offered | Recommended |
|---|---|---|
| Product owner | Free, Starter, Growth | Starter |
| Freelancer / consultant | Starter, Growth, Agency | Growth |
| Agency / organization | Growth, Agency | Agency |

Three things this is **not**, each of which has a test in `tests/test_workspace_profile.py`:

- **Not a price change.** Every profile bills against the same `PLAN_CONFIG` amounts and
  the same Stripe `price_id`s. There are no per-profile Stripe products.
- **Not a permission.** It grants no capability and changes no limit; `subscription`
  remains the only source of truth for what an org may do. It is deliberately *not*
  `organization.account_type`, which is a one-way flip that drives `permissions.py` —
  folding the two together would let a pricing-page click move someone's permissions.
- **Not able to hide your own plan.** `plans_for_profile()` always re-inserts the org's
  current tier (in `PLAN_CONFIG` order) even when the profile would not offer it, and an
  unrecognised stored value falls back to the full grid. Both fail open.

`NULL` is the default and means "never chosen" → the full four-tier grid, with Growth
marked "Most Popular" as before. Setting it needs `billing.manage`.

### Checkout Flow

1. Frontend calls `POST /api/v1/billing/checkout` with `plan_tier` (required); `success_url` / `cancel_url` optional — when omitted, defaults are `{FRONTEND_URL}/settings?checkout=success` and `{FRONTEND_URL}/pricing?checkout=cancel`
2. Backend creates Stripe Checkout Session via `billing.create_checkout_session()`
3. Returns `{checkout_url}` — frontend redirects to Stripe
4. On completion, Stripe sends webhook to `POST /api/v1/billing/webhook`

### Webhook Signature Verification
**Status**: [LIVE] — `routers/billing.py`

`POST /api/v1/billing/webhook` verifies every request before it can mutate a subscription:

1. No `STRIPE_WEBHOOK_SECRET` configured → **503**, so an unconfigured deploy fails closed rather than accepting anything
2. Missing `stripe-signature` header → **400**
3. `stripe.Webhook.construct_event(payload, sig_header, secret)` against the **raw request body** (`await request.body()`, not the parsed JSON)
4. `ValueError` → **400** invalid payload; `SignatureVerificationError` → **400** invalid signature

Only a verified event reaches `billing.handle_webhook()`. This closes the "anyone can grant themselves a paid plan" hole — hardening backlog P0-3 is satisfied in code, though `tests/test_billing.py` asserting it does not yet run (P0-2).

### Webhook Events

| Event | Handler | Action |
|-------|---------|--------|
| `checkout.session.completed` | `_handle_checkout_completed` | Update subscription tier + limits |
| `invoice.paid` | `_handle_invoice_paid` | Reset usage counters |
| `customer.subscription.deleted` | `_handle_subscription_cancelled` | Downgrade to free |
| `customer.subscription.updated` | `_handle_subscription_updated` | Sync plan changes |

### Quota Enforcement

`billing.check_quota(db, org_id, resource="posts")` — Checks `posts_used < posts_limit` before publishing (immediate and scheduled). On successful publish, `billing.record_post_published()` increments `posts_used`.

### Amplify Generation Quota
<!-- verified: 260921 -->

**Status**: [LIVE] — `routers/amplify.py`, `services/billing.py`

1 Amplify pack (one `POST /amplify/preview` that returns at least one draft) = 1 generation, regardless of how many drafts are in it or how many are later committed.

<!-- verified: 260923 -->
**Since 260923 the same allowance covers every generator**, through `services/generation_quota.py` (`require_generation_quota` before the model, `charge_generation` after a usable result). 1 generation each: Amplify pack; Queue generate / regenerate / creative brief (`/content/generate`, `/content/{id}/regenerate`, `/content/{id}/creative-brief`); Setup brand-voice draft and strategy lens; Create › Content blog / comparison / niche scan / video script / blog-from-gap / AI-SEO pack; Create › Email campaign; Create › Launch kit and PRFAQ stress-test; Create › Ads set; Insights advocacy; Inbox reply suggestion. **Free:** intake answer coaching, manual posts, approvals, asset list/rename/delete. The new screens' `QuotaHint` / `UsageMeter` say "generations left"; Amplify's still says "packs left this period", which now overstates it — the same pool is spent by every other screen. Post Studio is the one path that refunds on cancel: it checks `request.is_disconnected()` after the model returns and charges nothing if the caller has gone.

- **Columns:** `subscription.generations_used` (NOT NULL, default 0) and `subscription.generations_limit` (nullable). See [database-schema.md](database-schema.md#subscription).
- **Limit resolution:** `generations_limit_for(sub)` — the row's `generations_limit`; if NULL, the tier's `PLAN_CONFIG["generations_limit"]`; if the tier is unknown, the free tier's. Never unlimited by default.
- **Where the limit is written:** on signup (`routers/auth.py`), Clerk auto-provisioning (`dependencies.py`), `checkout.session.completed`, `customer.subscription.updated`, and downgrade to free on `customer.subscription.deleted` — the same places `posts_limit` is written.
- **Enforcement:** preview checks `generations_used >= limit` → **402** `{"code": "generation_quota_exceeded", "message"}` before calling the LLM. A missing subscription row is also a 402.
- **Charging:** only after a successful generation — `UPDATE subscription SET generations_used = generations_used + 1` in the same transaction as the `repurpose_pack` insert. An LLM error or an empty result is a 502 and charges nothing. Commit never charges.
- **Known race:** the limit check and the increment are separate statements, so concurrent previews by the same org at the boundary can each pass the check and overshoot the limit.
- **Cancel does not refund:** the UI's Cancel aborts the browser request; the server does not observe the abort, so a generation that completes server-side is still charged.
- **Reset:** `invoice.paid` sets `generations_used = 0` alongside `posts_used = 0`. There is no other reset — Free orgs, which never receive `invoice.paid`, are never reset.
- **Reporting:** `GET /billing/subscription` returns `generations_used` and `generations_limit` (the row's values, placed after the `PLAN_CONFIG` spread so a per-org override is not hidden). With no subscription row it returns the free plan and `generations_used: 0`. The Amplify screen's `QuotaHint` reads these and renders nothing if either is missing.
- **Migration:** `db/migrations/260921_amplify.sql` backfills `generations_limit` by tier for existing rows.

### Frontend

**Route**: `/pricing`
**Component**: `PricingPage` (client component)

- Fetches plans via `api.getPricing()` (shaped by the workspace profile) and subscription via `api.getSubscription()`. `api.getPlans()` still returns the raw, unshaped tier list — prefer `getPricing()` on any screen that sells.
- A profile picker above the grid (`ProfilePicker`); choosing one saves immediately via `PUT /billing/workspace-profile` and reshapes the grid. Re-clicking the selected card clears it back to the full grid. Disabled without `billing.manage`.
- Displays the tiers the server returned (2–4 of Free, Starter, Growth, Agency); the recommended one is highlighted and carries the profile's one-line reason
- Current plan badge on active tier
- Upgrade buttons call `api.createCheckout()` and redirect

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `STRIPE_SECRET_KEY` | Stripe API key |
| `STRIPE_WEBHOOK_SECRET` | Webhook signature verification — endpoint returns 503 without it |
| `STRIPE_PRICE_STARTER` | Price ID for the starter tier (falls back to the literal `price_starter`) |
| `STRIPE_PRICE_GROWTH` | Price ID for the growth tier (falls back to `price_growth`) |
| `STRIPE_PRICE_AGENCY` | Price ID for the agency tier (falls back to `price_agency`) |
| `FRONTEND_URL` | Base URL for default Stripe Checkout return URLs (default `http://localhost:3000`) |

> The three `STRIPE_PRICE_*` variables are read by `config.py` but are **missing from `.env.example`**. Without them, checkout builds sessions against nonexistent `price_starter`-style IDs and Stripe rejects them.
