"""Scheduler wake-interval tests — the idle-cost regression suite.

The loop used to sleep a flat 60s and run a SELECT on every tick: 1,440 queries
a day at zero traffic, which pinned a scale-to-zero database awake permanently.
The fix computes the next moment there is actually work and sleeps until then.

The load-bearing assertions here are about *wakes*, not correctness of
publishing: every wake restarts the database's idle timer, so wake count is the
thing that maps to the bill. ``test_idle_hour_issues_one_query_not_sixty``
asserts the query count directly — a test that only checked the returned delay
would not catch a regression that reintroduced a per-tick query.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, select

from agency.models.tables import ContentPiece
from agency.services.scheduler import (
    MAX_SLEEP_SECONDS,
    MIN_SLEEP_SECONDS,
    SchedulerEngine,
)

from .conftest import create_client_row, create_content_row, create_org


@pytest.fixture
async def seeded(session_factory):
    org_id = await create_org(session_factory)
    client_id = await create_client_row(session_factory, org_id)
    return org_id, client_id


async def _schedule(session_factory, org_id, client_id, when: datetime) -> UUID:
    content_id = await create_content_row(
        session_factory, org_id, client_id, status="scheduled"
    )
    async with session_factory() as db:
        piece = (
            await db.execute(select(ContentPiece).where(ContentPiece.id == content_id))
        ).scalar_one()
        piece.scheduled_at = when
        await db.commit()
    return content_id


async def test_empty_queue_sleeps_the_full_cap(session_factory):
    """The regression test for the whole bug.

    Nothing scheduled must mean nothing to wake for.
    """
    engine = SchedulerEngine()
    engine._last_metrics_refresh_day = datetime.now(UTC).date()

    delay = await engine._compute_next_wake()

    assert delay == float(MAX_SLEEP_SECONDS)


async def test_sleeps_until_the_next_due_item(session_factory, seeded):
    org_id, client_id = seeded
    now = datetime.now(UTC)
    await _schedule(session_factory, org_id, client_id, now + timedelta(seconds=90))

    engine = SchedulerEngine()
    engine._last_metrics_refresh_day = now.date()

    delay = await engine._compute_next_wake(now=now)

    assert 85 <= delay <= 95


async def test_distant_item_does_not_defeat_the_cap(session_factory, seeded):
    """Content five days out must not produce a five-day sleep.

    The cap bounds how late a post scheduled on another machine can be.
    """
    org_id, client_id = seeded
    now = datetime.now(UTC)
    await _schedule(session_factory, org_id, client_id, now + timedelta(days=5))

    engine = SchedulerEngine()
    engine._last_metrics_refresh_day = now.date()

    delay = await engine._compute_next_wake(now=now)

    assert delay == float(MAX_SLEEP_SECONDS)


async def test_overdue_item_floors_at_min_sleep(session_factory, seeded):
    """An overdue backlog must make progress, not spin the loop."""
    org_id, client_id = seeded
    now = datetime.now(UTC)
    # Strictly in the future but sooner than the floor.
    await _schedule(session_factory, org_id, client_id, now + timedelta(seconds=1))

    engine = SchedulerEngine()
    engine._last_metrics_refresh_day = now.date()

    delay = await engine._compute_next_wake(now=now)

    assert delay == float(MIN_SLEEP_SECONDS)


async def test_pending_daily_refresh_wins_over_the_cap(session_factory):
    """A refresh that has not run today is due immediately."""
    engine = SchedulerEngine()
    engine._last_metrics_refresh_day = None

    delay = await engine._compute_next_wake()

    assert delay == float(MIN_SLEEP_SECONDS)


async def test_refresh_done_today_waits_for_midnight(session_factory):
    engine = SchedulerEngine()
    now = datetime(2026, 9, 7, 23, 30, tzinfo=UTC)
    engine._last_metrics_refresh_day = now.date()

    delay = await engine._compute_next_wake(now=now)

    # 30 minutes to midnight beats the one-hour cap.
    assert 1795 <= delay <= 1805


async def test_notify_scheduled_breaks_the_sleep(session_factory):
    """A post scheduled on this machine must not wait out the cap."""
    engine = SchedulerEngine()
    assert not engine._wake.is_set()

    engine.notify_scheduled()

    assert engine._wake.is_set()


async def test_schedule_content_notifies(session_factory, seeded):
    org_id, client_id = seeded
    content_id = await create_content_row(session_factory, org_id, client_id)

    engine = SchedulerEngine()
    async with session_factory() as db:
        await engine.schedule_content(
            db, content_id, datetime.now(UTC) + timedelta(minutes=2)
        )

    assert engine._wake.is_set(), "scheduling must wake the loop"


async def test_idle_hour_issues_one_query_not_sixty(session_factory, db_engine):
    """Count real SQL, not elapsed time.

    Simulates an idle hour: the old loop would have computed 60 wakes and issued
    60 SELECTs. The new one computes a single one-hour sleep off a single query.
    """
    statements: list[str] = []

    sync_engine = db_engine.sync_engine

    def before_execute(conn, clauseelement, multiparams, params, execution_options):
        statements.append(str(clauseelement))

    event.listen(sync_engine, "before_execute", before_execute)
    try:
        engine = SchedulerEngine()
        engine._last_metrics_refresh_day = datetime.now(UTC).date()
        delay = await engine._compute_next_wake()
    finally:
        event.remove(sync_engine, "before_execute", before_execute)

    assert delay == float(MAX_SLEEP_SECONDS)
    assert len(statements) == 1, f"expected exactly one query, got {len(statements)}"
