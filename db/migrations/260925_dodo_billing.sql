-- 260925 — Dodo Payments billing swap: provider-neutral columns, ordering guard,
-- webhook idempotency table.
--
-- No Alembic in this repo (schema lives in db/init.sql), and init.sql only runs on a
-- FRESH database. Run this by hand on Neon — nothing applies it automatically.
-- Forward-only and idempotent: the renames are guarded on the old column still
-- existing, so a second run is a no-op rather than an error.
--
-- THE RENAMES ARE ONLY SAFE BECAUSE EVERY VALUE IS NULL. Stripe was never configured
-- in production (no STRIPE_* secrets on the Fly app), so nobody has ever checked out
-- and no row carries a customer id. A rename loses nothing here; against a database
-- that HAS live values it would be a breaking change and the right shape is instead
-- an additive billing_* pair plus a backfill. Run the guard below FIRST and stop if
-- it returns anything but 0:
--
--   SELECT count(*) FROM subscription WHERE stripe_customer_id IS NOT NULL;

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Provider-neutral ids. Named for the role, not the provider — a
--    provider-shaped name is what forced this rename in the first place.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = 'subscription' AND column_name = 'stripe_customer_id') THEN
        ALTER TABLE subscription RENAME COLUMN stripe_customer_id TO billing_customer_id;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = 'subscription' AND column_name = 'stripe_subscription_id') THEN
        ALTER TABLE subscription RENAME COLUMN stripe_subscription_id TO billing_subscription_id;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. Ordering guard. Dodo states events can arrive out of order; an event older
--    than this is dropped. Without it a late subscription.active silently
--    re-grants a plan that was already cancelled.
-- ---------------------------------------------------------------------------
ALTER TABLE subscription ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMPTZ;

-- ---------------------------------------------------------------------------
-- 3. Idempotency. The PRIMARY KEY *is* the claim: Dodo retries a non-2xx eight
--    times, and the insert is what makes the second delivery lose. It must be
--    written in the same transaction as the entitlement change it guards, or a
--    redelivered subscription.renewed re-zeroes posts_used/generations_used and
--    hands the org a free extra period of quota.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS billing_webhook_event (
    webhook_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

-- Verify: expects billing_customer_id, billing_subscription_id, last_event_at
-- and no stripe_* columns.
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'subscription'
--     AND (column_name LIKE 'billing_%' OR column_name LIKE 'stripe_%'
--          OR column_name = 'last_event_at');
-- SELECT count(*) FROM billing_webhook_event;
