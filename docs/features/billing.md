# Billing
<!-- verified: 260817 -->

## Stripe Integration
**Status**: [LIVE]
**File**: `backend/src/agency/services/billing.py`

### Plan Tiers

Source of truth is `PLAN_CONFIG` in `services/billing.py`. Price IDs come from `STRIPE_PRICE_STARTER` / `_GROWTH` / `_AGENCY` with `price_*` string fallbacks.

| Tier | Monthly Price | Clients | Posts/mo | Campaigns/mo | Target |
|------|--------------|---------|----------|--------------|--------|
| Free | $0 | 1 | 30 | 5 | Trial users — no publishing |
| Starter | $49 | 3 | 200 | 20 | Solo marketers |
| Growth | $149 | 10 | 1000 | Unlimited | Growing teams |
| Agency | $399 | Unlimited | Unlimited | Unlimited | Agencies |

"Unlimited" is stored as a large sentinel integer (`999` clients, `99999` posts, `9999` campaigns), not null — quota checks are plain integer comparisons.

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

### Frontend

**Route**: `/pricing`
**Component**: `PricingPage` (client component)

- Fetches plans via `api.getPlans()` and subscription via `api.getSubscription()`
- Displays 4 tiers: Free, Starter, Growth (highlighted), Agency
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
