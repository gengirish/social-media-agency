"""Content scheduling engine — manages timed publishing queue."""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.database import get_session_factory
from agency.models.tables import ContentPiece, PlatformAccount
from agency.services.publishing import publisher

logger = structlog.get_logger()


def _merge_metadata(piece: ContentPiece, updates: dict) -> None:
    base = dict(piece.metadata_ or {})
    base.update(updates)
    piece.metadata_ = base


class SchedulerEngine:
    """Runs a background loop checking for content due for publishing."""

    _running = False

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
            await asyncio.sleep(60)  # Check every minute

    async def _process_due_content(self):
        factory = get_session_factory()
        async with factory() as db:
            now = datetime.now(timezone.utc)

            result = await db.execute(
                select(ContentPiece)
                .where(
                    ContentPiece.status == "scheduled",
                    ContentPiece.scheduled_at <= now,
                )
                .limit(10)
            )
            pieces = result.scalars().all()

            for piece in pieces:
                await self._publish_piece(db, piece)

    async def _publish_piece(self, db: AsyncSession, piece: ContentPiece):
        # Get platform credentials
        result = await db.execute(
            select(PlatformAccount).where(
                PlatformAccount.client_id == piece.client_id,
                PlatformAccount.platform == piece.platform,
                PlatformAccount.status == "connected",
            )
        )
        account = result.scalar_one_or_none()

        if not account:
            logger.warning(
                "no_platform_account", content_id=str(piece.id), platform=piece.platform
            )
            piece.status = "failed"
            _merge_metadata(piece, {"publish_error": "No connected platform account"})
            await db.commit()
            return

        content_data = {
            "body": piece.body,
            "hashtags": piece.hashtags or [],
            "title": piece.title,
        }
        credentials = {
            "access_token": account.access_token_enc,  # In production, decrypt this
            "page_id": account.account_handle,
        }

        pub_result = await publisher.publish(piece.platform, content_data, credentials)

        if pub_result.get("success"):
            piece.status = "published"
            piece.published_at = datetime.now(timezone.utc)
            _merge_metadata(
                piece,
                {
                    "post_id": pub_result.get("post_id"),
                    "post_url": pub_result.get("url"),
                },
            )
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
        await db.commit()
        return {"status": "scheduled", "scheduled_at": scheduled_at.isoformat()}

    async def get_calendar(
        self, db: AsyncSession, org_id: UUID, start: datetime, end: datetime
    ) -> list:
        """Get all scheduled/published content in a date range."""
        result = await db.execute(
            select(ContentPiece)
            .where(
                ContentPiece.org_id == org_id,
                ContentPiece.status.in_(["scheduled", "published"]),
                ContentPiece.scheduled_at >= start,
                ContentPiece.scheduled_at <= end,
            )
            .order_by(ContentPiece.scheduled_at)
        )
        return list(result.scalars().all())


scheduler = SchedulerEngine()
