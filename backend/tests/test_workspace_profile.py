"""The workspace profile that reshapes the pricing page.

The profile is a *storefront* setting: it decides which of the four PLAN_CONFIG
tiers a workspace is offered, in what order, and which one is called out. It is
not a tier, it grants nothing, and it changes no amount. These tests pin the two
ways that could go wrong in a way nobody would notice:

* a plan someone is already paying for disappearing from their own billing page
* a bad stored value hiding plans entirely, rather than falling back to all of them

Both fail open -- a storefront that hides a product is worse than one that shows
too many.
"""

import pytest
from sqlalchemy import select

from agency.models.tables import Organization
from agency.services.billing import (
    PLAN_CONFIG,
    WORKSPACE_PROFILES,
    BillingService,
    normalize_workspace_profile,
    plans_for_profile,
    workspace_profile_catalog,
)
from tests.conftest import create_org


def _tiers(plans):
    return [p["tier"] for p in plans]


# ---------------------------------------------------------------------------
# The catalogue itself
# ---------------------------------------------------------------------------
def test_every_profile_offers_only_real_tiers_and_recommends_one_of_them():
    for key, cfg in WORKSPACE_PROFILES.items():
        assert cfg["tiers"], f"{key} offers no plans"
        for tier in cfg["tiers"]:
            assert tier in PLAN_CONFIG, f"{key} offers unknown tier {tier}"
        assert cfg["recommended"] in cfg["tiers"], (
            f"{key} recommends {cfg['recommended']}, which it does not offer"
        )


def test_catalog_exposes_one_entry_per_profile():
    catalog = workspace_profile_catalog()
    assert [c["id"] for c in catalog] == list(WORKSPACE_PROFILES)
    for entry in catalog:
        assert entry["label"] and entry["description"] and entry["reason"]


def test_no_profile_changes_any_price():
    """A profile picks which plans are shown -- never what they cost."""
    for key in WORKSPACE_PROFILES:
        for plan in plans_for_profile(key):
            source = PLAN_CONFIG[plan["tier"]]
            assert plan.get("amount") == source.get("amount")
            assert plan.get("price_id") == source.get("price_id")


# ---------------------------------------------------------------------------
# Shaping
# ---------------------------------------------------------------------------
def test_unset_profile_shows_every_plan_and_recommends_nothing():
    plans = plans_for_profile(None)
    assert _tiers(plans) == list(PLAN_CONFIG)
    assert not any(p["recommended"] for p in plans)


@pytest.mark.parametrize("bogus", ["", "enterprise", "product-owner", "PRODUCT_OWNER"])
def test_unrecognised_profile_falls_back_to_every_plan(bogus):
    """Fail open: a stale or hand-edited value must not hide a purchasable plan."""
    assert normalize_workspace_profile(bogus) is None
    assert _tiers(plans_for_profile(bogus)) == list(PLAN_CONFIG)


def test_profile_filters_and_marks_exactly_one_recommendation():
    plans = plans_for_profile("organization")
    assert _tiers(plans) == WORKSPACE_PROFILES["organization"]["tiers"]
    assert [p["tier"] for p in plans if p["recommended"]] == [
        WORKSPACE_PROFILES["organization"]["recommended"]
    ]


def test_current_plan_is_never_hidden_from_its_own_billing_page():
    """An org on Free with the 'organization' profile still sees Free.

    'organization' offers growth+agency only, so without this the person paying
    for -- or sitting on -- another tier could not see their own subscription.
    """
    assert "free" not in WORKSPACE_PROFILES["organization"]["tiers"]
    plans = plans_for_profile("organization", current_tier="free")
    assert "free" in _tiers(plans)


def test_reinstated_current_plan_keeps_plan_config_order():
    """free is prepended, not appended -- the grid never reads growth, agency, free."""
    plans = plans_for_profile("organization", current_tier="free")
    assert _tiers(plans) == [t for t in PLAN_CONFIG if t in set(_tiers(plans))]


def test_unknown_current_tier_is_ignored_rather_than_injected():
    plans = plans_for_profile("organization", current_tier="legacy_enterprise")
    assert _tiers(plans) == WORKSPACE_PROFILES["organization"]["tiers"]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
async def test_profile_round_trips_and_clears(db, session_factory):
    org_id = await create_org(session_factory, "Profiled")
    svc = BillingService()

    assert await svc.get_workspace_profile(db, org_id) is None

    assert await svc.set_workspace_profile(db, org_id, "freelancer") == "freelancer"
    assert await svc.get_workspace_profile(db, org_id) == "freelancer"

    assert await svc.set_workspace_profile(db, org_id, None) is None
    assert await svc.get_workspace_profile(db, org_id) is None


async def test_setting_an_unknown_profile_is_refused_not_stored(db, session_factory):
    org_id = await create_org(session_factory, "Bad input")
    svc = BillingService()
    with pytest.raises(ValueError):
        await svc.set_workspace_profile(db, org_id, "enterprise")
    assert await svc.get_workspace_profile(db, org_id) is None


async def test_a_stale_stored_value_reads_back_as_unset(db, session_factory):
    """Written around the API (a migration, psql) -- the reader must not trust it."""
    org_id = await create_org(session_factory, "Stale")
    org = (
        await db.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    org.workspace_profile = "retired_profile"
    await db.commit()

    assert await BillingService().get_workspace_profile(db, org_id) is None
