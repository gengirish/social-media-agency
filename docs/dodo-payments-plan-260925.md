# Dodo Payments — replacing the Stripe billing path

Created 260925. Scope: make Dodo Payments the payment integration for CampaignForge AI,
replacing the Stripe code in `services/billing.py` and `routers/billing.py`.

**Decision taken up front: this is a replacement, not a second provider.** Evidence that the
swap is cheap: `flyctl secrets list -a campaignforge-api` (260925, recorded in
[docs/oauth-connect-plan-260925.md](oauth-connect-plan-260925.md)) lists twelve secrets and
none of them is `STRIPE_*`. So in production `stripe.api_key` is `None` and every
`PLAN_CONFIG` entry falls back to the literal placeholders `price_starter` / `price_growth` /
`price_agency`. **Nobody has ever checked out.** There are no live Stripe customers, no
`stripe_customer_id` values in Neon, and therefore no data migration. If that assumption is
wrong, §8 has the fallback.

---

## 1. What exists today

| Layer | File | State |
|---|---|---|
| Config | [backend/src/agency/config.py:87-92](../backend/src/agency/config.py#L87-L92) | `stripe_secret_key`, `stripe_webhook_secret`, `stripe_price_{starter,growth,agency}` — all default `""` |
| Plans | [services/billing.py](../backend/src/agency/services/billing.py) `PLAN_CONFIG` | 4 tiers (free/starter/growth/agency), each with `price_id`, `clients_limit`, `posts_limit`, `generations_limit`, `amount` (cents), `features` |
| Service | `BillingService` | `create_checkout_session`, `handle_webhook` + 4 handlers, `get_subscription`, `check_quota`, `record_post_published`, `get_plans` |
| Router | [routers/billing.py](../backend/src/agency/routers/billing.py) | `GET /plans`, `GET /subscription`, `POST /checkout` (gated on `BILLING_MANAGE`), `POST /webhook` (deliberately ungated, signature-authenticated) |
| Schema | `subscription` table in [db/init.sql:48-65](../db/init.sql#L48-L65) + [models/tables.py:130-148](../backend/src/agency/models/tables.py#L130-L148) | `stripe_customer_id`, `stripe_subscription_id`, `plan_tier`, limits, `posts_used`, `generations_used`, period bounds, `status` |
| Frontend | [pricing/page.tsx](../frontend/src/app/(dashboard)/pricing/page.tsx), [lib/api.ts:355-372](../frontend/src/lib/api.ts#L355-L372), [cadence-settings.tsx](../frontend/src/components/settings/cadence-settings.tsx) | Reads `/billing/plans` + `/billing/subscription`, POSTs `/billing/checkout`, redirects to `checkout_url` |
| Tests | [backend/tests/test_billing.py](../backend/tests/test_billing.py) | Handlers unit-tested against the SQLite fixture; the network client is monkeypatched wholesale |

The shape is already provider-shaped: **one service, four webhook handlers, one `checkout_url`
returned to the browser.** The frontend contract (`{ checkout_url }`) does not have to change
at all. That is what keeps this a backend-only swap for phases 1–3.

---

## 1a. Verified against the SDK (260925)

Both Dodo MCP servers timed out, so the surface below was checked by unpacking the published
wheel — **`dodopayments` 1.117.0** — rather than trusting the plugin's bundled skill docs. Three
of those docs' claims are wrong, and the plan follows the SDK:

| Claim in the bundled docs | What the SDK actually has | Consequence |
|---|---|---|
| "Wrap sync SDK calls in a thread" | `AsyncDodoPayments` exists (`_client.py:470`) with `async` resources | **Use the async client.** No `to_thread`, no blocked event loop. §4c below is corrected |
| "a single `return_url`; there is no separate cancel URL" | `checkout_sessions.create` takes **both** `return_url` and `cancel_url` | The existing `success_url` / `cancel_url` request shape is kept as-is — no API change for the frontend |
| Metadata may only appear on the creating event | `Subscription.metadata` is a **required** field (`types/subscription.py:58`), and `Subscription` is the payload of every `subscription.*` event | `metadata.org_id` is reliable on renewals and cancels. §9 Q1 is resolved |

Other facts pinned from the wheel, all load-bearing:

- **`unwrap` needs the `webhooks` extra.** `webhooks.unwrap()` imports `standardwebhooks` lazily
  and raises `DodoPaymentsError("You need to install dodopayments[webhooks]")` if absent. A plain
  `dodopayments` dependency gives a service that starts fine and then **fails every webhook at
  runtime**. Declare `dodopayments[webhooks]`.
- `unwrap(payload: str, *, headers, key)` is **sync even on the async client** — it is pure HMAC,
  no I/O. Call it directly; do not `await` it.
- **`environment` defaults to `live_mode`** when not given (`_client.py:182`). This is the
  strongest argument for the `Literal` narrowing in phase 1 — an unset var charges real cards.
- `webhook_key` falls back to `$DODO_PAYMENTS_WEBHOOK_KEY`; pass it explicitly anyway, since this
  repo's settings come from `config.py`, not raw env reads.
- `CheckoutSessionResponse.checkout_url` is `Optional[str]` → the 502 guard in phase 3 is required,
  not defensive padding.
- `customer_portal.create(customer_id, *, return_url, send_email)` returns
  `CustomerPortalSession`, whose only field is **`.link`** (not `.url`).
- The event enum also contains `subscription.past_due`, `subscription.paused` and
  `subscription.unpaused`, which the bundled docs never mention (they explicitly claim no
  pause/resume exists). Subscribe to and handle all three.

Three more, found during implementation and each one a production incident avoided:

- **`AsyncDodoPayments.__init__` raises `DodoPaymentsError` when `bearer_token` is absent.**
  This is the sharpest edge in the whole swap. `stripe.api_key = None` was inert, so the old
  module imported cleanly with no key; the Dodo equivalent **throws at construction**. Built
  eagerly at module scope — the obvious port — it takes the entire app down at import in every
  environment without a key: CI, local dev, and production until the secrets land. The client
  must be lazy and return `None` when unconfigured, with callers answering `503`.
- **`dispute.lost` cannot be resolved from its own payload.** Unlike `Subscription`, the
  `Dispute` model carries no `customer` and no `metadata` — only `payment_id`, `dispute_id` and
  `amount`, and that `amount` is a **string**, not an integer of cents. Resolving the org needs
  a `payments.retrieve(payment_id)` round-trip, so **dispute handling is inert without a working
  `DODO_API_KEY`**, and the "full refund only" amount comparison used for refunds cannot be
  reused. That is the real reason `dispute.lost` downgrades unconditionally (§9 Q2).
- **`get_subscription` spreads `**plan`, so the API now returns `product_id` where it returned
  `price_id`.** A wire-format change with no compile-time signal: the frontend's `Plan` and
  `SubscriptionInfo` both declared `price_id?` as *optional*, so `tsc` stayed green while the
  type lied about the response. Renamed in `lib/api.ts`; worth remembering that optional fields
  make this class of drift invisible to the build.

---

## 2. Concept mapping

| Stripe (today) | Dodo Payments | Note |
|---|---|---|
| `price_xxx` | `pdt_xxx` **product** id | One Dodo product per paid tier, created in the dashboard |
| `stripe.Customer.create` | Implicit — pass `customer: {email, name}` to the checkout session, or `{customer_id}` to reuse | Dodo has no mandatory pre-create step |
| `stripe.checkout.Session.create` | `client.checkout_sessions.create(...)` | Returns `session_id` + `checkout_url` |
| `success_url` / `cancel_url` | `return_url` / `cancel_url` | Both exist (§1a). Dodo appends `?status=success\|failed&session_id=…` to the return URL |
| `stripe-signature` header | `webhook-id` + `webhook-signature` + `webhook-timestamp` | Standard Webhooks spec; the signed message is `id.timestamp.raw_body` |
| `stripe.Webhook.construct_event` | `client.webhooks.unwrap(raw_body, headers=…)` | Raises on bad signature; needs raw bytes |
| Billing Portal (never wired here) | `client.customers.customer_portal.create(customer_id, return_url=…)` | Link expires in 24h. **New capability — see §5, phase 4** |
| Stripe Tax / invoicing | Dodo is merchant of record | VAT/GST, invoices and receipts are Dodo's; nothing to build |

---

## 3. Event mapping — and the one that matters

| Stripe handler today | Dodo event(s) | What changes |
|---|---|---|
| `checkout.session.completed` → activate | `subscription.active` | Fires on first activation **and** on recovery from `on_hold`. Must be idempotent on re-entry, not "activate again" |
| `invoice.paid` → reset `posts_used`/`generations_used` | `subscription.renewed` | **The highest-consequence mapping in this plan.** Dodo emits no `invoice.paid`. Miss it and every paying org's Amplify and publishing quota never resets — they pay and then hit `402` for the rest of the year |
| `customer.subscription.deleted` → downgrade to free | `subscription.cancelled` *(+ `subscription.expired`)* | Dodo splits these. `cancelled` with `cancel_at_next_billing_date: true` means **keep access until `next_billing_date`** — downgrading on that event bills the customer for a month they cannot use |
| `customer.subscription.updated` → re-derive tier from price id | `subscription.plan_changed` (+ `subscription.updated`) | `plan_changed` also fires when `cancel_at_next_billing_date` is toggled and when add-ons change. Do not treat every one as a paid upgrade — re-read `product_id` and map that |
| *(none)* | `subscription.on_hold` | Renewal payment failed, recoverable. Set `status='on_hold'`, notify. **Do not revoke** — Dodo retries and dunning may recover it |
| *(none)* | `subscription.failed` | Terminal: the initial mandate never took. The org never had access; leave it on free |
| *(none)* | `subscription.past_due` | Record `status`; same policy question as `on_hold` (§9 Q3) |
| *(none)* | `subscription.paused` / `.unpaused` | Record `status`. Exists in the SDK enum despite the bundled docs claiming there is no pause (§1a); handle rather than silently ignore |
| *(none)* | `refund.succeeded`, `dispute.lost` | Money returned. Decide policy (§9) |

Everything else in Dodo's 40+ event catalogue stays unsubscribed.

---

## 4. Gaps the swap exposes

These are not Dodo's fault — the Stripe path has the same holes. Dodo's documented delivery
semantics turn two of them from theoretical into certain.

**4a. No webhook idempotency.** Dodo retries a non-2xx **eight times** (immediately, 5s, 5m,
30m, 2h, 5h, 10h, 10h). `_handle_checkout_completed` is roughly idempotent by luck — it
overwrites the same fields. `_handle_invoice_paid`'s successor is not: a redelivered
`subscription.renewed` re-zeroes `posts_used`, handing an org a free extra period of quota
every time Dodo retries. Needs a claimed-event table, with the claim and the entitlement write
**in the same transaction** (claim-then-commit-separately is the classic way to permanently
drop an event).

**4b. No ordering guarantee.** Dodo states events can arrive out of order. `subscription.active`
landing after `subscription.cancelled` silently re-grants a cancelled plan. Guard with the
event's own `timestamp` against a new `last_event_at` column; ignore anything older.

**4c. Today's Stripe calls block the event loop.** `stripe.checkout.Session.create` and
`stripe.Customer.create` are synchronous HTTPS calls made from `async def`. On Fly with one
worker this stalls every concurrent request, including the SSE campaign streams.
**The fix is `AsyncDodoPayments`, not a thread pool** (§1a) — the async client makes this
gap disappear rather than needing to be worked around. Do not port the sync shape.

**4d. No customer portal.** There is no way for a customer to cancel, change card, or see an
invoice — `routers/billing.py` has no portal route at all. Dodo gives this for one endpoint's
worth of work, and it removes the whole class of "email support to cancel" load.

**4e. `amount` in `PLAN_CONFIG` is display-only and can drift** from the real price set on the
Dodo product. The landing page ([frontend/src/app/page.tsx:28](../frontend/src/app/page.tsx#L28))
already mirrors these numbers by hand. Add a go-live check (§7) that reads each product back
from Dodo and asserts the price matches; showing a price we do not charge is the "no invented
numbers" rule applied to money.

---

## 5. Work breakdown

### Phase 0 — Dashboard provisioning (blocks everything)

**The Dodo business is shared with another product.** Probed live on 260925 with the account's
live key: business `bus_0No57DDIUZL3BWTVbAMLp` ("Intelliforge Digital Services",
intelliforge.tech) contains exactly one product — `pdt_0NoEmv9rQptrP7E5FUb2K`, "CertForge Pro",
`199900`, recurring. None of CampaignForge's tiers exist yet.

Two consequences, and the second is easy to miss:

1. `DODO_PRODUCT_STARTER/GROWTH/AGENCY` cannot be filled until the three products are created.
2. **Webhook endpoints are scoped to the business, not the product.** Every CertForge
   subscription event will therefore be delivered to CampaignForge's endpoint. The code is
   safe — `_tier_for_product_id` returns `None`, `_unknown_product` refuses to guess a tier, and
   the route answers 200 so Dodo does not retry — but it logs `dodo_unknown_product_id` at
   **ERROR** for every foreign event. That is exactly the alarm that is supposed to mean "a
   `DODO_PRODUCT_*` env var is misconfigured and paying customers are at risk", so a steady
   drip of CertForge traffic would train everyone to ignore it.

   Fix one of two ways, and decide before go-live: give CampaignForge its **own Dodo business**
   (cleanest — separate catalogue, separate keys, separate webhook stream), or treat a product
   id that belongs to a known-foreign product as `{"status": "ignored"}` at `debug`, keeping
   ERROR for ids that are genuinely unrecognised.

1. Dodo account; test mode and live mode are separate catalogues.
2. Create three **recurring, USD, monthly** products: Starter **$20**, Growth **$36**, Agency
   **$168** (`tax_category: saas`). Record both the test and live `pdt_` ids. Currency matters:
   the amounts are smallest-unit, so an INR-defaulted product turns $20 into ₹20.
3. Create a webhook endpoint → `https://campaignforge-api.fly.dev/api/v1/billing/webhook`,
   subscribed to: `subscription.active`, `subscription.renewed`, `subscription.on_hold`,
   `subscription.past_due`, `subscription.paused`, `subscription.unpaused`,
   `subscription.plan_changed`, `subscription.cancelled`, `subscription.expired`,
   `subscription.failed`, `refund.succeeded`, `dispute.lost`. Copy the signing secret.
4. API keys: one test, one live. Every Dodo API key is secret and server-side only — there is
   no Stripe-style publishable key to put in the frontend.

### Phase 1 — Config and dependencies

- `backend/pyproject.toml`: drop `stripe>=11.0.0`, add **`dodopayments[webhooks]>=1.117.0`** —
  the extra is not optional here, it is what makes signature verification importable (§1a).
- `config.py`: replace the five `stripe_*` settings with
  `dodo_api_key`, `dodo_webhook_key`, `dodo_environment` (`test_mode` | `live_mode`),
  `dodo_product_starter`, `dodo_product_growth`, `dodo_product_agency`.
  **Narrow `dodo_environment` to a `Literal` defaulting to `test_mode`** — the SDK raises
  `ValueError: Unknown environment` on a typo, and defaulting to live would let a
  misconfigured deploy charge real cards.
- `backend/.env.example`: replace the `=== Stripe (billing) ===` block (lines 215-230), keep
  `FRONTEND_URL` and retitle its comment (line 342) — it now feeds one `return_url`, not two.

### Phase 2 — Schema

Three edits, per the repo rule, plus the forward-only script (nothing applies these on Neon
automatically):

- `db/init.sql` + `models/tables.py`: rename `stripe_customer_id` → `billing_customer_id`,
  `stripe_subscription_id` → `billing_subscription_id`; add `last_event_at TIMESTAMPTZ`.
- New table `billing_webhook_event (webhook_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW())`. The primary key **is** the idempotency
  claim.
- `db/migrations/260925_dodo_billing.sql`: the two `ALTER TABLE … RENAME COLUMN`s, the two
  `ADD COLUMN`s, the `CREATE TABLE`. The renames are safe only because every value is NULL —
  **run `SELECT count(*) FROM subscription WHERE stripe_customer_id IS NOT NULL;` on Neon
  first** and stop if it is non-zero (§8).
- `backend/tests/conftest.py:303-323`: `create_subscription`'s kwargs follow the rename.

**Four test files call the renamed kwargs, not two.** An earlier draft of this plan named only
two because the survey `grep` was truncated by `head -40`. The full set:

| File | What it needs |
|---|---|
| `test_amplify.py:451` | one kwarg. **Plus** `test_invoice_paid_resets_generations` (~line 447) drives `handle_webhook` with a literal `{"type": "invoice.paid"}` — an event Dodo never emits. It is a rewrite to a `subscription.renewed` payload, not a rename |
| `test_billing_subscription_updated.py` | `stripe_subscription_id=` at lines 37, 57, 77, 98, 128, 157, 182, and the whole file is built on `customer.subscription.updated` payload shapes → re-target at `subscription.plan_changed` |
| `test_gate_team_billing.py` | **The dangerous one.** It does `import stripe` at line 33 and monkeypatches `stripe.Customer`, `stripe.checkout.Session` and `stripe.Webhook`. Once `stripe` leaves `pyproject.toml` this fails at *collection* time and takes the entire module down — including tests that have nothing to do with billing. Port it in the same change that drops the dependency, never after |
| `test_billing.py` | the full port described in §7 |

`test_gate_team_billing.py::test_stripe_webhook_works_with_no_user_at_all` asserts the webhook
route stays reachable with no bearer token at all. That property is the whole reason the route
is ungated — **port it, do not delete it.**

### Phase 3 — Service rewrite (`services/billing.py`)

Keep the public surface — `create_checkout_session`, `handle_webhook`, `get_subscription`,
`check_quota`, `record_post_published`, `get_plans` — so callers and tests stay pointed at the
same names.

- `PLAN_CONFIG`: `price_id` → `product_id`, sourced from the new settings. Keep `amount`,
  `features` and every limit **unchanged** — pricing is not part of this change.
- `_tier_for_price_id` → `_tier_for_product_id`, same contract: an unknown id returns `None`,
  the caller logs loudly and touches nothing. That guard is what stops a misconfigured env var
  from mass-downgrading paying customers; it must survive the port verbatim.
- `create_checkout_session`: one `checkout_sessions.create` with `product_cart`, `customer`
  (`{customer_id}` when the row already has one, else `{email, name}`), `metadata`
  `{org_id, plan_tier}`, and `return_url = {FRONTEND_URL}/settings?checkout=success`.
  **The router must start passing the caller's email** — `get_current_user` returns the JWT
  payload dict, which carries `email` ([dependencies.py:186](../backend/src/agency/dependencies.py#L186));
  `user.id` / `user.email` attribute access raises and surfaces as a 500.
  Refuse a `checkout_url` of `None` with a 502 rather than returning it.
- `handle_webhook(db, event, webhook_id)`: claim `webhook_id` → if already present, return
  `{"status": "duplicate"}`; compare the event `timestamp` to `sub.last_event_at` → drop if
  older; dispatch; write `last_event_at`; **commit once, at the end**. Today each handler
  commits itself — that must change, or the claim and the entitlement write land in separate
  transactions.
- Handlers, one per §3 row. `_handle_subscription_cancelled` gains the
  `cancel_at_next_billing_date` branch: set `status='cancelled'` and keep the tier until
  `subscription.expired` arrives.
- Org resolution: prefer `metadata.org_id`, fall back to `billing_customer_id`. Neither alone
  is reliable — metadata's presence on renewal payloads is unverified (§9), and the customer
  id is absent on the very first `subscription.active` if the row was never written.

### Phase 4 — Router (`routers/billing.py`)

- `POST /webhook`: read raw bytes (`await request.body()` already does), require the three
  `webhook-*` headers, `client.webhooks.unwrap(...)`, 401 on failure. Keep the route ungated —
  the existing docstring explaining *why* applies unchanged to Dodo and should be kept.
  `503` when `dodo_webhook_key` is unset, as today.
- `POST /checkout`: pass `user["email"]` and `user.get("full_name")` through.
- **New** `POST /billing/portal`, gated on `BILLING_MANAGE`: returns `{portal_url}` from
  `customers.customer_portal.create`. `409` when the org has no `billing_customer_id` (a free
  org has never had a customer created) — do not 500.

### Phase 5 — Frontend

Small, because the contract held.

- [lib/api.ts](../frontend/src/lib/api.ts): add `createPortalSession()`; update the comment at
  line 372 that names Stripe; `SubscriptionInfo` gains `on_hold` as a possible `status`.
- Settings → Plan & usage ([cadence-settings.tsx:263-301](../frontend/src/components/settings/cadence-settings.tsx#L263-L301)):
  a **Manage billing** button hitting the portal, and an `on_hold` banner ("Your last payment
  failed — update your card to keep publishing"). `on_hold` is the one state a customer can fix
  themselves, and today they would not even know they are in it.
- **Rename `price_id?` -> `product_id?`** in both `Plan` and the `SubscriptionInfo`
  declaration-merge block. Easy to lose: both fields are *optional*, so `tsc` stays green while
  the type lies about the response shape (§1a).
- **How the UI knows a portal exists.** A 409-only design means every free user sees a button
  that fails once. The shipped code gates on `plan_tier !== "free"` with the 409 as a backstop,
  which leaves one wrong case: an org that cancelled down to free **still has a
  `billing_customer_id`**, and the portal would work for it (invoices, reactivation) but the
  button is hidden. The honest signal is a `has_billing_customer` boolean on
  `GET /billing/subscription`; the tier heuristic should be replaced by it.
- Comment-only: [frontend/src/app/page.tsx:33](../frontend/src/app/page.tsx#L33) names Stripe.
- `?checkout=cancel` no longer happens (Dodo has one `return_url`). Leave the pricing page's
  handling in place — harmless — or drop it; do not build a cancel route Dodo will never call.

---

## 6. Non-goals

Stated so scope does not creep: no new tier, no usage-based/credit billing,
no annual plans (the landing page's monthly-only toggle stays honest), no seat-based billing,
no in-app invoice list (the Dodo portal has it), no proration UI.

**Pricing did change, on 260926, after this plan was written**: paid tiers moved from
$49 / $149 / $399 to **$20 / $36 / $168**, set at 20% under Metricool's USD monthly list on
brand-count parity. Limits were deliberately left alone. The anchor and the per-tier arithmetic
live in the `PLAN_CONFIG` comment in `services/billing.py`; `docs/competitive-analysis-gtm.md`
and `docs/campaignforge-hardening-backlog.md` carry a dated note that their positioning analysis
predates the change and has not been re-run.

Plan changes go through the
portal in v1 rather than `subscriptions.change_plan` — `change_plan` needs an explicit
`proration_billing_mode` and a preview screen to be honest about what we charge, and that is
its own piece of work.

---

## 7. Testing

- Port every existing case in **all four** files listed in phase 2 to the Dodo payloads — they
  already cover "which plan/limits an org gets", which is the part that must not regress.
  `test_gate_team_billing.py` must be done in the same commit that drops the `stripe`
  dependency, or CI fails at import.
- New cases, each of which should fail when its guard is deleted (same discipline as
  `test_approval_gate.py` and `test_tenancy_routers.py`):
  - a redelivered `subscription.renewed` with the same `webhook-id` resets usage **once**;
  - an out-of-order `subscription.active` older than `last_event_at` does not resurrect a
    cancelled plan;
  - `subscription.cancelled` with `cancel_at_next_billing_date: true` **keeps** the paid tier;
  - `subscription.expired` downgrades to free;
  - an unknown `product_id` leaves entitlements untouched and returns an error;
  - a bad signature is a 401 and writes nothing;
  - the claim rolls back when the handler raises, so a retry can still apply the event.
- Local delivery: `dodo wh listen http://localhost:8001/api/v1/billing/webhook` against a
  test-mode key. Use `unwrap()`, never `unsafeUnwrap()`, outside of unsigned `dodo wh trigger`
  payloads.
- Go-live price check: a one-off script that retrieves each configured product and asserts its
  price equals `PLAN_CONFIG[tier]["amount"]`. Run it after the live catalogue is created and
  whenever a price changes (§4e).
- Gate before presenting: `ruff` + `mypy` + `pytest` (backend), `npm run lint` + `npm run build`
  (frontend).

---

## 8. Go-live

> **Status 260929 — steps 1-5 are DONE; step 6 (the live smoke test) is NOT.**
>
> | Step | State |
> |---|---|
> | Neon precheck + migration | Applied. `stripe_*` gone, `billing_*` + `last_event_at` present, `billing_webhook_event` exists (0 rows), 48 orgs |
> | Backend deploy | Live (v64+). `POST /billing/portal` answers 401, not 404 |
> | Frontend | Merged to `main` as PR #10; pricing page shows $20 / $36 / $168 |
> | Dodo catalogue | Brand `brnd_0NoaEFOLvJ66awNxR4nVP`; products `pdt_0NoaS4Lzldp0Oif1k6gxB` / `pdt_0NoaS4PJzcSCUbjlpQl0z` / `pdt_0NoaS4QHgtnAbtN2kLUMg`; webhook `ep_3JxcNOKdvf9JsOAsis8qiIvY5Kd` |
> | Fly secrets | All eight set, `FRONTEND_URL` included |
> | **Live smoke test** | **Not run. No payment has ever completed.** |
>
> Two things learned doing it, both worth keeping:
>
> * **The brand id prefix is `brnd_`, not `brd_`.** And a brand created through the Dodo UI
>   put the URL into `name`, which generated the card-statement descriptor
>   `DODOPAY_HTTPSCAMPAIGNF`. Fixed via `brands.update`; there is **no brand delete**, so a
>   mistaken brand can only be renamed, never removed.
> * Sequencing drifted from this plan and got away with it: the migration and the backend
>   deploy happened close together, and the frontend merged before the secrets were set —
>   so for a period the public pricing page advertised plans whose checkout returned 503.
>   Nobody appears to have hit it, but the ordering in this section exists precisely to
>   avoid that, and it is the one step worth being pedantic about next time.


1. Run the NULL check from phase 2 on Neon. Non-zero → stop; the rename becomes an additive
   `billing_*` column pair plus a backfill, and this plan needs a Stripe-wind-down section.
2. Apply `db/migrations/260925_dodo_billing.sql` to Neon by hand.
3. `flyctl secrets set DODO_API_KEY=… DODO_WEBHOOK_KEY=… DODO_ENVIRONMENT=live_mode
   DODO_PRODUCT_STARTER=pdt_… DODO_PRODUCT_GROWTH=pdt_… DODO_PRODUCT_AGENCY=pdt_…` — this
   redeploys on its own.
4. Confirm `FRONTEND_URL=https://campaignforge.intelliforge.tech`. It is not among the twelve
   secrets today, so it currently defaults to `http://localhost:3000` — **every checkout would
   return the customer to localhost.** Set it in the same command as step 3.
5. Frontend deploys from the repo root: `npx vercel --prod --archive=tgz`.
6. Live smoke: one real checkout on Starter with a real card, confirm `subscription.active`
   arrives and the row flips, then cancel from the portal and confirm access survives to the
   period end. Refund it.
7. Only after the live smoke passes: delete the `stripe` dependency's last traces and refresh
   the docs below.

### Documentation touchpoints

`grep -rl -i stripe docs/ db/ README.md backend/pyproject.toml` (260925) returns 26 files.
Most are dated historical records — `stub-audit-260817.md`, `fix-plan-260907.md`,
`build-status-260907.md`, `sessions/260817-session-notes.md` — and **should not be rewritten**;
they describe what was true then.

These must change, because they describe what is true now:

| File | Why |
|---|---|
| `docs/features/billing.md` | Entirely Stripe-shaped: price ids, checkout flow, webhook list. Rewrite via the `feature-docs` skill |
| `docs/features/integrations.md` | Has a `## Stripe` section |
| `docs/features/api-endpoints.md`, `services.md`, `database-schema.md`, `frontend-pages.md` | Column renames, the new portal route, the new webhook table |
| `docs/features/changelog.md` | One entry for the swap |
| `README.md:21,64-65` | Tech table says "Stripe subscriptions"; env table lists `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` |
| `docs/yc-pitch.md:89,161` | Claims "Stripe billing" as a shipped capability to investors — the one place a stale line actively misleads |
| `docs/beta-testing-plan.md:94,208,223` | TC-17 is a Stripe checkout test case; week 3 says "Enable Stripe live mode"; a success metric sources from the Stripe dashboard |
| `docs/diagrams/campaignforge-architecture.html` + `.json` | Regenerate; the payments node is labelled Stripe |
| `docs/campaignforge-hardening-backlog.md`, `docs/campaignforge-implementation-plan.md`, `docs/competitive-analysis-gtm.md`, `docs/rbac-phase-plan-260923.md` | Live planning docs — check each hit and update or strike it |

---

## 9. Open questions

1. ~~Does `metadata` persist onto later subscription events?~~ **Resolved** (§1a):
   `Subscription.metadata` is a required field on the model every `subscription.*` event
   carries, so `metadata.org_id` is reliable. The `billing_customer_id` fallback stays anyway —
   it costs one `or` and covers a subscription created outside our checkout (e.g. re-created by
   support in the Dodo dashboard), which would carry no `org_id`.
2. **Refund / dispute policy.** `refund.succeeded` currently maps to nothing. Downgrade to free
   immediately, or let the period run out? A full-period refund and an immediate downgrade are
   the consistent pair; a partial refund is not, and there is no partial-refund concept in
   `PLAN_CONFIG`.
3. **`on_hold` enforcement.** Today *nothing* enforces on `subscription.status` — the field is
   recorded and ignored, which the existing code comments call out deliberately. Does `on_hold`
   block publishing, block generation, or only show a banner? Product decision; §5 phase 5
   assumes banner-only.
4. **Test vs live catalogue.** Two sets of `pdt_` ids means preview/staging needs its own
   secrets. There is no staging Fly app today — does preview traffic point at production's
   backend? If so, test-mode checkout is not reachable anywhere but localhost.
5. Whether to keep a `billing_provider` column. Omitted above on purpose (single provider), but
   adding it later is another three-file migration.
