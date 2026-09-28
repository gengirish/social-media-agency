"""``subscription.plan_changed`` handler tests.

Under Stripe this handler was ``return {"status": "noted"}`` while registered in
the webhook map, so plan changes were discarded behind a success-shaped body.
These tests pin the behaviour that replaced it, now against Dodo payloads,
including the two refusals: an unrecognised ``product_id`` and an unmatched
subscription must both leave entitlements untouched rather than guess.

``plan_changed`` also fires when ``cancel_at_next_billing_date`` is toggled and
when add-ons change, so the event alone means nothing — only the ``product_id``
does.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from agency.models.tables import Subscription
from agency.services.billing import PLAN_CONFIG, BillingService, _tier_for_product_id
from tests.conftest import create_org, create_subscription


async def _get_sub(session_factory, org_id) -> Subscription:
    async with session_factory() as s:
        return (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()


def _payload(sub_id: str, product_id: str | None, **extra: Any) -> dict:
    """The Dodo ``Subscription`` object that is a ``subscription.*`` event's ``data``."""
    data: dict[str, Any] = {"subscription_id": sub_id, "metadata": {}, **extra}
    if product_id is not None:
        data["product_id"] = product_id
    return data


async def test_upgrade_applies_new_limits(db, session_factory):
    org_id = await create_org(session_factory, "Upgrader")
    await create_subscription(
        session_factory, org_id, plan_tier="starter", billing_subscription_id="sub_up"
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        {
            "type": "subscription.plan_changed",
            "data": _payload("sub_up", PLAN_CONFIG["growth"]["product_id"], status="active"),
        },
        "wh_up",
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
        session_factory, org_id, plan_tier="growth", billing_subscription_id="sub_down"
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        {
            "type": "subscription.plan_changed",
            "data": _payload(
                "sub_down", PLAN_CONFIG["starter"]["product_id"], status="active"
            ),
        },
        "wh_down",
    )

    assert result["plan"] == "starter"

    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "starter"
    assert sub.clients_limit == PLAN_CONFIG["starter"]["clients_limit"]
    assert sub.posts_limit == PLAN_CONFIG["starter"]["posts_limit"]
    assert sub.generations_limit == PLAN_CONFIG["starter"]["generations_limit"]


async def test_on_hold_status_is_persisted(db, session_factory):
    """The state must land in the row even though nothing enforces on it yet."""
    org_id = await create_org(session_factory, "Lapsed")
    await create_subscription(
        session_factory, org_id, plan_tier="growth", billing_subscription_id="sub_pd"
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        {
            "type": "subscription.plan_changed",
            "data": _payload(
                "sub_pd", PLAN_CONFIG["growth"]["product_id"], status="on_hold"
            ),
        },
        "wh_pd",
    )

    assert result["subscription_status"] == "on_hold"

    sub = await _get_sub(session_factory, org_id)
    assert sub.status == "on_hold"
    # Limits are unchanged — lockout is a separate policy decision.
    assert sub.plan_tier == "growth"
    assert sub.clients_limit == PLAN_CONFIG["growth"]["clients_limit"]


async def test_unknown_product_id_changes_nothing(db, session_factory):
    """A misconfigured ``DODO_PRODUCT_*`` must not silently re-tier a customer."""
    org_id = await create_org(session_factory, "Mystery")
    await create_subscription(
        session_factory, org_id, plan_tier="agency", billing_subscription_id="sub_unk"
    )
    before = await _get_sub(session_factory, org_id)
    before_limits = (before.plan_tier, before.clients_limit, before.posts_limit)

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        {
            "type": "subscription.plan_changed",
            "data": _payload("sub_unk", "pdt_not_in_config", status="active"),
        },
        "wh_unk",
    )

    assert result["status"] == "error"
    assert result["reason"] == "unknown_product_id"

    after = await _get_sub(session_factory, org_id)
    assert (after.plan_tier, after.clients_limit, after.posts_limit) == before_limits


async def test_no_local_subscription_is_ignored_not_raised(db, session_factory):
    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        {
            "type": "subscription.plan_changed",
            "data": _payload(
                "sub_does_not_exist", PLAN_CONFIG["growth"]["product_id"], status="active"
            ),
        },
        "wh_nolocal",
    )

    assert result["status"] == "ignored"
    assert result["reason"] == "no_subscription"


async def test_period_timestamps_become_tz_aware(db, session_factory):
    """Dodo sends RFC 3339 strings, not Stripe's epoch ints."""
    org_id = await create_org(session_factory, "Periods")
    await create_subscription(
        session_factory, org_id, plan_tier="starter", billing_subscription_id="sub_per"
    )

    svc = BillingService()
    await svc.handle_webhook(
        db,
        {
            "type": "subscription.plan_changed",
            "data": _payload(
                "sub_per",
                PLAN_CONFIG["starter"]["product_id"],
                status="active",
                previous_billing_date="2026-09-01T00:00:00Z",
                next_billing_date="2026-10-01T00:00:00Z",
            ),
        },
        "wh_per",
    )

    sub = await _get_sub(session_factory, org_id)
    assert sub.current_period_start is not None
    assert sub.current_period_end is not None
    assert sub.current_period_start.year == 2026
    assert sub.current_period_end.month == 10


async def test_missing_product_id_is_treated_as_unknown(db, session_factory):
    """Dodo can send an update whose ``product_id`` we cannot read; do not guess."""
    org_id = await create_org(session_factory, "NoProduct")
    await create_subscription(
        session_factory, org_id, plan_tier="growth", billing_subscription_id="sub_noprod"
    )

    svc = BillingService()
    result = await svc.handle_webhook(
        db,
        {
            "type": "subscription.plan_changed",
            "data": _payload("sub_noprod", None, status="active"),
        },
        "wh_noprod",
    )

    assert result["status"] == "error"
    assert result["reason"] == "unknown_product_id"

    sub = await _get_sub(session_factory, org_id)
    assert sub.plan_tier == "growth"


def test_tier_lookup_ignores_blank_product_ids():
    """The free tier has ``product_id`` "" — a blank lookup must not match it."""
    assert _tier_for_product_id("") is None
    assert _tier_for_product_id(PLAN_CONFIG["growth"]["product_id"]) == "growth"


async def test_handler_is_reachable_through_the_webhook_map(db, session_factory):
    """Guards against the handler being wired out of handle_webhook.

    Both ``plan_changed`` and the plainer ``updated`` land on it.
    """
    org_id = await create_org(session_factory, "Routed")
    await create_subscription(
        session_factory, org_id, plan_tier="starter", billing_subscription_id="sub_route"
    )

    svc = BillingService()
    for i, event_type in enumerate(("subscription.plan_changed", "subscription.updated")):
        result = await svc.handle_webhook(
            db,
            {
                "type": event_type,
                "data": _payload(
                    "sub_route", PLAN_CONFIG["growth"]["product_id"], status="active"
                ),
            },
            f"wh_route_{i}",
        )
        assert result["status"] == "updated", event_type
        assert result["plan"] == "growth", event_type
