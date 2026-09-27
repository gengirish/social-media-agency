"""Dodo Payments billing service — subscriptions, checkout, webhooks."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from dodopayments import AsyncDodoPayments
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agency.config import get_settings
from agency.models.tables import BillingWebhookEvent, Organization, Subscription

logger = structlog.get_logger()

_s = get_settings()

# Pricing anchor (260926): deliberately 20% under Metricool's USD **monthly list**,
# matched on their brand count vs our clients_limit. Fetched from
# metricool.com/pricing on 260926:
#
#   Metricool monthly      -> our tier          20% lower
#   Starter,  5 brands $25 -> starter (3)       $20   (2000)
#   Starter, 10 brands $45 -> growth (10)       $36   (3600)
#   Advanced,50 brands $210-> agency (unlimited)$168  (16800)
#
# Their top "Custom" tier has no public price, so agency is anchored on the
# largest published Advanced band rather than a like-for-like plan.
# `amount` is DISPLAY COPY ONLY -- the Dodo product's own price is what actually
# charges. They can drift; the go-live check in the Dodo plan doc reads each
# product back and asserts the two agree. Change one, change both, and mirror
# the figures in frontend/src/app/page.tsx and (dashboard)/pricing/page.tsx.
PLAN_CONFIG = {
    "free": {
        "product_id": "",
        "clients_limit": 1,
        "posts_limit": 30,
        "campaigns_limit": 5,
        # Amplify packs per billing period (1 pack = up to 8 drafts). Sized so a
        # tier's packs roughly cover its publishing allowance with room to drop
        # atoms at review. Mirrored in db/migrations/260921_amplify.sql.
        "generations_limit": 10,
        # CF-11: this said "No publishing" beside a "Published posts 0/30" meter.
        # The meter was right and the feature line was wrong — nothing gates
        # publishing by plan, and `posts_limit` above is 30, so a free org can
        # and does publish. Blocking it to match the copy would take away a
        # capability real orgs are using; the copy is what was untrue.
        "features": ["1 client", "5 campaigns/mo", "30 published posts/mo"],
    },
    "starter": {
        "product_id": _s.dodo_product_starter or "pdt_starter",
        "clients_limit": 3,
        "posts_limit": 200,
        "campaigns_limit": 20,
        "generations_limit": 50,
        "amount": 2000,
        # No report is ever emailed (nothing in reports.py sends mail), so
        # "Email reports" was dropped in the 260817 stub audit.
        "features": ["3 clients", "20 campaigns/mo", "2 platforms"],
    },
    "growth": {
        "product_id": _s.dodo_product_growth or "pdt_growth",
        "clients_limit": 10,
        "posts_limit": 1000,
        "campaigns_limit": 9999,
        "generations_limit": 250,
        "amount": 3600,
        "features": [
            "10 clients",
            "Unlimited campaigns",
            "All platforms",
            "Analytics",
            # No seat limit exists in PLAN_CONFIG or is enforced anywhere, so
            # "Team (3 seats)" was dropped in the 260817 stub audit.
            "Team workspaces",
        ],
    },
    "agency": {
        "product_id": _s.dodo_product_agency or "pdt_agency",
        "clients_limit": 999,
        "posts_limit": 99999,
        "campaigns_limit": 9999,
        "generations_limit": 9999,
        "amount": 16800,
        "features": [
            "Unlimited clients",
            "Unlimited campaigns",
            "All platforms",
            "White-label",
            "Priority support",
            "API access",
        ],
    },
}


#: How a workspace describes itself -> which plans its pricing page offers.
#:
#: PRESENTATION ONLY. Every profile bills against the same four ``PLAN_CONFIG``
#: tiers, the same amounts and the same Dodo ``product_id``s; a profile decides
#: only which of them are shown, in what order, and which one is called out.
#: Nothing here grants a capability or changes a limit -- ``subscription`` remains
#: the sole source of truth for what an org may do.
#:
#: ``tiers`` is also the display order. ``recommended`` must be one of them.
WORKSPACE_PROFILES: dict[str, dict] = {
    "product_owner": {
        "label": "Product owner",
        "description": "One product, marketed by the person who builds it.",
        "tiers": ["free", "starter", "growth"],
        "recommended": "starter",
        # Why this tier: one product = one client, so the client ceiling never
        # binds; what does bind is publishing at all, which Starter is the first
        # tier to allow.
        "reason": "One product is one client — Starter is the first tier that can publish.",
    },
    "freelancer": {
        "label": "Freelancer / consultant",
        "description": "A handful of clients, all of them run by you.",
        "tiers": ["starter", "growth", "agency"],
        "recommended": "growth",
        "reason": "Growth lifts the client ceiling to 10 and opens every platform.",
    },
    "organization": {
        "label": "Agency / organization",
        "description": "A team running many client brands, with seats and white-label.",
        "tiers": ["growth", "agency"],
        "recommended": "agency",
        "reason": "Agency is the only tier with white-label, API access and no client cap.",
    },
}


def normalize_workspace_profile(value: str | None) -> str | None:
    """A recognised profile key, or ``None``.

    ``None`` is a real state -- "never chosen" -- and renders the full plan grid.
    An unrecognised string (a stale row, a hand-edited database) normalises to
    ``None`` rather than raising, so a bad value can never hide a plan someone
    is entitled to buy.
    """
    return value if value in WORKSPACE_PROFILES else None


def plans_for_profile(profile: str | None, current_tier: str | None = None) -> list[dict]:
    """The plan list a workspace of this profile should see, in display order.

    Two invariants, both load-bearing:

    * ``current_tier`` is **always** included, even when the profile would not
      offer it. Hiding the plan someone is already paying for would make their
      own subscription unrepresentable on the billing screen.
    * An unknown profile falls through to every plan. Fail open -- this is a
      storefront, and the failure mode of guessing wrong is a hidden product.
    """
    key = normalize_workspace_profile(profile)
    if key is None:
        tiers = list(PLAN_CONFIG)
    else:
        cfg = WORKSPACE_PROFILES[key]
        tiers = [t for t in cfg["tiers"] if t in PLAN_CONFIG]
        if current_tier and current_tier in PLAN_CONFIG and current_tier not in tiers:
            # Keep PLAN_CONFIG's own ordering rather than appending, so the grid
            # never reads free -> growth -> starter.
            tiers = [t for t in PLAN_CONFIG if t in {*tiers, current_tier}]
    recommended = WORKSPACE_PROFILES[key]["recommended"] if key else None
    return [
        {"tier": t, **PLAN_CONFIG[t], "recommended": t == recommended}
        for t in tiers
    ]


def workspace_profile_catalog() -> list[dict]:
    """The choosable profiles, for the picker. Order is the dict's order."""
    return [
        {
            "id": key,
            "label": cfg["label"],
            "description": cfg["description"],
            "recommended_tier": cfg["recommended"],
            "reason": cfg["reason"],
        }
        for key, cfg in WORKSPACE_PROFILES.items()
    ]


def generations_limit_for(sub: Subscription) -> int:
    """The org's Amplify pack allowance.

    A NULL column (a row created before 260921 that the migration's backfill
    missed, e.g. an unknown tier) falls back to the tier's PLAN_CONFIG value,
    then to the free tier -- never to "unlimited".
    """
    if sub.generations_limit is not None:
        return int(sub.generations_limit)
    plan = PLAN_CONFIG.get(str(sub.plan_tier), PLAN_CONFIG["free"])
    return int(plan["generations_limit"])


def _tier_for_product_id(product_id: str) -> str | None:
    """Reverse ``PLAN_CONFIG``'s ``product_id`` -> tier.

    Returns ``None`` for an unrecognised id so callers can refuse to act rather
    than guess. Blank ids (the free tier, and unconfigured ``DODO_PRODUCT_*``
    vars) never match.
    """
    if not product_id:
        return None
    for tier, cfg in PLAN_CONFIG.items():
        if cfg["product_id"] and cfg["product_id"] == product_id:
            return tier
    return None


def _as_utc(value: Any) -> datetime | None:
    """Coerce a webhook timestamp or a DB column into an aware UTC datetime.

    Dodo sends RFC 3339 strings; SQLAlchemy hands back aware datetimes on
    Postgres and naive ones on SQLite. Comparing the two raises, and a raise
    inside the ordering guard would 500 the webhook and earn eight retries.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _plan_amount(tier: str) -> int | None:
    """The tier's list price in cents, or ``None`` for a tier that has no price."""
    amount = PLAN_CONFIG.get(tier, {}).get("amount")
    return int(amount) if isinstance(amount, int) else None


class BillingService:
    def __init__(self) -> None:
        self._client: AsyncDodoPayments | None = None

    def client(self) -> AsyncDodoPayments | None:
        """The Dodo client, or ``None`` when no API key is configured.

        Built lazily and cached. ``AsyncDodoPayments`` *raises* on a missing
        bearer token, so constructing it at import time would take the whole app
        down on any deployment that simply has not configured billing yet --
        which is every environment except production.
        """
        settings = get_settings()
        if not settings.dodo_api_key:
            return None
        if self._client is None:
            self._client = AsyncDodoPayments(
                bearer_token=settings.dodo_api_key,
                webhook_key=settings.dodo_webhook_key or None,
                environment=settings.dodo_environment,
            )
        return self._client

    async def create_checkout_session(
        self,
        db: AsyncSession,
        org_id: UUID,
        plan_tier: str,
        success_url: str | None = None,
        cancel_url: str | None = None,
        email: str | None = None,
        full_name: str | None = None,
    ) -> dict:
        """Create a Dodo checkout session for a subscription.

        ``email``/``full_name`` come from the caller's JWT payload. Dodo has no
        mandatory customer pre-create step: an org that has never paid is
        identified by email, one that has is attached by ``customer_id``.
        """
        plan = PLAN_CONFIG.get(plan_tier)
        if not plan or plan_tier == "free":
            return {"error": "Invalid plan"}

        client = self.client()
        if client is None:
            return {"error": "Billing is not configured", "error_status": 503}

        base = (_s.frontend_url or "http://localhost:3000").rstrip("/")
        return_url = success_url or f"{base}/settings?checkout=success"
        cancel_url = cancel_url or f"{base}/pricing?checkout=cancel"

        result = await db.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()

        customer: dict[str, Any] | None = None
        if sub and sub.billing_customer_id:
            customer = {"customer_id": sub.billing_customer_id}
        elif email:
            name = full_name
            if not name:
                org_row = await db.execute(select(Organization).where(Organization.id == org_id))
                org = org_row.scalar_one_or_none()
                name = org.name if org else None
            customer = {"email": email, "name": name}
        else:
            # Dodo requires an email to create a customer. Failing here beats a
            # 422 from the API with no hint of which field was missing.
            return {"error": "No billing email for this account"}

        session = await client.checkout_sessions.create(
            product_cart=[{"product_id": plan["product_id"], "quantity": 1}],
            customer=customer,  # type: ignore[arg-type]
            metadata={"org_id": str(org_id), "plan_tier": plan_tier},
            return_url=return_url,
            cancel_url=cancel_url,
        )
        if not session.checkout_url:
            # Optional on the response model, and a null here means Dodo accepted
            # the session but produced nothing for the browser to open. Returning
            # it would send the customer to "undefined".
            logger.error(
                "dodo_checkout_url_missing",
                org_id=str(org_id),
                plan=plan_tier,
                session_id=session.session_id,
            )
            return {"error": "Payment provider returned no checkout URL", "error_status": 502}
        return {"checkout_url": session.checkout_url, "session_id": session.session_id}

    async def create_portal_session(
        self, db: AsyncSession, org_id: UUID, return_url: str | None = None
    ) -> dict:
        """A Dodo customer-portal link: cancel, change card, download invoices.

        Requires a customer to exist, which only happens once an org has been
        through checkout. A free org has none, and that is a 409 (nothing to
        manage), not a 500.
        """
        client = self.client()
        if client is None:
            return {"error": "Billing is not configured", "error_status": 503}

        result = await db.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()
        customer_id = sub.billing_customer_id if sub else None
        if not customer_id:
            return {"error": "No billing account for this workspace", "error_status": 409}

        base = (_s.frontend_url or "http://localhost:3000").rstrip("/")
        session = await client.customers.customer_portal.create(
            str(customer_id),
            return_url=return_url or f"{base}/settings",
        )
        # CustomerPortalSession's only field is `link` -- not `url`.
        return {"portal_url": session.link}

    # --- webhooks -----------------------------------------------------------

    async def handle_webhook(self, db: AsyncSession, event: dict, webhook_id: str) -> dict:
        """Apply one Dodo webhook, exactly once, in one transaction.

        Two invariants, both of which Dodo's delivery semantics make mandatory
        rather than theoretical:

        * **Idempotency.** Dodo retries a non-2xx eight times. The insert into
          ``billing_webhook_event`` is the claim, and it happens in the *same*
          transaction as the entitlement write -- claim-then-commit-separately is
          how an event gets permanently dropped when the handler later raises.
        * **Ordering.** Dodo does not guarantee order. Anything older than the
          row's ``last_event_at`` is dropped, or a late ``subscription.active``
          silently re-grants a plan that was already cancelled.

        Handlers below never commit; this method commits once, at the end.
        """
        event_type = str(event.get("type") or "")
        data = event.get("data") or {}
        occurred_at = _as_utc(event.get("timestamp"))

        db.add(BillingWebhookEvent(webhook_id=webhook_id, event_type=event_type))
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            logger.info("dodo_webhook_duplicate", webhook_id=webhook_id, event_type=event_type)
            return {"status": "duplicate", "event_type": event_type}

        handlers = {
            "subscription.active": self._handle_subscription_active,
            "subscription.renewed": self._handle_subscription_renewed,
            "subscription.plan_changed": self._handle_subscription_plan_changed,
            "subscription.updated": self._handle_subscription_plan_changed,
            "subscription.cancelled": self._handle_subscription_cancelled,
            "subscription.expired": self._handle_subscription_expired,
            "subscription.failed": self._handle_subscription_failed,
            "subscription.on_hold": self._handle_subscription_status_only,
            "subscription.past_due": self._handle_subscription_status_only,
            "subscription.paused": self._handle_subscription_status_only,
            "subscription.unpaused": self._handle_subscription_status_only,
            "refund.succeeded": self._handle_refund_succeeded,
            "dispute.lost": self._handle_dispute_lost,
        }
        handler = handlers.get(event_type)
        if handler is None:
            await db.commit()
            return {"status": "ignored", "event_type": event_type}

        org_id, sub = await self._resolve_subscription(db, event_type, data)

        if sub is not None and occurred_at is not None:
            previous = _as_utc(sub.last_event_at)
            if previous is not None and occurred_at < previous:
                logger.warning(
                    "dodo_webhook_out_of_order",
                    webhook_id=webhook_id,
                    event_type=event_type,
                    org_id=str(sub.org_id),
                )
                await db.commit()
                return {"status": "stale", "event_type": event_type}

        outcome = await handler(db, data, org_id, sub)

        if sub is None:
            # ``subscription.active`` creates the row when an org checks out for
            # the first time. Re-resolve so that row gets a ``last_event_at`` too,
            # or its very first ordering guard has nothing to compare against.
            _, sub = await self._resolve_subscription(db, event_type, data)
        if sub is not None and occurred_at is not None:
            sub.last_event_at = occurred_at
        await db.commit()
        return outcome

    async def _resolve_subscription(
        self, db: AsyncSession, event_type: str, data: dict
    ) -> tuple[UUID | None, Subscription | None]:
        """Find the local row an event applies to, by whatever the payload carries.

        ``metadata.org_id`` first -- it is a required field on every
        ``subscription.*`` payload, so it survives renewals and cancels. The
        ``billing_customer_id`` fallback costs one query and covers a
        subscription created outside our checkout (support re-creating one in the
        Dodo dashboard), which carries no ``org_id``.
        """
        org_id: UUID | None = None
        raw_org = (data.get("metadata") or {}).get("org_id")
        if raw_org:
            try:
                org_id = UUID(str(raw_org))
            except ValueError:
                logger.warning("dodo_webhook_bad_org_id", event_type=event_type, org_id=raw_org)

        customer_id = (data.get("customer") or {}).get("customer_id")
        if event_type == "dispute.lost":
            # The dispute payload carries a payment_id and no customer at all, so
            # the owning customer has to be read back from the payment.
            customer_id = await self._customer_for_payment(data.get("payment_id"))

        if org_id is not None:
            result = await db.execute(select(Subscription).where(Subscription.org_id == org_id))
            sub = result.scalar_one_or_none()
            if sub is not None:
                return org_id, sub

        if customer_id:
            result = await db.execute(
                select(Subscription).where(Subscription.billing_customer_id == customer_id)
            )
            sub = result.scalar_one_or_none()
            if sub is not None:
                return org_id or sub.org_id, sub

        subscription_id = data.get("subscription_id")
        if subscription_id:
            result = await db.execute(
                select(Subscription).where(Subscription.billing_subscription_id == subscription_id)
            )
            sub = result.scalar_one_or_none()
            if sub is not None:
                return org_id or sub.org_id, sub

        return org_id, None

    async def _customer_for_payment(self, payment_id: Any) -> str | None:
        client = self.client()
        if not payment_id or client is None:
            return None
        try:
            payment = await client.payments.retrieve(str(payment_id))
        except Exception as exc:  # noqa: BLE001 - never 500 a webhook over a lookup
            logger.error("dodo_payment_lookup_failed", payment_id=str(payment_id), error=str(exc))
            return None
        return payment.customer.customer_id

    def _apply_plan(self, sub: Subscription, tier: str) -> None:
        plan = PLAN_CONFIG[tier]
        sub.plan_tier = tier
        sub.clients_limit = plan["clients_limit"]
        sub.posts_limit = plan["posts_limit"]
        sub.generations_limit = plan["generations_limit"]

    def _apply_period(self, sub: Subscription, data: dict) -> None:
        start = _as_utc(data.get("previous_billing_date"))
        end = _as_utc(data.get("next_billing_date"))
        if start:
            sub.current_period_start = start
        if end:
            sub.current_period_end = end

    def _downgrade_to_free(self, sub: Subscription, status: str) -> None:
        self._apply_plan(sub, "free")
        sub.status = status

    async def _handle_subscription_active(
        self, db: AsyncSession, data: dict, org_id: UUID | None, sub: Subscription | None
    ) -> dict:
        """First activation, and recovery from ``on_hold``.

        Must be re-entrant: Dodo fires this again when dunning recovers a
        subscription, so it overwrites rather than "activates again". Usage is
        deliberately NOT reset here -- that belongs to ``subscription.renewed``,
        and resetting on every recovery would hand out a free extra period.
        """
        tier = _tier_for_product_id(str(data.get("product_id") or ""))
        if tier is None:
            return self._unknown_product(data, org_id, sub)

        if sub is None:
            if org_id is None:
                logger.error("dodo_subscription_active_unresolvable", data_keys=sorted(data))
                return {"status": "error", "reason": "no_org_for_subscription"}
            sub = Subscription(org_id=org_id, plan_tier=tier)
            db.add(sub)

        # Merge, never overwrite with nothing. A payload that omits the customer
        # block would otherwise NULL an id we already hold, which silently breaks
        # both the portal (409 "no customer") and customer-id webhook resolution
        # for an org that is perfectly healthy.
        customer_id = (data.get("customer") or {}).get("customer_id")
        if customer_id:
            sub.billing_customer_id = customer_id
        subscription_id = data.get("subscription_id")
        if subscription_id:
            sub.billing_subscription_id = subscription_id
        self._apply_plan(sub, tier)
        self._apply_period(sub, data)
        sub.status = "active"
        logger.info("subscription_activated", org_id=str(sub.org_id), plan=tier)
        return {"status": "activated", "plan": tier}

    async def _handle_subscription_renewed(
        self, db: AsyncSession, data: dict, org_id: UUID | None, sub: Subscription | None
    ) -> dict:
        """Reset the period's usage. **The highest-consequence handler here.**

        Dodo emits no ``invoice.paid``; ``subscription.renewed`` is the only
        signal that a new billing period has been paid for. Miss it and every
        paying org's publishing and Amplify quotas never reset -- they pay and
        then 402 for the rest of the year.
        """
        if sub is None:
            # Do not report a reset that did not happen -- an unmatched
            # subscription means this deployment does not know the org, which is
            # an operational signal, not a no-op.
            logger.warning("dodo_renewed_no_subscription", org_id=str(org_id))
            return {"status": "ignored", "reason": "no_subscription"}

        sub.posts_used = 0
        sub.generations_used = 0
        sub.status = "active"
        self._apply_period(sub, data)
        logger.info("subscription_usage_reset", org_id=str(sub.org_id), plan=sub.plan_tier)
        return {"status": "usage_reset"}

    async def _handle_subscription_plan_changed(
        self, db: AsyncSession, data: dict, org_id: UUID | None, sub: Subscription | None
    ) -> dict:
        """Re-derive the tier from the payload's ``product_id``.

        ``plan_changed`` also fires when ``cancel_at_next_billing_date`` is
        toggled and when add-ons change, so the event alone means nothing -- only
        the product id does. ``status`` is taken from Dodo verbatim; whether
        ``past_due`` or ``on_hold`` restricts access is a separate policy
        decision, and inventing that enforcement inside a webhook handler would
        hide it.
        """
        if sub is None:
            logger.warning("dodo_plan_changed_no_subscription", org_id=str(org_id))
            return {"status": "ignored", "reason": "no_subscription"}

        tier = _tier_for_product_id(str(data.get("product_id") or ""))
        if tier is None:
            return self._unknown_product(data, org_id, sub)

        self._apply_plan(sub, tier)
        self._apply_period(sub, data)
        sub.status = data.get("status") or sub.status
        logger.info(
            "subscription_updated",
            org_id=str(sub.org_id),
            plan=tier,
            subscription_status=sub.status,
        )
        return {"status": "updated", "plan": tier, "subscription_status": sub.status}

    async def _handle_subscription_cancelled(
        self, db: AsyncSession, data: dict, org_id: UUID | None, sub: Subscription | None
    ) -> dict:
        """Cancellation *requested*. Usually not a downgrade.

        With ``cancel_at_next_billing_date`` the customer has paid through
        ``next_billing_date`` and keeps the tier until ``subscription.expired``
        arrives. Downgrading here bills someone for a month they cannot use.
        """
        if sub is None:
            logger.warning("dodo_cancelled_no_subscription", org_id=str(org_id))
            return {"status": "ignored", "reason": "no_subscription"}

        sub.status = "cancelled"
        if data.get("cancel_at_next_billing_date"):
            self._apply_period(sub, data)
            logger.info(
                "subscription_cancel_scheduled",
                org_id=str(sub.org_id),
                plan=sub.plan_tier,
                ends_at=str(sub.current_period_end),
            )
            return {"status": "cancel_scheduled", "plan": sub.plan_tier}

        self._downgrade_to_free(sub, "cancelled")
        logger.info("subscription_cancelled", org_id=str(sub.org_id))
        return {"status": "cancelled", "plan": "free"}

    async def _handle_subscription_expired(
        self, db: AsyncSession, data: dict, org_id: UUID | None, sub: Subscription | None
    ) -> dict:
        """The paid period actually ran out -- the only downgrade path for a
        normal cancellation."""
        if sub is None:
            logger.warning("dodo_expired_no_subscription", org_id=str(org_id))
            return {"status": "ignored", "reason": "no_subscription"}
        self._downgrade_to_free(sub, "expired")
        logger.info("subscription_expired", org_id=str(sub.org_id))
        return {"status": "expired", "plan": "free"}

    async def _handle_subscription_failed(
        self, db: AsyncSession, data: dict, org_id: UUID | None, sub: Subscription | None
    ) -> dict:
        """Terminal: the initial mandate never took, so the org never had access.

        Record the status and leave the tier alone -- it is still whatever it was
        before the attempt, which for a first-time buyer is free.
        """
        if sub is None:
            return {"status": "ignored", "reason": "no_subscription"}
        sub.status = "failed"
        logger.warning("subscription_failed", org_id=str(sub.org_id), plan=sub.plan_tier)
        return {"status": "failed", "plan": sub.plan_tier}

    async def _handle_subscription_status_only(
        self, db: AsyncSession, data: dict, org_id: UUID | None, sub: Subscription | None
    ) -> dict:
        """``on_hold`` / ``past_due`` / ``paused`` / ``unpaused``: record, never revoke.

        Dodo retries and dunning routinely recovers these, so revoking access
        here would lock out customers who are about to pay. Nothing in this
        codebase enforces on ``subscription.status`` -- that is deliberate, and
        adding the first enforcement inside a webhook handler would hide it.
        """
        if sub is None:
            return {"status": "ignored", "reason": "no_subscription"}
        sub.status = data.get("status") or sub.status
        logger.info(
            "subscription_status_recorded",
            org_id=str(sub.org_id),
            subscription_status=sub.status,
        )
        return {"status": "noted", "subscription_status": sub.status}

    async def _handle_refund_succeeded(
        self, db: AsyncSession, data: dict, org_id: UUID | None, sub: Subscription | None
    ) -> dict:
        """Downgrade only on a full refund of the period's price.

        A full-period refund and an immediate downgrade are the consistent pair.
        A partial refund is not: ``PLAN_CONFIG`` has no concept of partial
        entitlement, so anything short of the plan's ``amount`` is logged and
        changes nothing rather than being guessed at.
        """
        if sub is None:
            logger.warning("dodo_refund_no_subscription", refund_id=data.get("refund_id"))
            return {"status": "ignored", "reason": "no_subscription"}

        amount = data.get("amount")
        expected = _plan_amount(str(sub.plan_tier))
        if data.get("is_partial") or expected is None or amount != expected:
            logger.info(
                "billing_partial_refund_no_change",
                org_id=str(sub.org_id),
                refund_id=data.get("refund_id"),
                amount=amount,
                plan_amount=expected,
            )
            return {"status": "noted", "reason": "partial_refund"}

        self._downgrade_to_free(sub, "refunded")
        logger.info("subscription_refunded", org_id=str(sub.org_id), amount=amount)
        return {"status": "refunded", "plan": "free"}

    async def _handle_dispute_lost(
        self, db: AsyncSession, data: dict, org_id: UUID | None, sub: Subscription | None
    ) -> dict:
        """Chargeback upheld: the money is gone and so is the entitlement."""
        if sub is None:
            logger.warning("dodo_dispute_no_subscription", dispute_id=data.get("dispute_id"))
            return {"status": "ignored", "reason": "no_subscription"}
        self._downgrade_to_free(sub, "disputed")
        logger.warning(
            "subscription_dispute_lost",
            org_id=str(sub.org_id),
            dispute_id=data.get("dispute_id"),
        )
        return {"status": "disputed", "plan": "free"}

    def _unknown_product(self, data: dict, org_id: UUID | None, sub: Subscription | None) -> dict:
        """Never guess a tier.

        Defaulting to "starter" would mean a misconfigured DODO_PRODUCT_* env var
        quietly downgrades every paying customer, so leave entitlements untouched
        and log loudly.
        """
        product_id = str(data.get("product_id") or "")
        logger.error(
            "dodo_unknown_product_id",
            subscription_id=data.get("subscription_id"),
            product_id=product_id,
            org_id=str(sub.org_id) if sub is not None else str(org_id),
        )
        return {"status": "error", "reason": "unknown_product_id", "product_id": product_id}

    async def get_subscription(self, db: AsyncSession, org_id: UUID) -> dict:
        result = await db.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()
        if not sub:
            return {
                "plan_tier": "free",
                **PLAN_CONFIG["free"],
                "generations_used": 0,
                "has_billing_customer": False,
            }
        plan = PLAN_CONFIG.get(sub.plan_tier, {})
        return {
            "plan_tier": sub.plan_tier,
            "status": sub.status,
            "clients_limit": sub.clients_limit,
            "posts_limit": sub.posts_limit,
            "posts_used": sub.posts_used,
            **plan,
            # After the spread: the row's usage and limit are the truth, not the
            # tier default (which would hide a per-org override).
            "generations_used": sub.generations_used or 0,
            "generations_limit": generations_limit_for(sub),
            # Whether a Dodo customer portal can be opened at all. The UI needs an
            # honest signal here: gating the "Manage billing" button on
            # plan_tier != "free" hides it from an org that cancelled down to free
            # but still has a customer id -- whose invoices and reactivation the
            # portal would happily serve.
            "has_billing_customer": bool(sub.billing_customer_id),
        }

    async def check_quota(self, db: AsyncSession, org_id: UUID, resource: str = "posts") -> bool:
        result = await db.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()
        if not sub:
            return False
        if resource == "posts":
            return sub.posts_used < sub.posts_limit
        return True

    async def record_post_published(self, db: AsyncSession, org_id: UUID) -> None:
        """Increment monthly post usage after a successful publish."""
        result = await db.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()
        if not sub:
            logger.warning("record_post_published_no_subscription", org_id=str(org_id))
            return
        sub.posts_used = (sub.posts_used or 0) + 1

    def get_plans(self) -> list:
        return [{"tier": k, **v} for k, v in PLAN_CONFIG.items()]

    async def get_workspace_profile(self, db: AsyncSession, org_id: UUID) -> str | None:
        """The org's stored profile, normalised. Never raises on a stale value."""
        result = await db.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        return normalize_workspace_profile(org.workspace_profile if org else None)

    async def set_workspace_profile(
        self, db: AsyncSession, org_id: UUID, profile: str | None
    ) -> str | None:
        """Store the org's profile. ``None`` clears it back to "never chosen".

        Rejects an unrecognised key rather than storing it -- the column has a
        CHECK constraint, and a 400 here is a better error than a database one.
        Changing this does not touch the subscription: it is a display choice,
        so it never starts, stops or reprices anything.
        """
        if profile is not None and profile not in WORKSPACE_PROFILES:
            raise ValueError(f"Unknown workspace profile: {profile}")
        result = await db.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if not org:
            raise ValueError("Organization not found")
        org.workspace_profile = profile
        await db.commit()
        logger.info("workspace_profile_set", org_id=str(org_id), profile=profile)
        return profile


billing = BillingService()
