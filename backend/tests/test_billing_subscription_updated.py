"""``customer.subscription.updated`` handler tests.

This handler was ``return {"status": "noted"}`` while registered in the webhook
map, so Stripe plan changes were discarded behind a success-shaped body. These
tests pin the behaviour that replaced it, including the two refusals: an
unrecognised price id and an unmatched subscription must both leave
entitlements untouched rather than guess.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from agency.models.tables import Subscription
from agency.services.billing import PLAN_CONFIG, BillingService, _tier_for_price_id
from tests.conftest import create_org, create_subscription


async def _get_sub(session_factory, org_id):
    async with session_factory() as s:
        return (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()


def _event(sub_id: str, price_id: str, **extra) -> dict:
    return {
        "id": sub_id,
        "items": {"data": [{"price": {"id": price_id}}]},
        **extra,
    }


async def test_upgrade_applies_new_limits(db, session_factory):
    org_id = await create_org(session_factory, "Upgrader")
    await create_subscription(
        session_factory, org_id, plan_tier="starter", stripe_subscription_id="sub_up"
    )

    svc = BillingService()
    result = await svc._handle_subscription_updated(
        db, _event("sub_up", PLAN_CONFIG["growth"]["price_id"], status="active")
    )

    assert result["status"] == "updated"
    assert result["plan"] == "growth"

    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "growth"
    assert sub.clients_limit == PLAN_CONFIG["growth"]["clients_limit"]
    assert sub.posts_limit == PLAN_CONFIG["growth"]["posts_limit"]


async def test_downgrade_lowers_limits(db, session_factory):
    org_id = await create_org(session_factory, "Downgrader")
    await create_subscription(
        session_factory, org_id, plan_tier="growth", stripe_subscription_id="sub_down"
    )

    svc = BillingService()
    result = await svc._handle_subscription_updated(
        db, _event("sub_down", PLAN_CONFIG["starter"]["price_id"], status="active")
    )

    assert result["plan"] == "starter"

    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "starter"
    assert sub.clients_limit == PLAN_CONFIG["starter"]["clients_limit"]
    assert sub.posts_limit == PLAN_CONFIG["starter"]["posts_limit"]


async def test_past_due_status_is_persisted(db, session_factory):
    """The state must land in the row even though nothing enforces on it yet."""
    org_id = await create_org(session_factory, "Lapsed")
    await create_subscription(
        session_factory, org_id, plan_tier="growth", stripe_subscription_id="sub_pd"
    )

    svc = BillingService()
    result = await svc._handle_subscription_updated(
        db, _event("sub_pd", PLAN_CONFIG["growth"]["price_id"], status="past_due")
    )

    assert result["subscription_status"] == "past_due"

    sub = await _get_sub(session_factory, org_id)
    assert sub.status == "past_due"
    # Limits are unchanged — lockout is a separate policy decision.
    assert sub.plan_tier == "growth"
    assert sub.clients_limit == PLAN_CONFIG["growth"]["clients_limit"]


async def test_unknown_price_id_changes_nothing(db, session_factory):
    """A misconfigured STRIPE_PRICE_* must not silently re-tier a customer."""
    org_id = await create_org(session_factory, "Mystery")
    await create_subscription(
        session_factory, org_id, plan_tier="agency", stripe_subscription_id="sub_unk"
    )
    before = await _get_sub(session_factory, org_id)
    before_limits = (before.plan_tier, before.clients_limit, before.posts_limit)

    svc = BillingService()
    result = await svc._handle_subscription_updated(
        db, _event("sub_unk", "price_not_in_config", status="active")
    )

    assert result["status"] == "error"
    assert result["reason"] == "unknown_price_id"

    after = await _get_sub(session_factory, org_id)
    assert (after.plan_tier, after.clients_limit, after.posts_limit) == before_limits


async def test_no_local_subscription_is_ignored_not_raised(db, session_factory):
    svc = BillingService()
    result = await svc._handle_subscription_updated(
        db, _event("sub_does_not_exist", PLAN_CONFIG["growth"]["price_id"])
    )

    assert result["status"] == "ignored"
    assert result["reason"] == "no_local_subscription"


async def test_period_timestamps_become_tz_aware(db, session_factory):
    org_id = await create_org(session_factory, "Periods")
    await create_subscription(
        session_factory, org_id, plan_tier="starter", stripe_subscription_id="sub_per"
    )

    start = int(datetime(2026, 9, 1, tzinfo=UTC).timestamp())
    end = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp())

    svc = BillingService()
    await svc._handle_subscription_updated(
        db,
        _event(
            "sub_per",
            PLAN_CONFIG["starter"]["price_id"],
            status="active",
            current_period_start=start,
            current_period_end=end,
        ),
    )

    sub = await _get_sub(session_factory, org_id)
    assert sub.current_period_start is not None
    assert sub.current_period_end is not None
    assert sub.current_period_start.year == 2026
    assert sub.current_period_end.month == 10


async def test_empty_items_is_treated_as_unknown_price(db, session_factory):
    """Stripe can send an update with no line items; do not crash or guess."""
    org_id = await create_org(session_factory, "NoItems")
    await create_subscription(
        session_factory, org_id, plan_tier="growth", stripe_subscription_id="sub_noitems"
    )

    svc = BillingService()
    result = await svc._handle_subscription_updated(
        db, {"id": "sub_noitems", "items": {"data": []}, "status": "active"}
    )

    assert result["status"] == "error"
    assert result["reason"] == "unknown_price_id"

    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "growth"


def test_tier_lookup_ignores_blank_price_ids():
    """The free tier has price_id "" — a blank lookup must not match it."""
    assert _tier_for_price_id("") is None
    assert _tier_for_price_id(PLAN_CONFIG["growth"]["price_id"]) == "growth"


async def test_handler_is_reachable_through_the_webhook_map(db, session_factory):
    """Guards against the handler being wired out of handle_webhook."""
    org_id = await create_org(session_factory, "Routed")
    await create_subscription(
        session_factory, org_id, plan_tier="starter", stripe_subscription_id="sub_route"
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        {
            "type": "customer.subscription.updated",
            "data": {
                "object": _event(
                    "sub_route", PLAN_CONFIG["growth"]["price_id"], status="active"
                )
            },
        },
    )

    assert result["status"] == "updated"
    assert result["plan"] == "growth"
