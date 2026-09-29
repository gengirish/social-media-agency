# Billing
<!-- verified: 260929 -->

## Dodo Payments Integration
**Status**: [LIVE] — provisioned in production 260929; **no live transaction yet**
**File**: `backend/src/agency/services/billing.py`
**Plan**: [dodo-payments-plan-260925.md](../dodo-payments-plan-260925.md)

Dodo Payments replaces Stripe outright (260925). There is no second provider and no
fallback path — the Stripe code, its five `STRIPE_*` settings and the `stripe` dependency
are gone.

**Provisioned in production on 260929 — but no money has moved through it yet.** The live
catalogue, the webhook endpoint and all eight secrets are in place, and the API answers on
them: `POST /billing/webhook` returns **400** (signature headers missing) rather than
**503** (key absent), which is exactly the difference between configured and not.

What has *not* happened is a completed payment. No customer has checked out, no
`subscription.active` has ever been received, and the cancel, refund and dispute paths have
never run against real money — every guard covering them is proven by unit tests and by
mutation, not by a transaction. The smoke test in §8 of the plan is what turns "configured"
into "working"; until it passes, do not describe billing as proven.

The live resources:

| Resource | Id | Note |
|---|---|---|
| Brand | `brnd_0NoaEFOLvJ66awNxR4nVP` | Card statement reads `DODOPAY_CAMPAIGNFORGE` |
| Starter | `pdt_0NoaS4Lzldp0Oif1k6gxB` | USD 2000 |
| Growth | `pdt_0NoaS4PJzcSCUbjlpQl0z` | USD 3600 |
| Agency | `pdt_0NoaS4QHgtnAbtN2kLUMg` | USD 16800 |
| Webhook | `ep_3JxcNOKdvf9JsOAsis8qiIvY5Kd` | 12 subscribed event types |

Each product's price was read back from the Dodo API and asserted equal to its `PLAN_CONFIG`
`amount`, so the app cannot be advertising a price it does not charge. A second brand,
`brnd_0NoaC3TaVRG9yKCXjNHMX`, is a duplicate created by mistake and renamed `UNUSED
duplicate`; Dodo has no brand delete, so it cannot be removed — never attach products to it.

**Dodo is merchant of record.** VAT/GST, invoices and receipts are Dodo's responsibility,
not ours. There is no tax code in this repo and no invoice list in the app — the Dodo
customer portal has both.

### Plan Tiers

Source of truth is `PLAN_CONFIG` in `services/billing.py`. **Pricing, tiers and limits are
unchanged by the Dodo swap.** Each paid tier carries a `product_id` — a Dodo `pdt_` product
id from `DODO_PRODUCT_STARTER` / `_GROWTH` / `_AGENCY`.

| Tier | Monthly Price | Clients | Posts/mo | Campaigns/mo | Amplify packs/period | Target |
|------|--------------|---------|----------|--------------|----------------------|--------|
| Free | $0 | 1 | 30 | 5 | 10 | Trial users — no publishing |
| Starter | $20 | 3 | 200 | 20 | 50 | Solo marketers |
| Growth | $36 | 10 | 1000 | Unlimited | 250 | Growing teams |
| Agency | $168 | Unlimited | Unlimited | Unlimited | Unlimited | Agencies |

"Unlimited" is stored as a large sentinel integer (`999` clients, `99999` posts, `9999` campaigns, `9999` generations), not null — quota checks are plain integer comparisons.

`amount` in `PLAN_CONFIG` is **display copy**, not the charged price — the real price lives
on the Dodo product. The landing page mirrors the same numbers by hand. A go-live check
reads each configured product back from Dodo and asserts its price matches `amount`;
showing a price we do not charge is the "no invented numbers" rule applied to money.

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
  the same Dodo `product_id`s. There are no per-profile Dodo products.
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
2. Backend creates a Dodo checkout session via `billing.create_checkout_session()` — one `checkout_sessions.create` with the tier's `product_cart`, a `customer` (`{customer_id}` when the row already has one, otherwise `{email, name}` from the caller's JWT payload) and `metadata` `{org_id, plan_tier}`
3. Returns `{checkout_url}` — frontend redirects to Dodo. `CheckoutSessionResponse.checkout_url` is optional in the SDK; a `None` is refused with a **502** rather than returned
4. On completion, Dodo sends `subscription.active` to `POST /api/v1/billing/webhook`

The request and response shape is unchanged from the Stripe path — `{checkout_url}` in,
redirect out — so no frontend contract moved. Dodo appends
`?status=success|failed&session_id=…` to the return URL, so `?checkout=cancel` no longer
occurs; the pricing page still handles it harmlessly.

All Dodo API calls use `AsyncDodoPayments`. The Stripe client was synchronous and blocked
the event loop (and with it every concurrent SSE campaign stream) on each checkout; do not
reintroduce a sync client.

### Customer Portal
**Status**: [LIVE] (260929) — new capability; no Stripe equivalent was ever wired

`POST /api/v1/billing/portal` (needs `billing.manage`) returns `{portal_url}` from
`customers.customer_portal.create(customer_id, return_url=...)`. The link expires after
24h. Cancelling, changing a card, and reading invoices and receipts all happen there —
there is no in-app equivalent and none is planned.

An org with no `billing_customer_id` (one that never checked out) gets **409**, not a 500; an unconfigured deploy gets **503**.
Plan changes also go through the portal in v1; `subscriptions.change_plan` needs an
explicit proration mode and a preview screen to be honest about what we charge, and is out
of scope.

### Webhook Signature Verification
**Status**: [LIVE] — `routers/billing.py`

`POST /api/v1/billing/webhook` verifies every request before it can mutate a subscription.
Dodo follows the **Standard Webhooks** spec: three headers, and a signed message of
`id.timestamp.raw_body`.

1. No `DODO_WEBHOOK_KEY` configured → **503**, so an unconfigured deploy fails closed rather than accepting anything
2. Missing `webhook-id` / `webhook-signature` / `webhook-timestamp` → **401**
3. `client.webhooks.unwrap(raw_body, headers=..., key=...)` against the **raw request body** (`await request.body()`, not the parsed JSON). It is a sync call even on the async client — pure HMAC, no I/O
4. A bad signature raises → **401**, and nothing is written

The route is deliberately **ungated** (no `require_permission`) because the caller is Dodo,
not a session — the signature *is* the authentication. Keep it that way.

`unwrap()` lives behind the `webhooks` extra, so the dependency is
**`dodopayments[webhooks]>=1.117.0`**. A plain `dodopayments` install starts fine and then
fails *every* webhook at runtime with "You need to install dodopayments[webhooks]".

### Webhook Events

Twelve events are subscribed in the Dodo dashboard. Everything else in Dodo's catalogue is
left unsubscribed.

| Event | Handler | Action |
|-------|---------|--------|
| `subscription.active` | `_handle_subscription_active` | Grant the tier + limits. Fires on first activation **and** on recovery from `on_hold`, so it must be idempotent on re-entry |
| `subscription.renewed` | `_handle_subscription_renewed` | **Reset `posts_used` and `generations_used`.** Successor to Stripe's `invoice.paid`; Dodo emits no invoice event. Miss it and a paying org's quota never resets |
| `subscription.plan_changed` | `_handle_subscription_plan_changed` | Re-read `product_id` and re-derive the tier. Also fires when `cancel_at_next_billing_date` toggles and when add-ons change — not every one is an upgrade |
| `subscription.cancelled` | `_handle_subscription_cancelled` | `status='cancelled'`. With `cancel_at_next_billing_date: true` the **tier is kept** until `subscription.expired` — downgrading here bills for a month the customer cannot use |
| `subscription.expired` | `_handle_subscription_expired` | Downgrade to free |
| `subscription.failed` | `_handle_subscription_failed` | Terminal: the initial mandate never took. The org never had access; leave it on free |
| `subscription.on_hold` | `_handle_subscription_status_only` | Renewal payment failed but recoverable. Record `status` only — **do not revoke**; Dodo retries and dunning may recover it |
| `subscription.past_due` | `_handle_subscription_status_only` | Record `status` only |
| `subscription.paused` / `.unpaused` | `_handle_subscription_status_only` | Record `status` only |
| `refund.succeeded` | `_handle_refund_succeeded` | Downgrade to free **only on a full refund**. A partial refund has no representation in `PLAN_CONFIG` and changes nothing |
| `dispute.lost` | `_handle_dispute_lost` | Downgrade to free |

**Nothing enforces on `subscription.status`.** `on_hold`, `past_due` and `paused` are
recorded and surfaced as a banner; they do not block publishing or generation. Deliberate,
not an oversight.

**Org resolution** prefers `metadata.org_id` — a required field on the `Subscription` model
that every `subscription.*` event carries — and falls back to `billing_customer_id`.
Neither alone is enough: a subscription re-created by support in the Dodo dashboard carries
no `org_id`, and the customer id is absent on the very first `subscription.active` if the
row was never written.

`_tier_for_product_id` returns `None` for an unknown id, and the caller logs loudly and
touches nothing. That guard is what stops a misconfigured `DODO_PRODUCT_*` var from
mass-downgrading paying customers.

### Webhook Idempotency and Ordering
**Status**: [LIVE] — new with the Dodo swap; the Stripe path had neither guard

Dodo retries a non-2xx **eight times** (immediately, 5s, 5m, 30m, 2h, 5h, 10h, 10h), and
states that events can arrive out of order. Two guards, both in `handle_webhook`:

- **Idempotency:** the `webhook-id` is inserted into `billing_webhook_event` (TEXT primary
  key). A duplicate insert fails and the call returns `{"status": "duplicate"}` having done
  nothing. Without this, a redelivered `subscription.renewed` re-zeroes `posts_used` and
  hands the org a free extra period of quota on every retry.
- **Ordering:** the event's own timestamp is compared against `subscription.last_event_at`
  and anything older is dropped. Without this, a `subscription.active` arriving after
  `subscription.cancelled` silently re-grants a cancelled plan.

The claim and the entitlement write land in **one transaction** — `handle_webhook` commits
once, at the end, and individual handlers no longer commit themselves. Claiming in a
separate transaction is the classic way to drop an event permanently: if the handler then
raises, the retry sees the claim and skips the work.

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
- **Where the limit is written:** on signup (`routers/auth.py`), Clerk auto-provisioning (`dependencies.py`), `subscription.active`, `subscription.plan_changed`, and downgrade to free on `subscription.expired` / `refund.succeeded` (full) / `dispute.lost` — the same places `posts_limit` is written.
- **Enforcement:** preview checks `generations_used >= limit` → **402** `{"code": "generation_quota_exceeded", "message"}` before calling the LLM. A missing subscription row is also a 402.
- **Charging:** only after a successful generation — `UPDATE subscription SET generations_used = generations_used + 1` in the same transaction as the `repurpose_pack` insert. An LLM error or an empty result is a 502 and charges nothing. Commit never charges.
- **Known race:** the limit check and the increment are separate statements, so concurrent previews by the same org at the boundary can each pass the check and overshoot the limit.
- **Cancel does not refund:** the UI's Cancel aborts the browser request; the server does not observe the abort, so a generation that completes server-side is still charged.
- **Reset:** `subscription.renewed` sets `generations_used = 0` alongside `posts_used = 0`. There is no other reset — Free orgs, which never receive a renewal event, are never reset. (Before 260925 this was Stripe's `invoice.paid`; Dodo emits no invoice event, so `renewed` is the only reset trigger.)
- **Reporting:** `GET /billing/subscription` returns `generations_used` and `generations_limit` (the row's values, placed after the `PLAN_CONFIG` spread so a per-org override is not hidden). With no subscription row it returns the free plan and `generations_used: 0`. The Amplify screen's `QuotaHint` reads these and renders nothing if either is missing.
- **Migration:** `db/migrations/260921_amplify.sql` backfills `generations_limit` by tier for existing rows.

### Frontend

**Route**: `/pricing`
**Component**: `PricingPage` (client component)

- Fetches plans via `api.getPricing()` (shaped by the workspace profile) and subscription via `api.getSubscription()`. `api.getPlans()` still returns the raw, unshaped tier list — prefer `getPricing()` on any screen that sells.
- A profile picker above the grid (`ProfilePicker`); choosing one saves immediately via `PUT /billing/workspace-profile` and reshapes the grid. Re-clicking the selected card clears it back to the full grid. Disabled without `billing.manage`.
- Displays the tiers the server returned (2–4 of Free, Starter, Growth, Agency); the recommended one is highlighted and carries the profile's one-line reason
- Current plan badge on active tier
- Upgrade buttons call `api.createCheckout()` and redirect to Dodo

**Route**: `/settings` → Plan & usage (`components/settings/cadence-settings.tsx`)

- **Manage billing** button → `api.createPortalSession()` → `POST /billing/portal`, redirects to the Dodo customer portal. Hidden/disabled for an org that has never checked out.
- An `on_hold` banner — "Your last payment failed — update your card to keep publishing". `SubscriptionInfo.status` gained `on_hold` for this. It is the one failure state a customer can fix themselves, and nothing else in the app surfaces it.

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `DODO_API_KEY` | Dodo Payments API key. Server-side only — Dodo has no publishable key |
| `DODO_WEBHOOK_KEY` | Webhook signing secret — endpoint returns 503 without it |
| `DODO_ENVIRONMENT` | `test_mode` \| `live_mode`. **Defaults to `test_mode` here**; the SDK's own default is `live_mode`, which is why `config.py` narrows it to a `Literal` and defaults it down |
| `DODO_PRODUCT_STARTER` | Dodo `pdt_` product id for the starter tier |
| `DODO_PRODUCT_GROWTH` | Dodo `pdt_` product id for the growth tier |
| `DODO_PRODUCT_AGENCY` | Dodo `pdt_` product id for the agency tier |
| `DODO_BRAND_ID` | Dodo `brnd_` brand owning those products. Webhook endpoints are scoped to the **business**, not the brand, so this account's other product (CertForge) delivers its events here too; events from another brand are ignored at debug. Blank filters nothing (fail open) |
| `FRONTEND_URL` | Base URL for the checkout `return_url` and the portal's return link (default `http://localhost:3000`) |

The five `STRIPE_*` settings are removed from `config.py` and `.env.example`.

> **All eight are set in production** (`flyctl secrets list -a campaignforge-api`, 260929),
> `FRONTEND_URL` included — without it the default `http://localhost:3000` would have
> returned every paying customer to localhost after checkout.
>
> Test mode and live mode are **separate catalogues** with separate `pdt_` ids and separate
> API keys. There is no staging Fly app, so test-mode checkout is only reachable locally.
