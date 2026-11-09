-- 261109 — organization.account_type: backfill 'business' for paid multi-client plans.
--
-- Data only, no schema change; safe to re-run. The UI hides "Add client" on a
-- 'personal' workspace, and until now only a team invite flipped it, so an org
-- that paid for a plan with clients_limit > 1 still could not add a second
-- client. services/billing.py::_unlock_clients now flips it when such a plan is
-- applied; this catches orgs that bought one before that shipped.
--
-- One-way, like the invite flip: nothing here (or in code) turns a business
-- workspace back into a personal one.

UPDATE organization
SET account_type = 'business'
WHERE account_type <> 'business'
  AND id IN (SELECT org_id FROM subscription WHERE clients_limit > 1);
