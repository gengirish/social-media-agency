"""Unit tests for BillingService webhook handlers, quota checks, and usage.

Stripe network calls are fully mocked via monkeypatch; the DB is the in-memory
SQLite fixture from conftest. These tests exercise the money paths that decide
which plan/limits an org gets and how usage is tracked.
"""

import types

from sqlalchemy import select

from agency.models.tables import Organization, Subscription
from agency.services.billing import PLAN_CONFIG, BillingService
from tests.conftest import create_org, create_subscription


async def _get_sub(session_factory, org_id):
    async with session_factory() as s:
        return (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()


# ---------------------------------------------------------------------------
# checkout.session.completed -> activate correct plan + limits
# ---------------------------------------------------------------------------
async def test_checkout_completed_upgrades_existing_sub(db, session_factory):
    org_id = await create_org(session_factory, "Upgrader")
    await create_subscription(session_factory, org_id, plan_tier="free")

    svc = BillingService()
    result = await svc._handle_checkout_completed(
        db,
        {
            "metadata": {"org_id": str(org_id), "plan_tier": "growth"},
            "subscription": "sub_123",
            "customer": "cus_123",
        },
    )

    assert result["status"] == "activated"
    assert result["plan"] == "growth"

    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "growth"
    assert sub.status == "active"
    assert sub.clients_limit == PLAN_CONFIG["growth"]["clients_limit"]
    assert sub.posts_limit == PLAN_CONFIG["growth"]["posts_limit"]
    assert sub.stripe_customer_id == "cus_123"
    assert sub.stripe_subscription_id == "sub_123"


async def test_checkout_completed_creates_sub_when_absent(db, session_factory):
    org_id = await create_org(session_factory, "NewSubscriber")

    svc = BillingService()
    result = await svc._handle_checkout_completed(
        db,
        {
            "metadata": {"org_id": str(org_id), "plan_tier": "starter"},
            "subscription": "sub_new",
            "customer": "cus_new",
        },
    )

    assert result["status"] == "activated"
    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "starter"
    assert sub.clients_limit == PLAN_CONFIG["starter"]["clients_limit"]
    assert sub.posts_limit == PLAN_CONFIG["starter"]["posts_limit"]


async def test_checkout_completed_without_org_id_errors(db):
    svc = BillingService()
    result = await svc._handle_checkout_completed(db, {"metadata": {}})
    assert "error" in result


# ---------------------------------------------------------------------------
# invoice.paid -> reset monthly usage
# ---------------------------------------------------------------------------
async def test_invoice_paid_resets_posts_used(db, session_factory):
    org_id = await create_org(session_factory, "BillingCycle")
    await create_subscription(
        session_factory,
        org_id,
        plan_tier="starter",
        posts_limit=200,
        posts_used=137,
        stripe_customer_id="cus_reset",
    )

    svc = BillingService()
    result = await svc._handle_invoice_paid(db, {"customer": "cus_reset"})

    assert result["status"] == "usage_reset"
    sub = await _get_sub(session_factory, org_id)
    assert sub.posts_used == 0


# ---------------------------------------------------------------------------
# customer.subscription.deleted -> downgrade to free with free limits
# ---------------------------------------------------------------------------
async def test_subscription_cancelled_downgrades_to_free(db, session_factory):
    org_id = await create_org(session_factory, "Churned")
    await create_subscription(
        session_factory,
        org_id,
        plan_tier="growth",
        clients_limit=10,
        posts_limit=1000,
        posts_used=500,
        status="active",
        stripe_subscription_id="sub_cancel",
    )

    svc = BillingService()
    result = await svc._handle_subscription_cancelled(db, {"id": "sub_cancel"})

    assert result["status"] == "cancelled"
    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "free"
    assert sub.status == "cancelled"
    assert sub.clients_limit == PLAN_CONFIG["free"]["clients_limit"]
    assert sub.posts_limit == PLAN_CONFIG["free"]["posts_limit"]


# ---------------------------------------------------------------------------
# check_quota boundary behaviour
# ---------------------------------------------------------------------------
async def test_check_quota_true_below_limit(db, session_factory):
    org_id = await create_org(session_factory, "UnderLimit")
    await create_subscription(session_factory, org_id, posts_limit=30, posts_used=29)

    svc = BillingService()
    assert await svc.check_quota(db, org_id, resource="posts") is True


async def test_check_quota_false_at_limit(db, session_factory):
    org_id = await create_org(session_factory, "AtLimit")
    await create_subscription(session_factory, org_id, posts_limit=30, posts_used=30)

    svc = BillingService()
    assert await svc.check_quota(db, org_id, resource="posts") is False


async def test_check_quota_false_when_no_subscription(db, session_factory):
    org_id = await create_org(session_factory, "NoSub")
    svc = BillingService()
    assert await svc.check_quota(db, org_id, resource="posts") is False


async def test_check_quota_non_post_resource_is_allowed(db, session_factory):
    org_id = await create_org(session_factory, "OtherResource")
    await create_subscription(session_factory, org_id, posts_limit=1, posts_used=99)
    svc = BillingService()
    assert await svc.check_quota(db, org_id, resource="clients") is True


# ---------------------------------------------------------------------------
# record_post_published -> increments usage
# ---------------------------------------------------------------------------
async def test_record_post_published_increments(db, session_factory):
    org_id = await create_org(session_factory, "Publisher")
    await create_subscription(session_factory, org_id, posts_used=5)

    svc = BillingService()
    await svc.record_post_published(db, org_id)
    await db.commit()

    sub = await _get_sub(session_factory, org_id)
    assert sub.posts_used == 6


async def test_record_post_published_no_sub_is_noop(db, session_factory):
    org_id = await create_org(session_factory, "PublisherNoSub")
    svc = BillingService()
    # Should not raise even though no subscription exists.
    assert await svc.record_post_published(db, org_id) is None


# ---------------------------------------------------------------------------
# create_checkout_session with a mocked stripe module
# ---------------------------------------------------------------------------
async def test_create_checkout_session_mocked_stripe(db, session_factory, monkeypatch):
    from agency.services import billing as billing_mod

    org_id = await create_org(session_factory, "CheckoutOrg")

    fake_stripe = types.SimpleNamespace()
    fake_stripe.api_key = None
    fake_stripe.Customer = types.SimpleNamespace(
        create=lambda **kw: types.SimpleNamespace(id="cus_mock")
    )
    fake_stripe.checkout = types.SimpleNamespace(
        Session=types.SimpleNamespace(
            create=lambda **kw: types.SimpleNamespace(
                id="sess_mock", url="https://stripe.test/checkout/sess_mock"
            )
        )
    )
    monkeypatch.setattr(billing_mod, "stripe", fake_stripe)

    svc = billing_mod.BillingService()
    out = await svc.create_checkout_session(db, org_id, "starter")

    assert out["session_id"] == "sess_mock"
    assert out["checkout_url"] == "https://stripe.test/checkout/sess_mock"

    # Sanity: organization existed so the customer lookup path executed.
    async with session_factory() as s:
        assert (
            await s.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none() is not None


async def test_create_checkout_session_rejects_free_plan(db, session_factory):
    org_id = await create_org(session_factory, "FreePlanOrg")
    svc = BillingService()
    out = await svc.create_checkout_session(db, org_id, "free")
    assert out == {"error": "Invalid plan"}
