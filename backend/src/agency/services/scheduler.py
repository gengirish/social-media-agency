"""Content scheduling engine — manages timed publishing queue."""

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Final
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.database import get_session_factory
from agency.models.tables import ContentPiece, PlatformAccount
from agency.services.analytics_fetcher import refresh_published_metrics
from agency.services.billing import billing
from agency.services.content_approval import ContentGateError, ensure_client_active
from agency.services.publishing import publisher

logger = structlog.get_logger()

#: Longest the loop may sleep when nothing is due.
#:
#: This is the main cost dial, and it is counted in *wakes*, not queries. Every
#: wake restarts the idle timer of everything it touches, so one wake costs a
#: full idle-timeout window of billed compute no matter how cheap the query is.
#: The loop used to sleep 60s unconditionally and ran a SELECT every tick —
#: 1,440 queries/day at zero traffic, which pinned Neon awake permanently and
#: made autosuspend unreachable however it was configured.
#:
#: At one hour that is ~24 wakes/day. Raise it to save more, lower it to publish
#: more punctually. It only bounds lateness for content scheduled on a *different*
#: machine — see :meth:`SchedulerEngine.notify_scheduled`.
MAX_SLEEP_SECONDS: Final = 3600

#: Floor, so a backlog of overdue content cannot spin the loop.
MIN_SLEEP_SECONDS: Final = 5


def _merge_metadata(piece: ContentPiece, updates: dict) -> None:
    base = dict(piece.metadata_ or {})
    base.update(updates)
    piece.metadata_ = base


def _clear_metadata(piece: ContentPiece, *keys: str) -> None:
    """Drop keys from a piece's metadata. Used to retire a stale blocked notice."""
    base = dict(piece.metadata_ or {})
    for key in keys:
        base.pop(key, None)
    piece.metadata_ = base


class SchedulerEngine:
    """Publishes content when it comes due, sleeping until then in between.

    The loop is deliberately *not* a fixed-interval poll. It computes the next
    moment it actually has work — the earliest future ``scheduled_at``, or the
    next daily analytics refresh — and sleeps until then, capped at
    :data:`MAX_SLEEP_SECONDS`. With an empty queue it issues no queries at all,
    which is what lets a scale-to-zero database suspend.
    """

    def __init__(self) -> None:
        self._running = False
        #: UTC day the analytics refresh pass last completed.
        self._last_metrics_refresh_day: date | None = None
        #: Broken early when content is scheduled on this machine, so a
        #: near-term post does not wait out a sleep computed before it existed.
        self._wake = asyncio.Event()

    def notify_scheduled(self) -> None:
        """Wake the loop now — content was scheduled on this machine.

        Only reaches the local process. A second machine scheduling content will
        not wake this one; that lateness is what :data:`MAX_SLEEP_SECONDS` bounds.
        """
        self._wake.set()

    async def start(self):
        """Start the scheduling loop (call at app startup)."""
        if self._running:
            return
        self._running = True
        logger.info("scheduler_started")
        asyncio.create_task(self._run_loop())

    async def stop(self):
        self._running = False
        logger.info("scheduler_stopped")

    async def _run_loop(self):
        while self._running:
            try:
                await self._process_due_content()
            except Exception as e:
                logger.error("scheduler_error", error=str(e))
            try:
                await self.refresh_analytics()
            except Exception as e:
                logger.error("metrics_refresh_error", error=str(e))

            try:
                delay = await self._compute_next_wake()
            except Exception as e:
                # Never let a failed lookup degrade into a hot loop.
                logger.error("scheduler_next_wake_failed", error=str(e))
                delay = float(MAX_SLEEP_SECONDS)

            logger.info("scheduler_sleeping", seconds=round(delay))
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=delay)
            except TimeoutError:
                pass
            finally:
                self._wake.clear()

    def _seconds_until_next_daily_refresh(self, now: datetime) -> float:
        """Seconds until the analytics refresh is next eligible to run."""
        if self._last_metrics_refresh_day != now.date():
            return 0.0
        midnight = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=UTC)
        return (midnight - now).total_seconds()

    async def _compute_next_wake(self, now: datetime | None = None) -> float:
        """Seconds to sleep before there is plausibly work to do.

        Opens its own short-lived session and closes it before the caller
        sleeps. Holding a connection open across the sleep would defeat the
        whole change — a scale-to-zero database cannot suspend while a client is
        connected, however idle that connection is.
        """
        now = now or datetime.now(UTC)

        factory = get_session_factory()
        async with factory() as db:
            next_due = (
                await db.execute(
                    select(func.min(ContentPiece.scheduled_at)).where(
                        ContentPiece.status == "scheduled",
                        ContentPiece.scheduled_at > now,
                    )
                )
            ).scalar()

        candidates = [float(MAX_SLEEP_SECONDS), self._seconds_until_next_daily_refresh(now)]
        if next_due is not None:
            if next_due.tzinfo is None:
                next_due = next_due.replace(tzinfo=UTC)
            candidates.append((next_due - now).total_seconds())

        return max(float(MIN_SLEEP_SECONDS), min(candidates))

    async def refresh_analytics(self, now: datetime | None = None) -> dict[str, Any]:
        """Refresh live platform metrics for recently published content.

        Runs at most once per UTC day off the existing scheduler loop. The
        per-content guard lives in ``analytics_fetcher`` so a mid-pass crash
        cannot cause a post to be measured twice on the same day.
        """
        now = now or datetime.now(UTC)
        today = now.date()
        if self._last_metrics_refresh_day == today:
            return {"status": "skipped", "reason": "Already refreshed today"}

        factory = get_session_factory()
        async with factory() as db:
            summary = await refresh_published_metrics(db, now=now)
            await db.commit()

        self._last_metrics_refresh_day = today
        logger.info("analytics_refresh_completed", **summary)
        return {"status": "completed", **summary}

    async def _process_due_content(self):
        factory = get_session_factory()
        async with factory() as db:
            now = datetime.now(UTC)

            # ``min_machines_running = 1`` keeps one machine warm, but
            # ``auto_start_machines`` can add more under load and each runs its
            # own engine. Without the lock, two machines select the same rows and
            # publish the same post twice.
            result = await db.execute(
                select(ContentPiece)
                .where(
                    ContentPiece.status == "scheduled",
                    ContentPiece.scheduled_at <= now,
                )
                .limit(10)
                .with_for_update(skip_locked=True)
            )
            pieces = result.scalars().all()

            for piece in pieces:
                await self._publish_piece(db, piece)

    async def _publish_piece(self, db: AsyncSession, piece: ContentPiece):
        try:
            await ensure_client_active(db, piece)
        except ContentGateError:
            # Only reachable if the post was scheduled in the same moment the client
            # was archived — archiving refuses while anything is scheduled.
            logger.warning("scheduled_post_client_archived", content_id=str(piece.id))
            piece.status = "failed"  # type: ignore[assignment]
            _merge_metadata(piece, {"publish_error": "Client is archived"})
            await db.commit()
            return

        # TENANCY: filter on the post's org, as publish_now does. Without it an account
        # row owned by another tenant but carrying this client's id would be selected and
        # the post published with that tenant's token. ``first()`` because an org may hold
        # more than one account per client+platform; newest connection wins, not an error.
        result = await db.execute(
            select(PlatformAccount)
            .where(
                PlatformAccount.org_id == piece.org_id,
                PlatformAccount.client_id == piece.client_id,
                PlatformAccount.platform == piece.platform,
                PlatformAccount.status == "connected",
            )
            .order_by(PlatformAccount.created_at.desc())
        )
        account = result.scalars().first()

        if not account:
            # CF-01: nothing is wrong with this post, so it does not belong in
            # Failed. Nothing is connected to publish it *to* — a workspace
            # configuration gap, which for most orgs means the platform's app
            # credentials are not set on the server at all and no Connect button
            # can even be pressed. Marking it failed read as "the copy was
            # rejected" and buried it in a tab whose only action was Delete.
            #
            # It goes back to Approved with the reason recorded, and its schedule
            # is cleared so the sweep does not pick it up again every minute and
            # rewrite the same row forever. Reschedule it once an account is
            # connected.
            logger.warning(
                "no_platform_account", content_id=str(piece.id), platform=piece.platform
            )
            piece.status = "approved"
            piece.scheduled_at = None
            _merge_metadata(
                piece,
                {
                    "publish_blocked": {
                        "reason": (
                            f"No {piece.platform} account is connected for this client, "
                            "so this post could not go out at its scheduled time. "
                            "Connect one under Setup › Accounts, then reschedule it."
                        ),
                        "code": "no_connected_account",
                        "platform": piece.platform,
                        "at": datetime.now(UTC).isoformat(),
                    }
                },
            )
            await db.commit()
            return

        if not await billing.check_quota(db, piece.org_id, resource="posts"):
            logger.warning("post_quota_exceeded_scheduler", content_id=str(piece.id))
            piece.status = "failed"
            _merge_metadata(
                piece,
                {"publish_error": "Monthly post limit reached for your plan."},
            )
            await db.commit()
            return

        content_data = {
            "body": piece.body,
            "hashtags": piece.hashtags or [],
            "title": piece.title,
        }
        credentials = {
            "access_token": account.access_token_enc,
            "page_id": account.account_handle,
        }

        pub_result = await publisher.publish(piece.platform, content_data, credentials)

        if pub_result.get("success"):
            piece.status = "published"
            piece.published_at = datetime.now(UTC)
            _merge_metadata(
                piece,
                {
                    "post_id": pub_result.get("post_id"),
                    "post_url": pub_result.get("url"),
                },
            )
            # A post that went out is neither blocked nor failing.
            _clear_metadata(piece, "publish_blocked", "publish_error")
            await billing.record_post_published(db, piece.org_id)
        else:
            piece.status = "failed"
            _merge_metadata(piece, {"publish_error": pub_result.get("error")})

        await db.commit()

    async def schedule_content(
        self, db: AsyncSession, content_id: UUID, scheduled_at: datetime
    ) -> dict:
        """Schedule a content piece for future publishing."""
        result = await db.execute(select(ContentPiece).where(ContentPiece.id == content_id))
        piece = result.scalar_one_or_none()
        if not piece:
            return {"error": "Content not found"}

        piece.status = "scheduled"
        piece.scheduled_at = scheduled_at
        # Rescheduling is the answer to "nothing was connected", so the notice
        # must not outlive it and label a queued post as blocked.
        _clear_metadata(piece, "publish_blocked")
        await db.commit()
        # Recompute the sleep now the queue changed.
        self.notify_scheduled()
        return {"status": "scheduled", "scheduled_at": scheduled_at.isoformat()}

    async def get_calendar(
        self,
        db: AsyncSession,
        org_id: UUID,
        start: datetime,
        end: datetime,
        *,
        client_id: UUID | None = None,
        include_pending: bool = False,
    ) -> list:
        """Content in a date range, by ``scheduled_at``.

        Default: scheduled/published only. ``include_pending`` adds drafts and
        approved posts that carry a *planned* day (Calendar's "Add post"), plus
        failed ones — none of those is published by the scheduler, which only
        ever picks ``status == "scheduled"``.
        """
        statuses = ["scheduled", "published"]
        if include_pending:
            statuses += ["draft", "approved", "failed"]
        q = select(ContentPiece).where(
            ContentPiece.org_id == org_id,
            ContentPiece.status.in_(statuses),
            ContentPiece.scheduled_at >= start,
            ContentPiece.scheduled_at <= end,
        )
        if client_id is not None:
            q = q.where(ContentPiece.client_id == client_id)
        result = await db.execute(q.order_by(ContentPiece.scheduled_at))
        return list(result.scalars().all())


scheduler = SchedulerEngine()
