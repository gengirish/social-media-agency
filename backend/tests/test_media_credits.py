"""Media credit quota — the weighted counter that keeps video spend bounded.

Separate from ``test_quota.py`` because the rules are different in kind, not
degree: the weight is configuration rather than 1, video is a plan entitlement
as well as a quota, and the charge has to be atomic (overshooting an Amplify
pack costs pennies; overshooting a video costs money).

Every test runs against the real SQLite harness from ``conftest.py`` so the
conditional UPDATE is exercised as SQL, which is the only place its atomicity
exists.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agency.config import get_settings, media_credit_weight
from agency.models.tables import Subscription
from agency.services.billing import PLAN_CONFIG
from agency.services.media_credits import charge_media_credits, require_media_credits
from tests.conftest import create_org


async def _media_sub(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    *,
    plan_tier: str = "growth",
    media_credits_used: int = 0,
    media_credits_limit: int | None = -1,
    videos_used: int = 0,
) -> UUID:
    """A subscription row with the media counters set.

    Local rather than in ``conftest.create_subscription`` because the shared
    factory is owned by another agent this stage — see the module report. The
    sentinel ``-1`` means "take the tier's value"; pass ``None`` explicitly to
    leave the column NULL and exercise the fallback.
    """
    plan = PLAN_CONFIG.get(plan_tier, PLAN_CONFIG["free"])
    sub = Subscription(
        id=uuid4(),
        org_id=org_id,
        plan_tier=plan_tier,
        clients_limit=plan["clients_limit"],
        posts_limit=plan["posts_limit"],
        posts_used=0,
        generations_used=0,
        generations_limit=plan["generations_limit"],
        media_credits_used=media_credits_used,
        media_credits_limit=(
            plan["media_credits_limit"] if media_credits_limit == -1 else media_credits_limit
        ),
        videos_used=videos_used,
        status="active",
    )
    async with session_factory() as session:
        session.add(sub)
        await session.commit()
    return sub.id


async def _counters(
    session_factory: async_sessionmaker[AsyncSession], org_id: UUID
) -> tuple[int, int]:
    async with session_factory() as session:
        sub = (
            await session.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        return int(sub.media_credits_used or 0), int(sub.videos_used or 0)


def _code(exc: HTTPException) -> str:
    detail: Any = exc.detail
    assert isinstance(detail, dict), detail
    return str(detail["code"])


# ---------------------------------------------------------------------------
# Weights come from config, never inlined at a call site
# ---------------------------------------------------------------------------
async def test_weights_are_read_from_config_not_hardcoded(session_factory, monkeypatch):
    """Re-price video in the environment and the charge must follow.

    This is the test that fails if someone inlines ``10``: the real weights are
    1 and 10, and these are deliberately neither.
    """
    monkeypatch.setattr(get_settings(), "media_credit_image", 3, raising=True)
    monkeypatch.setattr(get_settings(), "media_credit_video", 7, raising=True)
    assert media_credit_weight("image") == 3
    assert media_credit_weight("video") == 7

    org_id = await create_org(session_factory, "WeightCfg")
    await _media_sub(session_factory, org_id, plan_tier="growth")

    async with session_factory() as db:
        assert await charge_media_credits(db, org_id, "image") == 3
        assert await charge_media_credits(db, org_id, "video") == 7
        await db.commit()

    assert await _counters(session_factory, org_id) == (10, 1)


async def test_require_is_weight_aware_not_a_bare_less_than(session_factory):
    """A 10-credit video must not slip through on the last remaining credit."""
    org_id = await create_org(session_factory, "LastCredit")
    limit = PLAN_CONFIG["growth"]["media_credits_limit"]
    await _media_sub(
        session_factory, org_id, plan_tier="growth", media_credits_used=limit - 1
    )

    async with session_factory() as db:
        # One credit left: an image fits, a 10-credit video does not.
        await require_media_credits(db, org_id, "image")
        with pytest.raises(HTTPException) as exc:
            await require_media_credits(db, org_id, "video")
    assert exc.value.status_code == 402
    assert _code(exc.value) == "media_credit_quota_exceeded"


async def test_charge_refuses_the_video_that_would_overshoot(session_factory):
    """Same boundary in the charge path — a bare ``< limit`` would let it land."""
    org_id = await create_org(session_factory, "LastCreditCharge")
    limit = PLAN_CONFIG["growth"]["media_credits_limit"]
    await _media_sub(
        session_factory, org_id, plan_tier="growth", media_credits_used=limit - 1
    )

    async with session_factory() as db:
        with pytest.raises(HTTPException) as exc:
            await charge_media_credits(db, org_id, "video")
        await db.commit()

    assert _code(exc.value) == "media_credit_quota_exceeded"
    # Nothing charged, and videos_used untouched — the two move together or not at all.
    assert await _counters(session_factory, org_id) == (limit - 1, 0)


# ---------------------------------------------------------------------------
# Video is a plan entitlement, with its own code so the UI offers an upgrade
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tier", ["free", "starter"])
async def test_video_refused_without_a_plan_that_has_it(session_factory, tier):
    org_id = await create_org(session_factory, f"NoVideo-{tier}")
    await _media_sub(session_factory, org_id, plan_tier=tier)

    async with session_factory() as db:
        with pytest.raises(HTTPException) as exc:
            await require_media_credits(db, org_id, "video")
    assert exc.value.status_code == 402
    # Not the quota code: waiting for a reset would never help on these tiers.
    assert _code(exc.value) == "media_video_not_in_plan"


@pytest.mark.parametrize("tier", ["free", "starter"])
async def test_images_still_allowed_on_tiers_without_video(session_factory, tier):
    org_id = await create_org(session_factory, f"ImagesOk-{tier}")
    await _media_sub(session_factory, org_id, plan_tier=tier)

    async with session_factory() as db:
        sub = await require_media_credits(db, org_id, "image")
    assert sub.plan_tier == tier


# ---------------------------------------------------------------------------
# The clip sub-cap bites on every tier that has video — agency included
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tier", ["growth", "agency"])
async def test_video_sub_cap_enforced_with_credits_to_spare(session_factory, tier):
    """Agency's 9999 generations_limit is a sentinel; the clip cap still applies.

    The org is given plenty of *credits* on purpose, so the only thing that can
    refuse the request is the separate ``videos_limit``.
    """
    videos_limit = PLAN_CONFIG[tier]["videos_limit"]
    assert videos_limit > 0
    org_id = await create_org(session_factory, f"ClipCap-{tier}")
    await _media_sub(
        session_factory,
        org_id,
        plan_tier=tier,
        media_credits_used=0,
        videos_used=videos_limit,
    )

    async with session_factory() as db:
        with pytest.raises(HTTPException) as exc:
            await require_media_credits(db, org_id, "video")
        # Credits are untouched, so an image is still fine — proof the refusal
        # came from the clip cap and not the credit total.
        await require_media_credits(db, org_id, "image")

    assert exc.value.status_code == 402
    assert _code(exc.value) == "media_credit_quota_exceeded"


@pytest.mark.parametrize("tier", ["growth", "agency"])
async def test_last_clip_under_the_sub_cap_is_allowed(session_factory, tier):
    videos_limit = PLAN_CONFIG[tier]["videos_limit"]
    org_id = await create_org(session_factory, f"ClipCapOk-{tier}")
    await _media_sub(
        session_factory, org_id, plan_tier=tier, videos_used=videos_limit - 1
    )

    async with session_factory() as db:
        await require_media_credits(db, org_id, "video")
        assert await charge_media_credits(db, org_id, "video") == media_credit_weight("video")
        await db.commit()

    _, videos_used = await _counters(session_factory, org_id)
    assert videos_used == videos_limit


async def test_video_charge_increments_both_counters_in_one_statement(session_factory):
    org_id = await create_org(session_factory, "BothCounters")
    await _media_sub(session_factory, org_id, plan_tier="growth")

    async with session_factory() as db:
        await charge_media_credits(db, org_id, "video")
        await db.commit()

    assert await _counters(session_factory, org_id) == (media_credit_weight("video"), 1)


async def test_image_charge_leaves_videos_used_alone(session_factory):
    org_id = await create_org(session_factory, "ImageOnlyCounter")
    await _media_sub(session_factory, org_id, plan_tier="growth")

    async with session_factory() as db:
        await charge_media_credits(db, org_id, "image")
        await db.commit()

    assert await _counters(session_factory, org_id) == (media_credit_weight("image"), 0)


# ---------------------------------------------------------------------------
# Atomicity — the one behaviour that differs from charge_generation
# ---------------------------------------------------------------------------
async def test_two_callers_at_the_boundary_cannot_both_charge(session_factory):
    """The lost-race path, interleaved deterministically.

    Both callers pass ``require_media_credits`` while one credit remains — that
    much is unavoidable — and the conditional UPDATE is what has to stop the
    second from landing.
    """
    org_id = await create_org(session_factory, "Boundary1")
    limit = PLAN_CONFIG["growth"]["media_credits_limit"]
    await _media_sub(
        session_factory, org_id, plan_tier="growth", media_credits_used=limit - 1
    )

    async with session_factory() as a, session_factory() as b:
        await require_media_credits(a, org_id, "image")
        await require_media_credits(b, org_id, "image")

        assert await charge_media_credits(a, org_id, "image") == 1
        await a.commit()

        with pytest.raises(HTTPException) as exc:
            await charge_media_credits(b, org_id, "image")
        await b.commit()

    assert _code(exc.value) == "media_credit_quota_exceeded"
    used, _ = await _counters(session_factory, org_id)
    assert used == limit, "the second charge overshot the limit"


async def test_concurrent_charges_do_not_overshoot(session_factory):
    """Many callers racing for few credits: the total lands exactly on the limit."""
    org_id = await create_org(session_factory, "RaceMany")
    limit = 5
    await _media_sub(
        session_factory, org_id, plan_tier="growth", media_credits_limit=limit
    )

    async def _one() -> bool:
        async with session_factory() as db:
            try:
                await charge_media_credits(db, org_id, "image")
            except HTTPException:
                await db.rollback()
                return False
            await db.commit()
            return True

    results = await asyncio.gather(*(_one() for _ in range(limit * 3)))

    assert sum(results) == limit
    used, _ = await _counters(session_factory, org_id)
    assert used == limit


async def test_concurrent_video_charges_do_not_overshoot(session_factory):
    """Weighted version: 25 credits is two videos, never three."""
    org_id = await create_org(session_factory, "RaceVideo")
    weight = media_credit_weight("video")
    await _media_sub(
        session_factory, org_id, plan_tier="agency", media_credits_limit=weight * 2 + 5
    )

    async def _one() -> bool:
        async with session_factory() as db:
            try:
                await charge_media_credits(db, org_id, "video")
            except HTTPException:
                await db.rollback()
                return False
            await db.commit()
            return True

    results = await asyncio.gather(*(_one() for _ in range(6)))

    assert sum(results) == 2
    used, videos_used = await _counters(session_factory, org_id)
    assert used == weight * 2
    assert videos_used == 2


# ---------------------------------------------------------------------------
# NULL limit falls back to the tier default, never to zero
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tier", ["free", "starter", "growth", "agency"])
async def test_null_limit_falls_back_to_the_tier_default(session_factory, tier):
    """An org provisioned before 261013 has no column value and must still work.

    Reading NULL as zero would silently switch the feature off for every
    existing org — the failure this asserts against.
    """
    org_id = await create_org(session_factory, f"NullLimit-{tier}")
    await _media_sub(session_factory, org_id, plan_tier=tier, media_credits_limit=None)
    tier_limit = PLAN_CONFIG[tier]["media_credits_limit"]

    async with session_factory() as db:
        # Not zero: an image is allowed.
        await require_media_credits(db, org_id, "image")

    # And the fallback is the tier's value, not something larger: exhaust it.
    async with session_factory() as db:
        sub = (
            await db.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        sub.media_credits_used = tier_limit
        await db.commit()

    async with session_factory() as db:
        with pytest.raises(HTTPException) as exc:
            await require_media_credits(db, org_id, "image")
    assert _code(exc.value) == "media_credit_quota_exceeded"


async def test_null_limit_charge_uses_the_tier_default(session_factory):
    org_id = await create_org(session_factory, "NullLimitCharge")
    await _media_sub(
        session_factory,
        org_id,
        plan_tier="free",
        media_credits_limit=None,
        media_credits_used=PLAN_CONFIG["free"]["media_credits_limit"] - 1,
    )

    async with session_factory() as db:
        assert await charge_media_credits(db, org_id, "image") == 1
        await db.commit()

    async with session_factory() as db:
        with pytest.raises(HTTPException):
            await charge_media_credits(db, org_id, "image")


# ---------------------------------------------------------------------------
# Missing subscription, unknown kind
# ---------------------------------------------------------------------------
async def test_no_subscription_is_refused_not_granted(session_factory):
    org_id = await create_org(session_factory, "NoSub")

    async with session_factory() as db:
        with pytest.raises(HTTPException) as req_exc:
            await require_media_credits(db, org_id, "image")
        with pytest.raises(HTTPException) as charge_exc:
            await charge_media_credits(db, org_id, "image")

    assert _code(req_exc.value) == "media_credit_quota_exceeded"
    assert _code(charge_exc.value) == "media_credit_quota_exceeded"


async def test_unknown_kind_raises_rather_than_charging_an_image_price(session_factory):
    org_id = await create_org(session_factory, "BadKind")
    await _media_sub(session_factory, org_id, plan_tier="growth")

    async with session_factory() as db:
        with pytest.raises(ValueError):
            await require_media_credits(db, org_id, "audio")
        with pytest.raises(ValueError):
            await charge_media_credits(db, org_id, "audio")

    assert await _counters(session_factory, org_id) == (0, 0)


# ---------------------------------------------------------------------------
# Tenancy — the counter is per org, and there is no RLS behind it
# ---------------------------------------------------------------------------
async def test_charge_only_touches_the_callers_org(session_factory):
    mine = await create_org(session_factory, "MineOrg")
    theirs = await create_org(session_factory, "TheirsOrg")
    await _media_sub(session_factory, mine, plan_tier="growth")
    await _media_sub(session_factory, theirs, plan_tier="growth")

    async with session_factory() as db:
        await charge_media_credits(db, mine, "video")
        await db.commit()

    assert await _counters(session_factory, theirs) == (0, 0)
