"""Stripe billing service — subscriptions, checkout, webhooks."""

from datetime import UTC, datetime
from uuid import UUID

import stripe
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.config import get_settings
from agency.models.tables import Organization, Subscription

logger = structlog.get_logger()

_s = get_settings()
PLAN_CONFIG = {
    "free": {
        "price_id": "",
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
        "price_id": _s.stripe_price_starter or "price_starter",
        "clients_limit": 3,
        "posts_limit": 200,
        "campaigns_limit": 20,
        "generations_limit": 50,
        "amount": 4900,
        # No report is ever emailed (nothing in reports.py sends mail), so
        # "Email reports" was dropped in the 260817 stub audit.
        "features": ["3 clients", "20 campaigns/mo", "2 platforms"],
    },
    "growth": {
        "price_id": _s.stripe_price_growth or "price_growth",
        "clients_limit": 10,
        "posts_limit": 1000,
        "campaigns_limit": 9999,
        "generations_limit": 250,
        "amount": 14900,
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
        "price_id": _s.stripe_price_agency or "price_agency",
        "clients_limit": 999,
        "posts_limit": 99999,
        "campaigns_limit": 9999,
        "generations_limit": 9999,
        "amount": 39900,
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
#: tiers, the same amounts and the same Stripe ``price_id``s; a profile decides
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


def _tier_for_price_id(price_id: str) -> str | None:
    """Reverse ``PLAN_CONFIG``'s ``price_id`` -> tier.

    Returns ``None`` for an unrecognised id so callers can refuse to act rather
    than guess. Blank ids (the free tier, and unconfigured ``STRIPE_PRICE_*``
    vars) never match.
    """
    if not price_id:
        return None
    for tier, cfg in PLAN_CONFIG.items():
        if cfg["price_id"] and cfg["price_id"] == price_id:
            return tier
    return None


class BillingService:
    def __init__(self):
        settings = get_settings()
        stripe.api_key = settings.stripe_secret_key or None

    async def create_checkout_session(
        self,
        db: AsyncSession,
        org_id: UUID,
        plan_tier: str,
        success_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict:
        """Create a Stripe Checkout session for subscription."""
        plan = PLAN_CONFIG.get(plan_tier)
        if not plan or plan_tier == "free":
            return {"error": "Invalid plan"}

        base = (_s.frontend_url or "http://localhost:3000").rstrip("/")
        success_url = success_url or f"{base}/settings?checkout=success"
        cancel_url = cancel_url or f"{base}/pricing?checkout=cancel"

        result = await db.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()

        customer_id = sub.stripe_customer_id if sub else None
        if not customer_id:
            result = await db.execute(select(Organization).where(Organization.id == org_id))
            org = result.scalar_one_or_none()
            customer = stripe.Customer.create(
                name=org.name if org else "Unknown",
                metadata={"org_id": str(org_id)},
            )
            customer_id = customer.id
            if sub:
                sub.stripe_customer_id = customer_id
                await db.commit()

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": plan["price_id"], "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"org_id": str(org_id), "plan_tier": plan_tier},
        )
        return {"checkout_url": session.url, "session_id": session.id}

    async def handle_webhook(self, db: AsyncSession, event: dict) -> dict:
        """Process Stripe webhook events."""
        event_type = event.get("type", "")
        data = event.get("data", {}).get("object", {})

        handlers = {
            "checkout.session.completed": self._handle_checkout_completed,
            "invoice.paid": self._handle_invoice_paid,
            "customer.subscription.deleted": self._handle_subscription_cancelled,
            "customer.subscription.updated": self._handle_subscription_updated,
        }

        handler = handlers.get(event_type)
        if handler:
            return await handler(db, data)
        return {"status": "ignored", "event_type": event_type}

    async def _handle_checkout_completed(self, db: AsyncSession, data: dict) -> dict:
        org_id_raw = data.get("metadata", {}).get("org_id")
        plan_tier = data.get("metadata", {}).get("plan_tier", "starter")
        subscription_id = data.get("subscription")
        customer_id = data.get("customer")

        if not org_id_raw:
            return {"error": "No org_id in metadata"}

        org_id = UUID(str(org_id_raw))
        plan = PLAN_CONFIG.get(plan_tier, PLAN_CONFIG["starter"])

        result = await db.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()

        if sub:
            sub.stripe_customer_id = customer_id
            sub.stripe_subscription_id = subscription_id
            sub.plan_tier = plan_tier
            sub.clients_limit = plan["clients_limit"]
            sub.posts_limit = plan["posts_limit"]
            sub.generations_limit = plan["generations_limit"]  # type: ignore[assignment]
            sub.status = "active"
        else:
            sub = Subscription(
                org_id=org_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
                plan_tier=plan_tier,
                clients_limit=plan["clients_limit"],
                posts_limit=plan["posts_limit"],
                generations_limit=plan["generations_limit"],
                status="active",
            )
            db.add(sub)

        await db.commit()
        logger.info("subscription_activated", org_id=str(org_id), plan=plan_tier)
        return {"status": "activated", "plan": plan_tier}

    async def _handle_invoice_paid(self, db: AsyncSession, data: dict) -> dict:
        customer_id = data.get("customer")
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_customer_id == customer_id)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            # Do not report a reset that did not happen — an unmatched customer means the
            # webhook is for a subscription this deployment does not know about, which is
            # an operational signal, not a no-op.
            logger.warning("stripe_invoice_paid_no_subscription", customer_id=str(customer_id))
            return {"status": "ignored", "reason": "no_subscription_for_customer"}

        sub.posts_used = 0  # Reset usage on new billing period
        sub.generations_used = 0  # type: ignore[assignment]
        await db.commit()
        return {"status": "usage_reset"}

    async def _handle_subscription_cancelled(self, db: AsyncSession, data: dict) -> dict:
        sub_id = data.get("id")
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == sub_id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            free = PLAN_CONFIG["free"]
            sub.status = "cancelled"
            sub.plan_tier = "free"
            sub.clients_limit = free["clients_limit"]
            sub.posts_limit = free["posts_limit"]
            sub.generations_limit = free["generations_limit"]  # type: ignore[assignment]
            await db.commit()
        return {"status": "cancelled"}

    async def _handle_subscription_updated(self, db: AsyncSession, data: dict) -> dict:
        """Apply a Stripe plan change to the local subscription.

        Was previously ``return {"status": "noted"}`` — registered in the
        handler map, so every upgrade, downgrade and ``past_due`` transition
        returned a success-shaped body and changed nothing. A customer who
        downgraded kept their old limits indefinitely.

        ``status`` is taken from Stripe verbatim, so ``past_due`` / ``unpaid``
        land in the row. Whether those states restrict access is a separate
        policy decision — nothing enforces on ``status`` today, and inventing
        that enforcement inside a webhook handler would hide it.
        """
        sub_id = data.get("id")
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == sub_id)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            # Mirrors _handle_invoice_paid: an unmatched subscription is an
            # operational signal, not a no-op.
            logger.warning("stripe_subscription_updated_no_local_sub", subscription_id=sub_id)
            return {"status": "ignored", "reason": "no_local_subscription"}

        items = data.get("items", {}).get("data", [])
        price_id = items[0].get("price", {}).get("id", "") if items else ""
        tier = _tier_for_price_id(price_id)

        if tier is None:
            # Never guess a tier. Defaulting to "starter" would mean a
            # misconfigured STRIPE_PRICE_* env var quietly downgrades every
            # paying customer, so leave entitlements untouched and log loudly.
            logger.error(
                "stripe_unknown_price_id",
                subscription_id=sub_id,
                price_id=price_id,
                org_id=str(sub.org_id),
            )
            return {"status": "error", "reason": "unknown_price_id", "price_id": price_id}

        plan = PLAN_CONFIG[tier]
        sub.plan_tier = tier
        sub.clients_limit = plan["clients_limit"]
        sub.posts_limit = plan["posts_limit"]
        sub.generations_limit = plan["generations_limit"]  # type: ignore[assignment]
        sub.status = data.get("status") or sub.status

        for column, key in (
            ("current_period_start", "current_period_start"),
            ("current_period_end", "current_period_end"),
        ):
            ts = data.get(key)
            if ts:
                setattr(sub, column, datetime.fromtimestamp(ts, tz=UTC))

        await db.commit()
        logger.info(
            "subscription_updated",
            org_id=str(sub.org_id),
            plan=tier,
            subscription_status=sub.status,
        )
        return {"status": "updated", "plan": tier, "subscription_status": sub.status}

    async def get_subscription(self, db: AsyncSession, org_id: UUID) -> dict:
        result = await db.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()
        if not sub:
            return {"plan_tier": "free", **PLAN_CONFIG["free"], "generations_used": 0}
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
