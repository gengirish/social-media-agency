"""Stripe billing service — subscriptions, checkout, webhooks."""

from uuid import UUID

import stripe
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.config import get_settings
from agency.models.tables import Organization, Subscription

logger = structlog.get_logger()

PLAN_CONFIG = {
    "free": {
        "price_id": "",
        "clients_limit": 1,
        "posts_limit": 30,
        "features": ["1 client", "5 campaigns/mo", "No publishing"],
    },
    "starter": {
        "price_id": "price_starter",
        "clients_limit": 3,
        "posts_limit": 200,
        "amount": 4900,
        "features": ["3 clients", "20 campaigns/mo", "2 platforms", "Email reports"],
    },
    "growth": {
        "price_id": "price_growth",
        "clients_limit": 10,
        "posts_limit": 1000,
        "amount": 14900,
        "features": [
            "10 clients",
            "Unlimited campaigns",
            "All platforms",
            "Analytics",
            "Team (3 seats)",
        ],
    },
    "agency": {
        "price_id": "price_agency",
        "clients_limit": 999,
        "posts_limit": 99999,
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


class BillingService:
    def __init__(self):
        settings = get_settings()
        stripe.api_key = settings.stripe_secret_key or None

    async def create_checkout_session(
        self,
        db: AsyncSession,
        org_id: UUID,
        plan_tier: str,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """Create a Stripe Checkout session for subscription."""
        plan = PLAN_CONFIG.get(plan_tier)
        if not plan or plan_tier == "free":
            return {"error": "Invalid plan"}

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
            sub.status = "active"
        else:
            sub = Subscription(
                org_id=org_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
                plan_tier=plan_tier,
                clients_limit=plan["clients_limit"],
                posts_limit=plan["posts_limit"],
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
        if sub:
            sub.posts_used = 0  # Reset usage on new billing period
            await db.commit()
        return {"status": "usage_reset"}

    async def _handle_subscription_cancelled(self, db: AsyncSession, data: dict) -> dict:
        sub_id = data.get("id")
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == sub_id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.status = "cancelled"
            sub.plan_tier = "free"
            sub.clients_limit = 1
            sub.posts_limit = 30
            await db.commit()
        return {"status": "cancelled"}

    async def _handle_subscription_updated(self, db: AsyncSession, data: dict) -> dict:
        return {"status": "noted"}

    async def get_subscription(self, db: AsyncSession, org_id: UUID) -> dict:
        result = await db.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()
        if not sub:
            return {"plan_tier": "free", **PLAN_CONFIG["free"]}
        plan = PLAN_CONFIG.get(sub.plan_tier, {})
        return {
            "plan_tier": sub.plan_tier,
            "status": sub.status,
            "clients_limit": sub.clients_limit,
            "posts_limit": sub.posts_limit,
            "posts_used": sub.posts_used,
            **plan,
        }

    async def check_quota(self, db: AsyncSession, org_id: UUID, resource: str = "posts") -> bool:
        result = await db.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()
        if not sub:
            return False
        if resource == "posts":
            return sub.posts_used < sub.posts_limit
        return True

    def get_plans(self) -> list:
        return [{"tier": k, **v} for k, v in PLAN_CONFIG.items()]


billing = BillingService()
