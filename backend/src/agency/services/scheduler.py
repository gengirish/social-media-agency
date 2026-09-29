"""Content scheduling engine — manages timed publishing queue.

Two kinds of due content, split in SQL by whether the piece's channel is *manual*:

- a connected channel → :meth:`SchedulerEngine._publish_piece`, which posts it;
- a manual channel (``platform_account.status = 'manual'``, no tokens) → it stays
  ``scheduled`` and a human gets a digest reminder. Nothing here ever publishes to a
  manual channel; only ``POST /publishing/{id}/mark-posted`` marks one posted, and only
  after a human says they did it.
"""

import asyncio
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Final
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.database import get_session_factory
from agency.models.tables import (
    Client,
    ContentPiece,
    Organization,
    PlatformAccount,
    User,
)
from agency.services.analytics_fetcher import refresh_published_metrics
from agency.services.billing import billing
from agency.services.content_approval import ContentGateError, ensure_client_active
from agency.services.notifications import create_notification
from agency.services.publishing import publisher
from agency.services.slack_integration import send_slack_message

logger = structlog.get_logger()

#: Who gets a "your manual posts are due" digest.
#:
#: ``create_notification`` is per user and there is no notification-preference column,
#: so this is a judgement, not a setting: the roles that hold ``publish.write`` and are
#: therefore accountable for a post going out. A ``member`` may hold ``publish.manual``
#: and do the actual posting, but addressing them would need a per-post assignee the
#: schema does not have — so they are not guessed at here.
REMINDER_ROLES: Final = ("owner", "admin")

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

            # Whether a *manual* channel exists for the piece's client + platform, as a
            # correlated EXISTS so the split happens in SQL rather than after a shared
            # ``LIMIT``. Two separate queries matter: a manual piece stays ``scheduled``
            # with its due time in the past forever, so if both kinds shared one capped
            # query, a handful of already-reminded manual pieces would occupy every slot
            # and no connected post would ever be published again.
            #
            # TENANCY: correlated on ``org_id`` as well as ``client_id``. Without it,
            # another tenant's manual row carrying this client's id would divert this
            # org's post away from its publisher — silently, and forever.
            manual_channel = (
                select(PlatformAccount.id)
                .where(
                    PlatformAccount.org_id == ContentPiece.org_id,
                    PlatformAccount.client_id == ContentPiece.client_id,
                    PlatformAccount.platform == ContentPiece.platform,
                    PlatformAccount.status == "manual",
                )
                .exists()
            )

            # ``min_machines_running = 1`` keeps one machine warm, but
            # ``auto_start_machines`` can add more under load and each runs its
            # own engine. Without the lock, two machines select the same rows and
            # publish the same post twice.
            due = (
                select(ContentPiece)
                .where(
                    ContentPiece.status == "scheduled",
                    ContentPiece.scheduled_at <= now,
                )
                .limit(10)
                .with_for_update(skip_locked=True)
            )

            autopost = (await db.execute(due.where(~manual_channel))).scalars().all()
            for piece in autopost:
                await self._publish_piece(db, piece)

            # A manual piece must never reach ``_publish_piece``: nothing in the product
            # posts to a tokenless channel, and a due time on one is a reminder to a
            # human, not an instruction to the publisher. Already-reminded pieces are
            # excluded here, not after the fact, so a long-standing backlog cannot crowd
            # out a newly due one.
            reminders = (
                (
                    await db.execute(
                        due.where(
                            manual_channel,
                            # ``as_string()`` matters: the plain JSON index compiles to
                            # ``JSON_QUOTE(JSON_EXTRACT(...))`` on SQLite, and
                            # ``JSON_QUOTE(NULL)`` is the *string* ``'null'``, so
                            # ``IS NULL`` would never match and every manual piece
                            # would be reminded on every wake. ``->>`` / bare
                            # ``JSON_EXTRACT`` give SQL NULL for a missing key on both
                            # Postgres and SQLite.
                            ContentPiece.metadata_["reminder_sent_at"]
                            .as_string()
                            .is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if reminders:
                await self._remind_due_manual(db, list(reminders))

    async def _remind_due_manual(
        self, db: AsyncSession, pieces: list[ContentPiece]
    ) -> None:
        """Tell a human that manual posts have come due. Never publishes anything.

        The pieces stay ``scheduled`` — only ``POST /publishing/{id}/mark-posted`` moves
        a manual piece to ``published``, and only after a human says they posted it.

        **A digest, not a ping per post.** Twelve due posts for one client are one
        notification. Grouping is by ``(org, client)``: a marketer works one brand at a
        time and the Queue is client-scoped, so a cross-client digest would link
        somewhere that cannot show all of it.

        **Who receives it.** ``create_notification`` is per user, and there is no
        notification-preference column to read (and inventing one is not this phase's
        job), so the recipients are the org's active ``owner``/``admin`` users — the
        roles that hold ``publish.write``, i.e. the people accountable for a post going
        out. A ``member`` may hold ``publish.manual`` and do the posting, but choosing
        *them* would need a per-post assignee the schema does not have.

        ``metadata.reminder_sent_at`` is written **only when the digest actually reached
        someone**. Writing it after a no-op would silence the reminder for a post nobody
        was ever told about; leaving it unset means the next wake tries again, which is
        right — a workspace with no active owner or admin today may have one tomorrow.
        """
        by_client: dict[tuple[UUID, UUID], list[ContentPiece]] = defaultdict(list)
        for piece in pieces:
            by_client[(piece.org_id, piece.client_id)].append(piece)

        now = datetime.now(UTC).isoformat()
        for (org_id, client_id), group in by_client.items():
            delivered = await self._send_manual_digest(db, org_id, client_id, group)
            if not delivered:
                continue
            for piece in group:
                _merge_metadata(piece, {"reminder_sent_at": now})

        await db.commit()

    async def _send_manual_digest(
        self,
        db: AsyncSession,
        org_id: UUID,
        client_id: UUID,
        group: list[ContentPiece],
    ) -> bool:
        """One digest for one client's due manual posts. True if anyone was told."""
        client_name = (
            await db.execute(
                select(Client.brand_name).where(
                    Client.id == client_id, Client.org_id == org_id
                )
            )
        ).scalar_one_or_none() or "this client"

        count = len(group)
        title = (
            f"{count} post{'s' if count != 1 else ''} ready for you to post "
            f"for {client_name}"
        )
        platforms = sorted({(p.platform or "unknown").lower() for p in group})
        body = (
            f"The scheduled time has arrived for {count} "
            f"{'post' if count == 1 else 'posts'} on "
            f"{', '.join(platforms)}. CampaignForge does not publish to a channel you "
            "manage yourself — open the Queue, copy the post and post it, then mark it "
            "as posted."
        )
        data = {
            "client_id": str(client_id),
            "content_ids": [str(p.id) for p in group],
            "count": count,
            "platforms": platforms,
            # The Queue honours ``?client=`` and ``?status=`` on load, so the digest
            # lands on exactly the posts it is about. A reminder that drops you on an
            # unfiltered list is a reminder you have to re-find the work from.
            "url": f"/content?client={client_id}&status=scheduled",
        }

        # TENANCY: recipients are resolved from the piece's own org. There is no RLS, so
        # an unfiltered ``users`` query here would mail another tenant's staff a digest
        # naming this org's client.
        recipients = (
            (
                await db.execute(
                    select(User.id).where(
                        User.org_id == org_id,
                        User.role.in_(REMINDER_ROLES),
                        User.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )

        for user_id in recipients:
            await create_notification(
                db,
                user_id=user_id,
                org_id=org_id,
                type="posts_due",
                title=title,
                body=body,
                data=data,
            )

        if not recipients:
            # Nothing was delivered, so nothing is recorded as delivered. Say so rather
            # than letting a silent workspace look like a working one.
            logger.warning(
                "manual_reminder_no_recipient",
                org_id=str(org_id),
                client_id=str(client_id),
                count=count,
            )

        slack_ok = await self._slack_manual_digest(db, org_id, f"{title}\n{body}")
        return bool(recipients) or slack_ok

    async def _slack_manual_digest(self, db: AsyncSession, org_id: UUID, text: str) -> bool:
        """Post the digest to the org's Slack channel, if it already has one.

        Connected-ness *is* the opt-in — there is no new setup step and no new column.
        The channel lives in ``organization.settings["slack_channel"]``, which the
        existing ``PATCH /api/v1/integrations/settings`` already writes. No channel, or
        no workspace bot token on the server, means skip and log: this is an extra
        delivery path, never the reason a reminder fails.

        No email. A due-time reminder per post would be the highest-volume mail this
        product ever sent, and it has claimed absent email before.
        """
        settings = (
            await db.execute(
                select(Organization.settings).where(Organization.id == org_id)
            )
        ).scalar_one_or_none()
        # ``settings`` is free-form JSONB written by ``PATCH /integrations/settings``,
        # so it is not guaranteed to be an object at all.
        channel = settings.get("slack_channel") if isinstance(settings, dict) else None
        if not channel:
            logger.info("manual_reminder_slack_skipped", org_id=str(org_id), reason="no_channel")
            return False

        try:
            result = await send_slack_message(str(channel), text)
        except Exception as exc:  # noqa: BLE001 - Slack must never break the reminder
            logger.warning("manual_reminder_slack_failed", org_id=str(org_id), error=str(exc))
            return False

        if result.get("error"):
            logger.warning(
                "manual_reminder_slack_failed", org_id=str(org_id), error=result["error"]
            )
            return False
        return True

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
