"""Analytics fetcher — retrieve engagement metrics from platform APIs.

DATA RELIABILITY CONTRACT (see ``services/platform_metrics.py``): this module
never invents a metric. Only values the platform API actually returned are
persisted; every other metric column is written as SQL ``NULL`` so a reader can
tell "the platform reported zero" apart from "we could not measure this".

When a fetch comes back ``{"status": "unavailable", ...}`` no ``AnalyticsSnapshot``
row is written at all — the reason is returned to the caller instead.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any, Final
from uuid import UUID

import structlog
from sqlalchemy import Select, func, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import AnalyticsSnapshot, ContentPiece, PlatformAccount
from agency.services.platform_metrics import fetch_post_metrics

logger = structlog.get_logger()

#: Metric columns on ``analytics_snapshot`` that hold a measurement.
METRIC_FIELDS: Final[tuple[str, ...]] = (
    "impressions",
    "reach",
    "engagement",
    "clicks",
    "shares",
    "likes",
)

#: Keys under ``ContentPiece.metadata_`` that may hold the platform's post id.
#: ``post_id`` is what ``services/publishing.py`` returns and what both
#: ``services/scheduler.py`` and ``routers/publishing.py`` store on publish.
POST_ID_KEYS: Final[tuple[str, ...]] = ("post_id", "platform_post_id", "external_post_id")

#: How far back the daily refresh job looks for published content.
REFRESH_WINDOW_DAYS: Final[int] = 30

#: Upper bound on how many pieces one refresh pass touches.
REFRESH_BATCH_SIZE: Final[int] = 100


def _result(status: str, reason: str | None = None, **extra: Any) -> dict[str, Any]:
    """Build a non-success result. ``error`` mirrors ``reason`` for older callers."""
    out: dict[str, Any] = {"status": status, "reason": reason, **extra}
    if reason is not None:
        out["error"] = reason
    return out


def extract_post_id(piece: ContentPiece) -> str | None:
    """Pull the platform-side post id out of ``ContentPiece.metadata_``."""
    metadata: dict[str, Any] = dict(piece.metadata_ or {})
    for key in POST_ID_KEYS:
        value = metadata.get(key)
        if value:
            return str(value)
    return None


def _snapshot_to_dict(snapshot: AnalyticsSnapshot) -> dict[str, Any]:
    """Serialize a snapshot, keeping unmeasured metrics as ``None`` (never 0)."""
    extra: dict[str, Any] = dict(snapshot.extra or {})
    values: dict[str, Any] = {field: getattr(snapshot, field) for field in METRIC_FIELDS}
    return {
        "date": snapshot.date.isoformat(),
        **values,
        "measured": [f for f in METRIC_FIELDS if values[f] is not None],
        "not_available": [f for f in METRIC_FIELDS if values[f] is None],
        "source": extra.get("source"),
        "fetched_at": extra.get("fetched_at"),
    }


async def _snapshot_for_day(
    db: AsyncSession, content_id: UUID, day: date
) -> AnalyticsSnapshot | None:
    result = await db.execute(
        select(AnalyticsSnapshot).where(
            AnalyticsSnapshot.content_id == content_id,
            AnalyticsSnapshot.date == day,
        )
    )
    return result.scalars().first()


def refresh_candidates_query(
    *,
    now: datetime | None = None,
    window_days: int = REFRESH_WINDOW_DAYS,
    limit: int = REFRESH_BATCH_SIZE,
) -> Select[tuple[UUID]]:
    """Published pieces from the last ``window_days`` with no snapshot for today.

    The ``NOT EXISTS`` clause is the per-day guard: a piece already measured
    today is not re-fetched, so one platform call per post per day is the cap.
    """
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=window_days)
    already_today = (
        select(AnalyticsSnapshot.id)
        .where(
            AnalyticsSnapshot.content_id == ContentPiece.id,
            AnalyticsSnapshot.date == now.date(),
        )
        .exists()
    )
    return (
        select(ContentPiece.id)
        .where(
            ContentPiece.status == "published",
            ContentPiece.published_at.is_not(None),
            ContentPiece.published_at >= cutoff,
            ~already_today,
        )
        .order_by(ContentPiece.published_at.desc())
        .limit(limit)
    )


async def select_content_for_metrics_refresh(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    window_days: int = REFRESH_WINDOW_DAYS,
    limit: int = REFRESH_BATCH_SIZE,
) -> list[UUID]:
    """Ids of published content due for a metrics refresh."""
    result = await db.execute(
        refresh_candidates_query(now=now, window_days=window_days, limit=limit)
    )
    return list(result.scalars().all())


async def fetch_content_metrics(
    db: AsyncSession,
    content_id: UUID,
    *,
    skip_if_fetched_today: bool = False,
) -> dict[str, Any]:
    """Fetch live engagement metrics for a published content piece.

    Returns one of:

    * ``{"status": "ok", "metrics": {...}, "measured": [...], "not_available": [...]}``
      — a snapshot row was written/updated for today.
    * ``{"status": "unavailable", "reason": "..."}`` — nothing was persisted.
    * ``{"status": "skipped", "reason": "..."}`` — already measured today.
    * ``{"status": "error", "reason": "..."}`` — the piece is missing or unpublished.

    Callers must never treat a non-``ok`` result as a measurement of zero.
    """
    result = await db.execute(select(ContentPiece).where(ContentPiece.id == content_id))
    piece = result.scalar_one_or_none()
    if not piece:
        return _result("error", "Content not found", content_id=str(content_id))
    if piece.status != "published":
        return _result(
            "error",
            "Content not published",
            content_id=str(content_id),
            platform=piece.platform,
        )

    now = datetime.now(UTC)
    today = now.date()

    existing = await _snapshot_for_day(db, content_id, today)
    if existing is not None and skip_if_fetched_today:
        return _result(
            "skipped",
            "Metrics already refreshed today",
            content_id=str(content_id),
            platform=piece.platform,
            latest=_snapshot_to_dict(existing),
        )

    account_result = await db.execute(
        select(PlatformAccount).where(
            PlatformAccount.client_id == piece.client_id,
            PlatformAccount.platform == piece.platform,
            PlatformAccount.status == "connected",
        )
    )
    account = account_result.scalar_one_or_none()
    if not account:
        return _result(
            "unavailable",
            f"No connected {piece.platform} account for this content's client",
            content_id=str(content_id),
            platform=piece.platform,
        )
    if not account.access_token_enc:
        return _result(
            "unavailable",
            f"Connected {piece.platform} account has no stored access token — reconnect it",
            content_id=str(content_id),
            platform=piece.platform,
        )

    post_id = extract_post_id(piece)
    if not post_id:
        return _result(
            "unavailable",
            "No platform post id recorded for this content — it was never published "
            "through CampaignForge",
            content_id=str(content_id),
            platform=piece.platform,
        )

    fetched = await fetch_post_metrics(
        str(piece.platform),
        post_id,
        str(account.access_token_enc),
        page_id=str(account.account_handle) if account.account_handle else None,
        token_is_encrypted=True,
    )

    if fetched.get("status") != "ok":
        reason = str(fetched.get("reason") or "Platform metrics unavailable")
        logger.info(
            "content_metrics_unavailable",
            content_id=str(content_id),
            platform=piece.platform,
            reason=reason,
        )
        # DATA RELIABILITY: no snapshot row on an unavailable result.
        return _result(
            "unavailable",
            reason,
            content_id=str(content_id),
            platform=piece.platform,
            http_status=fetched.get("http_status"),
        )

    values: dict[str, int | None] = {
        field: int(fetched[field]) for field in METRIC_FIELDS if field in fetched
    }
    measured = [field for field in METRIC_FIELDS if field in values]
    not_available = [field for field in METRIC_FIELDS if field not in values]
    for field in not_available:
        values[field] = None

    extra: dict[str, Any] = dict(fetched.get("extra") or {})
    extra.update(
        {
            "post_id": post_id,
            "platform": piece.platform,
            "fetched_at": now.isoformat(),
            "measured_fields": measured,
            "fields_not_provided": not_available,
        }
    )

    snapshot = existing or AnalyticsSnapshot(
        platform_account_id=account.id,
        content_id=content_id,
        date=today,
    )
    snapshot.platform_account_id = account.id
    # The metric columns carry a DB-level ``DEFAULT 0`` and SQLAlchemy treats a
    # plain ``None`` as "unset", which would fire that default. ``null()`` forces
    # a real SQL NULL, so an unmeasured metric can never read back as a real 0.
    for field in METRIC_FIELDS:
        value = values[field]
        setattr(snapshot, field, null() if value is None else value)
    snapshot.followers_delta = null()  # type: ignore[assignment]  # not a per-post measurement
    snapshot.extra = extra  # type: ignore[assignment]
    if existing is None:
        db.add(snapshot)
    await db.flush()

    logger.info(
        "content_metrics_recorded",
        content_id=str(content_id),
        platform=piece.platform,
        measured=measured,
        not_available=not_available,
    )

    return {
        "status": "ok",
        "reason": None,
        "content_id": str(content_id),
        "platform": piece.platform,
        "date": today.isoformat(),
        "metrics": values,
        "measured": measured,
        "not_available": not_available,
        "source": extra.get("source"),
        "fetched_at": extra["fetched_at"],
    }


async def refresh_published_metrics(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    window_days: int = REFRESH_WINDOW_DAYS,
    limit: int = REFRESH_BATCH_SIZE,
) -> dict[str, Any]:
    """Refresh metrics for recently published content. Idempotent per day."""
    content_ids = await select_content_for_metrics_refresh(
        db, now=now, window_days=window_days, limit=limit
    )
    recorded = 0
    unavailable: list[dict[str, Any]] = []
    for content_id in content_ids:
        outcome = await fetch_content_metrics(db, content_id, skip_if_fetched_today=True)
        if outcome.get("status") == "ok":
            recorded += 1
        elif outcome.get("status") != "skipped":
            unavailable.append({"content_id": str(content_id), "reason": outcome.get("reason")})
    return {
        "selected": len(content_ids),
        "recorded": recorded,
        "unavailable": unavailable,
    }


async def get_content_analytics(db: AsyncSession, content_id: UUID) -> list[dict[str, Any]]:
    """Historical analytics snapshots for a content piece, newest first.

    Metric values are ``None`` when the platform did not expose them; each item
    also carries ``measured`` / ``not_available`` field lists.
    """
    result = await db.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.content_id == content_id)
        .order_by(AnalyticsSnapshot.date.desc())
    )
    return [_snapshot_to_dict(s) for s in result.scalars().all()]


async def get_client_analytics_summary(
    db: AsyncSession, client_id: UUID, org_id: UUID
) -> dict[str, Any]:
    """Aggregated analytics for all content by a client.

    ``SUM`` skips NULLs, so unmeasured metrics do not drag totals toward zero.
    ``*_measured_snapshots`` says how many snapshots actually carried each
    metric, so a total is never read as covering more posts than it does.
    """
    result = await db.execute(
        select(
            func.sum(AnalyticsSnapshot.impressions),
            func.sum(AnalyticsSnapshot.engagement),
            func.sum(AnalyticsSnapshot.clicks),
            func.sum(AnalyticsSnapshot.likes),
            func.sum(AnalyticsSnapshot.shares),
            func.count(AnalyticsSnapshot.id),
            func.count(AnalyticsSnapshot.impressions),
            func.count(AnalyticsSnapshot.engagement),
        )
        .join(ContentPiece, ContentPiece.id == AnalyticsSnapshot.content_id)
        .where(ContentPiece.client_id == client_id, ContentPiece.org_id == org_id)
    )
    row = result.one()
    return {
        "total_impressions": row[0],
        "total_engagement": row[1],
        "total_clicks": row[2],
        "total_likes": row[3],
        "total_shares": row[4],
        "snapshot_count": row[5] or 0,
        "impressions_measured_snapshots": row[6] or 0,
        "engagement_measured_snapshots": row[7] or 0,
    }
