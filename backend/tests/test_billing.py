"""Unit tests for BillingService webhook handlers, quota checks, and usage.

Dodo network calls are fully mocked (the client is monkeypatched wholesale); the
DB is the in-memory SQLite fixture from conftest. These tests exercise the money
paths that decide which plan/limits an org gets and how usage is tracked, plus
the two delivery guards Dodo's semantics make mandatory rather than theoretical:
idempotency (eight retries on a non-2xx) and ordering (none guaranteed).
"""

from __future__ import annotations

import types
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from agency.models.tables import BillingWebhookEvent, Organization, Subscription
from agency.services.billing import (
    PLAN_CONFIG,
    BillingService,
    _tier_for_product_id,
)
from tests.conftest import create_org, create_subscription

STARTER = PLAN_CONFIG["starter"]["product_id"]
GROWTH = PLAN_CONFIG["growth"]["product_id"]
AGENCY = PLAN_CONFIG["agency"]["product_id"]


async def _get_sub(session_factory, org_id) -> Subscription:
    async with session_factory() as s:
        return (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()


async def _set_sub(session_factory, org_id, **fields: Any) -> None:
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        for key, value in fields.items():
            setattr(sub, key, value)
        await s.commit()


async def _claim_count(session_factory) -> int:
    async with session_factory() as s:
        return (
            await s.execute(select(func.count()).select_from(BillingWebhookEvent))
        ).scalar_one()


def _sub_event(
    event_type: str,
    *,
    org_id: UUID | str | None = None,
    product_id: str | None = None,
    customer_id: str | None = None,
    subscription_id: str | None = "sub_1",
    timestamp: str | None = None,
    **payload: Any,
) -> dict:
    """A Dodo ``subscription.*`` envelope.

    ``data`` *is* the Subscription object — Dodo does not nest it under
    ``data.object`` the way Stripe did.
    """
    data: dict[str, Any] = {
        "subscription_id": subscription_id,
        "metadata": {"org_id": str(org_id)} if org_id is not None else {},
        **payload,
    }
    if product_id is not None:
        data["product_id"] = product_id
    if customer_id is not None:
        data["customer"] = {"customer_id": customer_id}
    event: dict[str, Any] = {"type": event_type, "data": data}
    if timestamp is not None:
        event["timestamp"] = timestamp
    return event


# ---------------------------------------------------------------------------
# subscription.active -> activate correct plan + limits
# ---------------------------------------------------------------------------
async def test_subscription_active_upgrades_existing_sub(db, session_factory):
    org_id = await create_org(session_factory, "Upgrader")
    await create_subscription(session_factory, org_id, plan_tier="free")

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.active",
            org_id=org_id,
            product_id=GROWTH,
            customer_id="cus_123",
            subscription_id="sub_123",
        ),
        "wh_active_1",
    )

    assert result["status"] == "activated"
    assert result["plan"] == "growth"

    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "growth"
    assert sub.status == "active"
    assert sub.clients_limit == PLAN_CONFIG["growth"]["clients_limit"]
    assert sub.posts_limit == PLAN_CONFIG["growth"]["posts_limit"]
    assert sub.billing_customer_id == "cus_123"
    assert sub.billing_subscription_id == "sub_123"


async def test_subscription_active_creates_sub_when_absent(db, session_factory):
    org_id = await create_org(session_factory, "NewSubscriber")

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.active",
            org_id=org_id,
            product_id=STARTER,
            customer_id="cus_new",
            subscription_id="sub_new",
        ),
        "wh_active_2",
    )

    assert result["status"] == "activated"
    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "starter"
    assert sub.clients_limit == PLAN_CONFIG["starter"]["clients_limit"]
    assert sub.posts_limit == PLAN_CONFIG["starter"]["posts_limit"]


async def test_subscription_active_without_org_id_errors(db):
    """No ``metadata.org_id`` and no row to fall back on: refuse, never guess."""
    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event("subscription.active", product_id=GROWTH, subscription_id=None),
        "wh_active_noorg",
    )
    assert result["status"] == "error"
    assert result["reason"] == "no_org_for_subscription"


async def test_subscription_active_reentry_does_not_reset_usage(db, session_factory):
    """Dunning recovery re-fires ``active``; resetting here is a free period."""
    org_id = await create_org(session_factory, "Recovered")
    await create_subscription(
        session_factory,
        org_id,
        plan_tier="growth",
        posts_used=412,
        generations_used=9,
        status="on_hold",
        billing_customer_id="cus_recover",
    )

    svc = BillingService()
    await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.active",
            org_id=org_id,
            product_id=GROWTH,
            customer_id="cus_recover",
        ),
        "wh_reentry",
    )

    sub = await _get_sub(session_factory, org_id)
    assert sub.status == "active"
    assert sub.posts_used == 412
    assert sub.generations_used == 9


# ---------------------------------------------------------------------------
# subscription.renewed -> reset monthly usage  (Dodo emits no invoice.paid)
# ---------------------------------------------------------------------------
async def test_subscription_renewed_resets_posts_used(db, session_factory):
    org_id = await create_org(session_factory, "BillingCycle")
    await create_subscription(
        session_factory,
        org_id,
        plan_tier="starter",
        posts_limit=200,
        posts_used=137,
        generations_used=44,
        billing_customer_id="cus_reset",
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.renewed",
            org_id=org_id,
            product_id=STARTER,
            customer_id="cus_reset",
        ),
        "wh_renew_1",
    )

    assert result["status"] == "usage_reset"
    sub = await _get_sub(session_factory, org_id)
    assert sub.posts_used == 0
    assert sub.generations_used == 0
    # The tier is untouched — a renewal is not a plan change.
    assert sub.plan_tier == "starter"


async def test_redelivered_renewed_resets_usage_exactly_once(db, session_factory):
    """Dodo retries a non-2xx eight times with the same ``webhook-id``.

    Without the ``billing_webhook_event`` claim, every retry re-zeroes usage and
    hands the org another free period of quota.
    """
    org_id = await create_org(session_factory, "Retried")
    await create_subscription(
        session_factory,
        org_id,
        plan_tier="growth",
        posts_used=900,
        generations_used=200,
        billing_customer_id="cus_retry",
    )
    event = _sub_event(
        "subscription.renewed",
        org_id=org_id,
        product_id=GROWTH,
        customer_id="cus_retry",
    )

    svc = BillingService()
    first = await svc.handle_webhook(db, event, "wh_same_id")
    assert first["status"] == "usage_reset"

    # The org then spends quota inside the new period.
    await _set_sub(session_factory, org_id, posts_used=17, generations_used=3)

    second = await svc.handle_webhook(db, event, "wh_same_id")
    assert second["status"] == "duplicate"

    sub = await _get_sub(session_factory, org_id)
    assert sub.posts_used == 17
    assert sub.generations_used == 3
    assert await _claim_count(session_factory) == 1


async def test_claim_rolls_back_when_the_handler_raises(db, session_factory, monkeypatch):
    """A failed delivery must stay retryable.

    Claiming in its own transaction and committing separately is the classic way
    to *permanently* drop an event: the claim survives, the entitlement write
    does not, and every one of Dodo's eight retries then returns "duplicate".
    """
    org_id = await create_org(session_factory, "Flaky")
    await create_subscription(
        session_factory,
        org_id,
        plan_tier="growth",
        posts_used=500,
        generations_used=120,
        billing_customer_id="cus_flaky",
    )
    event = _sub_event(
        "subscription.renewed",
        org_id=org_id,
        product_id=GROWTH,
        customer_id="cus_flaky",
    )

    svc = BillingService()

    async def _boom(*args: Any, **kwargs: Any) -> dict:
        raise RuntimeError("downstream exploded")

    monkeypatch.setattr(svc, "_handle_subscription_renewed", _boom)
    with pytest.raises(RuntimeError):
        await svc.handle_webhook(db, event, "wh_retryable")
    await db.rollback()

    # Nothing was claimed and nothing was applied.
    assert await _claim_count(session_factory) == 0
    assert (await _get_sub(session_factory, org_id)).posts_used == 500

    # A fresh service (the un-monkeypatched handler) stands in for the ninth try.
    retry = await BillingService().handle_webhook(db, event, "wh_retryable")
    assert retry["status"] == "usage_reset"
    assert (await _get_sub(session_factory, org_id)).posts_used == 0


# ---------------------------------------------------------------------------
# Ordering: Dodo guarantees none
# ---------------------------------------------------------------------------
async def test_out_of_order_active_does_not_resurrect_a_cancelled_plan(db, session_factory):
    org_id = await create_org(session_factory, "Zombie")
    await create_subscription(
        session_factory,
        org_id,
        plan_tier="free",
        status="cancelled",
        billing_customer_id="cus_zombie",
    )
    await _set_sub(
        session_factory, org_id, last_event_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.active",
            org_id=org_id,
            product_id=GROWTH,
            customer_id="cus_zombie",
            timestamp="2026-09-19T12:00:00Z",
        ),
        "wh_stale",
    )

    assert result["status"] == "stale"
    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "free"
    assert sub.status == "cancelled"
    assert sub.clients_limit == PLAN_CONFIG["free"]["clients_limit"]


async def test_newer_event_is_applied_and_advances_last_event_at(db, session_factory):
    """The ordering guard drops only what is *older* — the control case."""
    org_id = await create_org(session_factory, "Ordered")
    await create_subscription(session_factory, org_id, plan_tier="free")
    await _set_sub(
        session_factory, org_id, last_event_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.active",
            org_id=org_id,
            product_id=GROWTH,
            customer_id="cus_ordered",
            timestamp="2026-09-21T12:00:00Z",
        ),
        "wh_fresh",
    )

    assert result["status"] == "activated"
    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "growth"
    assert sub.last_event_at is not None


# ---------------------------------------------------------------------------
# cancelled / expired — Dodo splits what Stripe called `deleted`
# ---------------------------------------------------------------------------
async def test_cancel_at_period_end_keeps_the_paid_tier(db, session_factory):
    """Downgrading on ``cancelled`` bills someone for a month they cannot use."""
    org_id = await create_org(session_factory, "Leaving")
    await create_subscription(
        session_factory,
        org_id,
        plan_tier="growth",
        clients_limit=10,
        posts_limit=1000,
        posts_used=500,
        billing_subscription_id="sub_leaving",
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.cancelled",
            org_id=org_id,
            product_id=GROWTH,
            subscription_id="sub_leaving",
            cancel_at_next_billing_date=True,
            next_billing_date="2026-10-20T00:00:00Z",
        ),
        "wh_cancel_scheduled",
    )

    assert result["status"] == "cancel_scheduled"
    assert result["plan"] == "growth"

    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "growth"
    assert sub.status == "cancelled"
    assert sub.clients_limit == PLAN_CONFIG["growth"]["clients_limit"]
    assert sub.posts_limit == PLAN_CONFIG["growth"]["posts_limit"]
    assert sub.current_period_end is not None


async def test_immediate_cancellation_downgrades_to_free(db, session_factory):
    org_id = await create_org(session_factory, "Churned")
    await create_subscription(
        session_factory,
        org_id,
        plan_tier="growth",
        clients_limit=10,
        posts_limit=1000,
        posts_used=500,
        status="active",
        billing_subscription_id="sub_cancel",
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.cancelled",
            org_id=org_id,
            product_id=GROWTH,
            subscription_id="sub_cancel",
            cancel_at_next_billing_date=False,
        ),
        "wh_cancel_now",
    )

    assert result["status"] == "cancelled"
    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "free"
    assert sub.status == "cancelled"
    assert sub.clients_limit == PLAN_CONFIG["free"]["clients_limit"]
    assert sub.posts_limit == PLAN_CONFIG["free"]["posts_limit"]


async def test_subscription_expired_downgrades_to_free(db, session_factory):
    """The only downgrade path for a normal, scheduled cancellation."""
    org_id = await create_org(session_factory, "Expired")
    await create_subscription(
        session_factory,
        org_id,
        plan_tier="agency",
        clients_limit=999,
        posts_limit=99999,
        status="cancelled",
        billing_subscription_id="sub_exp",
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.expired",
            org_id=org_id,
            product_id=AGENCY,
            subscription_id="sub_exp",
        ),
        "wh_expired",
    )

    assert result["status"] == "expired"
    assert result["plan"] == "free"

    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "free"
    assert sub.status == "expired"
    assert sub.clients_limit == PLAN_CONFIG["free"]["clients_limit"]
    assert sub.posts_limit == PLAN_CONFIG["free"]["posts_limit"]
    assert sub.generations_limit == PLAN_CONFIG["free"]["generations_limit"]


# ---------------------------------------------------------------------------
# on_hold / past_due — record, never revoke
# ---------------------------------------------------------------------------
async def test_on_hold_records_status_without_revoking_access(db, session_factory):
    org_id = await create_org(session_factory, "Dunning")
    await create_subscription(
        session_factory, org_id, plan_tier="growth", billing_customer_id="cus_hold"
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.on_hold",
            org_id=org_id,
            product_id=GROWTH,
            customer_id="cus_hold",
            status="on_hold",
        ),
        "wh_hold",
    )

    assert result["status"] == "noted"
    assert result["subscription_status"] == "on_hold"

    sub = await _get_sub(session_factory, org_id)
    assert sub.status == "on_hold"
    assert sub.plan_tier == "growth"
    assert sub.clients_limit == PLAN_CONFIG["growth"]["clients_limit"]


# ---------------------------------------------------------------------------
# Unknown product ids — never guess a tier
# ---------------------------------------------------------------------------
async def test_unknown_product_id_leaves_entitlements_untouched(db, session_factory):
    """A misconfigured ``DODO_PRODUCT_*`` must not mass-downgrade paying orgs."""
    org_id = await create_org(session_factory, "Mystery")
    await create_subscription(
        session_factory,
        org_id,
        plan_tier="agency",
        billing_subscription_id="sub_unk",
    )
    before = await _get_sub(session_factory, org_id)
    before_limits = (before.plan_tier, before.clients_limit, before.posts_limit)

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.plan_changed",
            org_id=org_id,
            product_id="pdt_not_in_config",
            subscription_id="sub_unk",
            status="active",
        ),
        "wh_unknown",
    )

    assert result["status"] == "error"
    assert result["reason"] == "unknown_product_id"
    assert result["product_id"] == "pdt_not_in_config"

    after = await _get_sub(session_factory, org_id)
    assert (after.plan_tier, after.clients_limit, after.posts_limit) == before_limits


def test_tier_lookup_ignores_blank_product_ids():
    """The free tier has ``product_id`` "" — a blank lookup must not match it."""
    assert _tier_for_product_id("") is None
    assert _tier_for_product_id(GROWTH) == "growth"
    assert _tier_for_product_id("pdt_nope") is None


# ---------------------------------------------------------------------------
# refund.succeeded — full refund only
# ---------------------------------------------------------------------------
async def test_full_refund_downgrades_to_free(db, session_factory):
    org_id = await create_org(session_factory, "Refunded")
    await create_subscription(
        session_factory, org_id, plan_tier="starter", billing_customer_id="cus_ref"
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        {
            "type": "refund.succeeded",
            "data": {
                "refund_id": "ref_1",
                "customer": {"customer_id": "cus_ref"},
                "amount": PLAN_CONFIG["starter"]["amount"],
                "is_partial": False,
            },
        },
        "wh_refund_full",
    )

    assert result["status"] == "refunded"
    assert result["plan"] == "free"

    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "free"
    assert sub.status == "refunded"
    assert sub.clients_limit == PLAN_CONFIG["free"]["clients_limit"]


async def test_partial_refund_changes_no_entitlement(db, session_factory):
    """``PLAN_CONFIG`` has no partial entitlement, so do not invent one."""
    org_id = await create_org(session_factory, "PartlyRefunded")
    await create_subscription(
        session_factory, org_id, plan_tier="starter", billing_customer_id="cus_part"
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        {
            "type": "refund.succeeded",
            "data": {
                "refund_id": "ref_2",
                "customer": {"customer_id": "cus_part"},
                "amount": 1000,
                "is_partial": True,
            },
        },
        "wh_refund_partial",
    )

    assert result["status"] == "noted"
    assert result["reason"] == "partial_refund"

    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "starter"
    assert sub.status == "active"
    assert sub.clients_limit == PLAN_CONFIG["starter"]["clients_limit"]


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
# create_checkout_session / create_portal_session with a mocked Dodo client
# ---------------------------------------------------------------------------
def _fake_client(
    *,
    checkout_url: str | None = "https://dodo.test/c/sess_mock",
    portal_link: str = "https://dodo.test/portal",
) -> tuple[Any, dict]:
    """A stand-in for ``AsyncDodoPayments``; returns it plus a kwargs spy."""
    seen: dict[str, Any] = {}

    async def _create(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return types.SimpleNamespace(session_id="sess_mock", checkout_url=checkout_url)

    async def _portal(customer_id: str, **kwargs: Any) -> Any:
        seen["customer_id"] = customer_id
        seen.update(kwargs)
        return types.SimpleNamespace(link=portal_link)

    client = types.SimpleNamespace(
        checkout_sessions=types.SimpleNamespace(create=_create),
        customers=types.SimpleNamespace(
            customer_portal=types.SimpleNamespace(create=_portal)
        ),
    )
    return client, seen


async def test_create_checkout_session_mocked_dodo(db, session_factory, monkeypatch):
    org_id = await create_org(session_factory, "CheckoutOrg")

    svc = BillingService()
    client, seen = _fake_client()
    monkeypatch.setattr(svc, "client", lambda: client)

    out = await svc.create_checkout_session(db, org_id, "starter", email="buyer@test.com")

    assert out["session_id"] == "sess_mock"
    assert out["checkout_url"] == "https://dodo.test/c/sess_mock"
    assert seen["product_cart"] == [{"product_id": STARTER, "quantity": 1}]
    assert seen["metadata"] == {"org_id": str(org_id), "plan_tier": "starter"}
    # No customer yet, so the org is identified by the caller's JWT email.
    assert seen["customer"]["email"] == "buyer@test.com"

    # Sanity: organization existed so the name lookup path executed.
    async with session_factory() as s:
        assert (
            await s.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none() is not None
    assert seen["customer"]["name"] == "CheckoutOrg"


async def test_create_checkout_session_reuses_existing_customer(db, session_factory, monkeypatch):
    org_id = await create_org(session_factory, "Returning")
    await create_subscription(
        session_factory, org_id, plan_tier="starter", billing_customer_id="cus_known"
    )

    svc = BillingService()
    client, seen = _fake_client()
    monkeypatch.setattr(svc, "client", lambda: client)

    out = await svc.create_checkout_session(db, org_id, "growth", email="buyer@test.com")

    assert out["checkout_url"]
    assert seen["customer"] == {"customer_id": "cus_known"}


async def test_create_checkout_session_refuses_a_null_checkout_url(
    db, session_factory, monkeypatch
):
    """``checkout_url`` is Optional on the response model, and a null there means
    Dodo accepted the session but produced nothing for the browser to open."""
    org_id = await create_org(session_factory, "NullUrl")

    svc = BillingService()
    client, _ = _fake_client(checkout_url=None)
    monkeypatch.setattr(svc, "client", lambda: client)

    out = await svc.create_checkout_session(db, org_id, "starter", email="buyer@test.com")
    assert out["error_status"] == 502
    assert "checkout_url" not in out


async def test_create_checkout_session_rejects_free_plan(db, session_factory):
    org_id = await create_org(session_factory, "FreePlanOrg")
    svc = BillingService()
    out = await svc.create_checkout_session(db, org_id, "free")
    assert out == {"error": "Invalid plan"}


async def test_create_checkout_session_without_billing_configured(db, session_factory):
    org_id = await create_org(session_factory, "Unconfigured")
    svc = BillingService()  # no DODO_API_KEY in the test env -> client() is None
    out = await svc.create_checkout_session(db, org_id, "starter", email="a@test.com")
    assert out["error_status"] == 503


async def test_create_portal_session_returns_the_link(db, session_factory, monkeypatch):
    org_id = await create_org(session_factory, "PortalOrg")
    await create_subscription(
        session_factory, org_id, plan_tier="growth", billing_customer_id="cus_portal"
    )

    svc = BillingService()
    client, seen = _fake_client()
    monkeypatch.setattr(svc, "client", lambda: client)

    out = await svc.create_portal_session(db, org_id)
    assert out == {"portal_url": "https://dodo.test/portal"}
    assert seen["customer_id"] == "cus_portal"


async def test_create_portal_session_without_a_customer_is_409(db, session_factory, monkeypatch):
    """A free org has never had a customer created — that is a 409, not a 500."""
    org_id = await create_org(session_factory, "NoCustomer")
    await create_subscription(session_factory, org_id, plan_tier="free")

    svc = BillingService()
    client, _ = _fake_client()
    monkeypatch.setattr(svc, "client", lambda: client)

    out = await svc.create_portal_session(db, org_id)
    assert out["error_status"] == 409


# ---------------------------------------------------------------------------
# Unsubscribed events are acknowledged, not exploded on
# ---------------------------------------------------------------------------
async def test_unhandled_event_type_is_ignored(db, session_factory):
    svc = BillingService()
    result = await svc.handle_webhook(
        db, {"type": "payment.succeeded", "data": {}}, "wh_ignored"
    )
    assert result["status"] == "ignored"
    assert result["event_type"] == "payment.succeeded"


async def test_renewed_for_an_unknown_subscription_is_not_reported_as_a_reset(db):
    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        _sub_event(
            "subscription.renewed",
            org_id=uuid4(),
            product_id=GROWTH,
            customer_id="cus_nobody",
        ),
        "wh_renew_nobody",
    )
    assert result["status"] == "ignored"
    assert result["reason"] == "no_subscription"
