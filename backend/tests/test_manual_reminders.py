"""Scheduled = reminder, for a channel the operator posts to by hand.

Phase 4 of ``docs/manual-publish-plan-260929.md``. The whole point is a *negative*: a
due piece on a manual channel must never reach ``_publish_piece``. Nothing in the
product can post to a ``status = 'manual'`` ``platform_account`` — it has no tokens — so
the scheduled time is a reminder to a human and the piece stays ``scheduled`` until
``POST /publishing/{id}/mark-posted`` records that someone actually posted it.

Every test here installs ``no_real_publish``, which fails the test outright if the
platform publisher is reached. Asserting only on the final status would not be enough:
a publish that *failed* also leaves a row that is not ``published``, and the regression
worth catching is the attempt, not its outcome.

The second property is volume. A manual piece sits at ``status = 'scheduled'`` with a
past ``scheduled_at`` indefinitely, so the naive implementation re-notifies on every
scheduler wake, forever — and twelve due posts for one client would be twelve pings.
``metadata.reminder_sent_at`` and the per-client digest are what stop each of those.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from agency.models.tables import ContentPiece, Notification, Organization
from agency.services import slack_integration
from agency.services.scheduler import SchedulerEngine
from tests.conftest import (
    create_client_row,
    create_content_row,
    create_org,
    create_platform_account,
    create_subscription,
    create_user_row,
)


@pytest.fixture
def no_real_publish(monkeypatch):
    """Fail the test if anything reaches the platform publisher.

    This is the guard the whole phase is built around, so it is installed on every
    test in the file rather than only on the ones that look risky.
    """
    from agency.services.publishing import publisher

    async def _boom(*_a: Any, **_k: Any) -> dict:
        raise AssertionError("publisher reached for a manual channel")

    monkeypatch.setattr(publisher, "publish", _boom)


@pytest.fixture
def published(monkeypatch) -> list[dict[str, Any]]:
    """Record publisher calls and report success — for the no-regression test only."""
    from agency.services.publishing import publisher

    calls: list[dict[str, Any]] = []

    async def _record(platform: str, content: dict, credentials: dict) -> dict:
        calls.append({"platform": platform, "credentials": credentials})
        return {"success": True, "post_id": "p1", "url": "https://example.com/p1"}

    monkeypatch.setattr(publisher, "publish", _record)
    return calls


@pytest.fixture
def slack_sends(monkeypatch) -> list[tuple[str, str]]:
    """Capture Slack digests instead of calling Slack.

    Patched on the ``scheduler`` module's own reference, which is what it calls.
    """
    sent: list[tuple[str, str]] = []

    async def _send(channel: str, text: str) -> dict:
        sent.append((channel, text))
        return {"ok": True}

    monkeypatch.setattr("agency.services.scheduler.send_slack_message", _send)
    return sent


@pytest.fixture
async def org(session_factory):
    """An org with an owner, an admin, a member and a viewer.

    All four exist so the recipient choice is actually tested: a digest addressed to
    "everyone" would pass a fixture that only had an owner.
    """
    org_id = await create_org(session_factory, "Reminder Org", slug=f"rem-{uuid4().hex[:6]}")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org_id, "Reminder Brand")
    users = {
        role: await create_user_row(
            session_factory, org_id, role=role, email=f"{role}-{uuid4().hex[:8]}@test.com"
        )
        for role in ("owner", "admin", "member", "viewer")
    }
    return {"org_id": org_id, "client_id": client_id, "users": users}


async def _due_piece(
    session_factory,
    org: dict,
    *,
    platform: str = "instagram",
    status: str = "scheduled",
    minutes_ago: int = 5,
    metadata: dict | None = None,
) -> UUID:
    """A piece whose ``scheduled_at`` is already in the past."""
    content_id = await create_content_row(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform=platform,
        status=status,
        metadata=metadata,
    )
    async with session_factory() as db:
        piece = await db.get(ContentPiece, content_id)
        piece.scheduled_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
        await db.commit()
    return content_id


async def _manual_channel(session_factory, org: dict, platform: str = "instagram") -> UUID:
    return await create_platform_account(
        session_factory,
        org["org_id"],
        org["client_id"],
        platform=platform,
        status="manual",
        account_handle=f"{platform}-by-hand",
    )


async def _notifications(session_factory, org_id: UUID) -> list[Notification]:
    async with session_factory() as db:
        rows = (
            await db.execute(
                select(Notification)
                .where(Notification.org_id == org_id)
                .order_by(Notification.created_at)
            )
        ).scalars()
        return list(rows)


async def _piece(session_factory, content_id: UUID) -> ContentPiece:
    async with session_factory() as db:
        return await db.get(ContentPiece, content_id)


# ---------------------------------------------------------------------------
# THE test of this phase: a due manual piece never reaches the publisher.
# ---------------------------------------------------------------------------
async def test_due_manual_piece_is_reminded_not_published(
    session_factory, org, no_real_publish, slack_sends
):
    """It stays ``scheduled`` — not ``published``, and above all not ``failed``.

    ``failed`` is the specific regression: before this phase a due Instagram piece hit
    ``_publish_piece``, found ``UNAVAILABLE_PUBLISH_PLATFORMS``, and landed in Failed,
    whose only action is Delete. The post is fine; the product simply is not the one
    posting it.
    """
    await _manual_channel(session_factory, org)
    content_id = await _due_piece(session_factory, org)

    await SchedulerEngine()._process_due_content()

    piece = await _piece(session_factory, content_id)
    assert piece.status == "scheduled"
    assert piece.status != "failed"
    assert "publish_error" not in (piece.metadata_ or {})
    # The due time is preserved: it is the reminder time, and the Queue shows it.
    assert piece.scheduled_at is not None
    assert piece.metadata_["reminder_sent_at"]

    notifs = await _notifications(session_factory, org["org_id"])
    assert len(notifs) == 2  # owner + admin
    assert {n.type for n in notifs} == {"posts_due"}


async def test_reminder_is_sent_once_across_two_wakes(
    session_factory, org, no_real_publish, slack_sends
):
    """``metadata.reminder_sent_at`` is what stops an hourly ping forever.

    The piece stays ``scheduled`` with a past due time, so it matches the due query on
    every subsequent wake. Delete the ``reminder_sent_at`` filter and this test goes
    from 2 notifications to 4.
    """
    await _manual_channel(session_factory, org)
    await _due_piece(session_factory, org)

    engine = SchedulerEngine()
    await engine._process_due_content()
    first = await _notifications(session_factory, org["org_id"])
    await engine._process_due_content()
    second = await _notifications(session_factory, org["org_id"])

    assert len(first) == 2
    assert [n.id for n in second] == [n.id for n in first], "re-notified on the second wake"
    # No Slack channel on this org, so Slack was never attempted on either wake.
    assert slack_sends == []


async def test_ten_due_posts_for_one_client_produce_one_digest(
    session_factory, org, no_real_publish, slack_sends
):
    """Twelve due posts must not be twelve pings — the plan's words, and the reason
    the reminder is grouped by client instead of emitted per piece.

    Ten pieces, two recipients: two notifications total, not twenty. Each recipient's
    single digest names all ten. (The due query is capped at ten rows, which is why
    this uses exactly ten rather than twelve.)
    """
    async with session_factory() as db:
        row = await db.get(Organization, org["org_id"])
        row.settings = {"slack_channel": "#social"}
        await db.commit()
    await _manual_channel(session_factory, org)
    content_ids = [await _due_piece(session_factory, org) for _ in range(10)]

    await SchedulerEngine()._process_due_content()

    notifs = await _notifications(session_factory, org["org_id"])
    assert len(notifs) == 2, f"one digest per recipient, got {len(notifs)}"
    for notif in notifs:
        assert notif.data["count"] == 10
        assert set(notif.data["content_ids"]) == {str(c) for c in content_ids}
        assert "10 posts" in notif.title
    assert len(slack_sends) == 1, "one Slack digest per client per batch"

    for content_id in content_ids:
        assert (await _piece(session_factory, content_id)).status == "scheduled"


async def test_two_clients_get_a_digest_each(
    session_factory, org, no_real_publish, slack_sends
):
    """Grouping is per client, not per org: one brand's digest must not name another's."""
    second_client = await create_client_row(session_factory, org["org_id"], "Other Brand")
    await _manual_channel(session_factory, org)
    await create_platform_account(
        session_factory,
        org["org_id"],
        second_client,
        platform="instagram",
        status="manual",
        account_handle="other-by-hand",
    )
    await _due_piece(session_factory, org)
    other_id = await create_content_row(
        session_factory,
        org["org_id"],
        second_client,
        platform="instagram",
        status="scheduled",
    )
    async with session_factory() as db:
        piece = await db.get(ContentPiece, other_id)
        piece.scheduled_at = datetime.now(UTC) - timedelta(minutes=5)
        await db.commit()

    await SchedulerEngine()._process_due_content()

    notifs = await _notifications(session_factory, org["org_id"])
    # Two clients x two recipients.
    assert len(notifs) == 4
    client_ids = {n.data["client_id"] for n in notifs}
    assert client_ids == {str(org["client_id"]), str(second_client)}
    assert all(n.data["count"] == 1 for n in notifs)
    titles = {n.title for n in notifs}
    assert any("Reminder Brand" in t for t in titles)
    assert any("Other Brand" in t for t in titles)


# ---------------------------------------------------------------------------
# Recipients
# ---------------------------------------------------------------------------
async def test_only_owners_and_admins_are_notified(
    session_factory, org, no_real_publish, slack_sends
):
    """The recipient choice is a documented judgement, so it is pinned by a test.

    ``member`` and ``viewer`` are excluded. A ``member`` may hold ``publish.manual`` and
    be the one who posts, but picking them would need a per-post assignee the schema
    does not have — so this must not silently start addressing everyone.
    """
    await _manual_channel(session_factory, org)
    await _due_piece(session_factory, org)

    await SchedulerEngine()._process_due_content()

    notifs = await _notifications(session_factory, org["org_id"])
    assert {n.user_id for n in notifs} == {
        org["users"]["owner"],
        org["users"]["admin"],
    }


async def test_other_orgs_staff_are_not_notified(
    session_factory, org, no_real_publish, slack_sends
):
    """TENANCY: the recipient query is ``org_id``-filtered.

    There is no RLS. Drop the filter and another tenant's owner receives a digest
    naming this org's client by name.
    """
    stranger_org = await create_org(session_factory, "Stranger", slug=f"str-{uuid4().hex[:6]}")
    stranger = await create_user_row(
        session_factory, stranger_org, role="owner", email=f"str-{uuid4().hex[:8]}@test.com"
    )
    await _manual_channel(session_factory, org)
    await _due_piece(session_factory, org)

    await SchedulerEngine()._process_due_content()

    notifs = await _notifications(session_factory, org["org_id"])
    assert stranger not in {n.user_id for n in notifs}
    async with session_factory() as db:
        for_stranger = (
            await db.execute(
                select(Notification).where(Notification.user_id == stranger)
            )
        ).scalars().all()
    assert for_stranger == []


async def test_no_recipient_leaves_the_reminder_unsent_and_logs(
    session_factory, no_real_publish, slack_sends
):
    """Nothing delivered means ``reminder_sent_at`` is not written.

    Recording a reminder that reached nobody would silence the post permanently. The
    next wake retries instead — a workspace with no active owner or admin today may
    have one tomorrow.
    """
    from structlog.testing import capture_logs

    org_id = await create_org(session_factory, "Ghost Org", slug=f"ghost-{uuid4().hex[:6]}")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org_id, "Ghost Brand")
    # A viewer only: nobody eligible.
    await create_user_row(
        session_factory, org_id, role="viewer", email=f"v-{uuid4().hex[:8]}@test.com"
    )
    bare = {"org_id": org_id, "client_id": client_id}
    await _manual_channel(session_factory, bare)
    content_id = await _due_piece(session_factory, bare)

    with capture_logs() as logs:
        await SchedulerEngine()._process_due_content()

    piece = await _piece(session_factory, content_id)
    assert piece.status == "scheduled"
    assert "reminder_sent_at" not in (piece.metadata_ or {})
    assert any(e["event"] == "manual_reminder_no_recipient" for e in logs)


# ---------------------------------------------------------------------------
# Slack: connected-ness is the opt-in
# ---------------------------------------------------------------------------
async def test_slack_digest_goes_to_the_orgs_configured_channel(
    session_factory, org, no_real_publish, slack_sends
):
    async with session_factory() as db:
        row = await db.get(Organization, org["org_id"])
        row.settings = {"slack_channel": "#social"}
        await db.commit()

    await _manual_channel(session_factory, org)
    await _due_piece(session_factory, org)

    await SchedulerEngine()._process_due_content()

    assert len(slack_sends) == 1
    channel, text = slack_sends[0]
    assert channel == "#social"
    assert "Reminder Brand" in text


async def test_no_slack_channel_skips_silently(
    session_factory, org, no_real_publish, monkeypatch
):
    """No configured channel is not an error, and not a new setup step either.

    ``send_slack_message`` must not even be called: it reads a workspace-wide bot token
    from settings, and calling it with no channel would be a request that can only fail.
    """
    called: list[str] = []

    async def _send(channel: str, text: str) -> dict:
        called.append(channel)
        return {"ok": True}

    monkeypatch.setattr("agency.services.scheduler.send_slack_message", _send)

    await _manual_channel(session_factory, org)
    content_id = await _due_piece(session_factory, org)

    await SchedulerEngine()._process_due_content()

    assert called == []
    # The in-app digest still landed, so the reminder is recorded as sent.
    assert len(await _notifications(session_factory, org["org_id"])) == 2
    assert (await _piece(session_factory, content_id)).metadata_["reminder_sent_at"]


async def test_slack_failure_does_not_lose_the_in_app_reminder(
    session_factory, org, no_real_publish, monkeypatch
):
    """Slack is an extra delivery path, never the reason a reminder fails."""
    async def _boom(channel: str, text: str) -> dict:
        raise RuntimeError("slack is down")

    monkeypatch.setattr("agency.services.scheduler.send_slack_message", _boom)
    async with session_factory() as db:
        row = await db.get(Organization, org["org_id"])
        row.settings = {"slack_channel": "#social"}
        await db.commit()

    await _manual_channel(session_factory, org)
    content_id = await _due_piece(session_factory, org)

    await SchedulerEngine()._process_due_content()

    assert len(await _notifications(session_factory, org["org_id"])) == 2
    assert (await _piece(session_factory, content_id)).metadata_["reminder_sent_at"]


async def test_slack_helper_is_unconfigured_without_a_bot_token(monkeypatch):
    """Sanity check on the real helper: no token means an error dict, not an exception."""
    from agency.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SLACK_BOT_TOKEN", "")
    try:
        assert await slack_integration.send_slack_message("#x", "y") == {
            "error": "Slack not configured"
        }
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# What must NOT be reminded
# ---------------------------------------------------------------------------
async def test_a_published_piece_with_a_past_due_time_is_never_re_notified(
    session_factory, org, no_real_publish, slack_sends
):
    """``mark_posted`` deliberately leaves ``scheduled_at`` set, exactly as
    ``publish_now`` does — the calendar still shows when the post went out.

    That is harmless here only because the reminder path selects
    ``status == "scheduled"`` and nothing else. This test pins that property rather
    than changing the endpoint: widen the status filter and a live post starts nagging
    its owner every hour forever.
    """
    await _manual_channel(session_factory, org)
    content_id = await _due_piece(
        session_factory,
        org,
        status="published",
        metadata={"publish_mode": "manual", "post_url": None},
    )

    await SchedulerEngine()._process_due_content()

    assert await _notifications(session_factory, org["org_id"]) == []
    piece = await _piece(session_factory, content_id)
    assert piece.status == "published"
    assert piece.scheduled_at is not None, "mark_posted leaves it set; nothing here clears it"
    assert "reminder_sent_at" not in (piece.metadata_ or {})


async def test_a_manual_channel_in_another_org_does_not_divert_the_post(
    session_factory, org, published
):
    """TENANCY, in the dangerous direction.

    The manual/autopost split is correlated on ``org_id``. Drop it and another tenant's
    manual row carrying this client's id would route this org's post away from its own
    publisher — silently, and forever, because a reminded piece is then skipped on every
    later wake. This piece has a real connected channel and must still publish.
    """
    stranger_org = await create_org(session_factory, "Stranger", slug=f"s2-{uuid4().hex[:6]}")
    await create_platform_account(
        session_factory,
        stranger_org,
        org["client_id"],
        platform="linkedin",
        status="manual",
        account_handle="not-yours",
    )
    await create_platform_account(
        session_factory, org["org_id"], org["client_id"], platform="linkedin"
    )
    content_id = await _due_piece(session_factory, org, platform="linkedin")

    await SchedulerEngine()._process_due_content()

    assert len(published) == 1, "a foreign manual row diverted the post"
    assert (await _piece(session_factory, content_id)).status == "published"
    assert await _notifications(session_factory, org["org_id"]) == []


async def test_a_connected_piece_still_publishes_alongside_a_manual_one(
    session_factory, org, published, slack_sends
):
    """No regression: the two paths run in the same batch without interfering.

    They are two separate capped queries precisely so a backlog of manual pieces
    cannot starve the publishing one.
    """
    await create_platform_account(
        session_factory, org["org_id"], org["client_id"], platform="linkedin"
    )
    await _manual_channel(session_factory, org, platform="instagram")
    connected_id = await _due_piece(session_factory, org, platform="linkedin")
    manual_id = await _due_piece(session_factory, org, platform="instagram")

    await SchedulerEngine()._process_due_content()

    assert [c["platform"] for c in published] == ["linkedin"]
    assert (await _piece(session_factory, connected_id)).status == "published"
    assert (await _piece(session_factory, manual_id)).status == "scheduled"
    notifs = await _notifications(session_factory, org["org_id"])
    assert len(notifs) == 2
    assert all(n.data["content_ids"] == [str(manual_id)] for n in notifs)


async def test_manual_wins_when_both_channel_kinds_exist(
    session_factory, org, no_real_publish, slack_sends
):
    """A client with both a manual and a connected LinkedIn page: manual wins.

    The plan makes mode a property of the ``platform_account`` row and does not say
    which wins when two rows disagree. Routing *away* from the publisher is the
    conservative direction: the cost of getting it wrong this way is a human reminded
    about a post the product could have sent, versus a post going out twice — once by
    the product and once by the operator who meant to do it themselves.
    """
    await create_platform_account(
        session_factory, org["org_id"], org["client_id"], platform="linkedin"
    )
    await _manual_channel(session_factory, org, platform="linkedin")
    content_id = await _due_piece(session_factory, org, platform="linkedin")

    await SchedulerEngine()._process_due_content()

    piece = await _piece(session_factory, content_id)
    assert piece.status == "scheduled"
    assert piece.metadata_["reminder_sent_at"]


async def test_a_future_manual_piece_is_not_reminded_early(
    session_factory, org, no_real_publish, slack_sends
):
    """At the minute, not before it. The lead time is the due time itself (plan §5)."""
    await _manual_channel(session_factory, org)
    content_id = await _due_piece(session_factory, org, minutes_ago=-60)

    await SchedulerEngine()._process_due_content()

    assert await _notifications(session_factory, org["org_id"]) == []
    assert "reminder_sent_at" not in (await _piece(session_factory, content_id)).metadata_


async def test_a_reminder_costs_no_post_quota(
    session_factory, org, no_real_publish, slack_sends
):
    """Nothing was posted, so nothing is charged.

    The plan charges ``posts_limit`` on *confirm* only (``mark-posted``); an abandoned
    composer tab costs nothing, and a reminder is less than that.
    """
    from agency.models.tables import Subscription

    await _manual_channel(session_factory, org)
    await _due_piece(session_factory, org)

    async with session_factory() as db:
        before = (
            await db.execute(
                select(Subscription.posts_used).where(Subscription.org_id == org["org_id"])
            )
        ).scalar_one()

    await SchedulerEngine()._process_due_content()

    async with session_factory() as db:
        after = (
            await db.execute(
                select(Subscription.posts_used).where(Subscription.org_id == org["org_id"])
            )
        ).scalar_one()

    assert after == before
