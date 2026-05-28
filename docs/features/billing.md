# Billing
<!-- verified: 260328 -->

## Stripe Integration
**Status**: [LIVE]
**File**: `backend/src/agency/services/billing.py`

### Plan Tiers

| Tier | Monthly Price | Clients | Posts/mo | Target |
|------|--------------|---------|----------|--------|
| Free | $0 | 1 | 30 | Trial users |
| Starter | $49 | 3 | 200 | Solo marketers |
| Growth | $149 | 10 | 1000 | Growing teams |
| Agency | $399 | Unlimited | Unlimited | Agencies |

### Checkout Flow

1. Frontend calls `POST /api/v1/billing/checkout` with `plan_tier` (required); `success_url` / `cancel_url` optional — when omitted, defaults are `{FRONTEND_URL}/settings?checkout=success` and `{FRONTEND_URL}/pricing?checkout=cancel`
2. Backend creates Stripe Checkout Session via `billing.create_checkout_session()`
3. Returns `{checkout_url}` — frontend redirects to Stripe
4. On completion, Stripe sends webhook to `POST /api/v1/billing/webhook`

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
| `STRIPE_WEBHOOK_SECRET` | Webhook signature verification |
| `FRONTEND_URL` | Base URL for default Stripe Checkout return URLs (default `http://localhost:3000`) |
