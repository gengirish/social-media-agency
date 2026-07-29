"""Product analytics — event capture and the beta metrics defined in
``docs/beta-testing-plan.md`` §7.

Two write paths:

- :func:`track` joins the caller's session; the caller owns the commit.
- :func:`track_detached` opens its own session and never raises, for background
  pipeline tasks and middleware where a tracking failure must not surface.

All reads are scoped by ``org_id`` unless ``org_id=None`` is passed explicitly
(programme-wide rollup for the beta coordinator).
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import Float, and_, case, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.database import get_session_factory
from agency.models.tables import ProductEvent, User

logger = structlog.get_logger()

# --- Event names -------------------------------------------------------------

CAMPAIGN_CREATED = "campaign_created"
CAMPAIGN_COMPLETED = "campaign_completed"
CAMPAIGN_FAILED = "campaign_failed"
AGENT_STEP_COMPLETED = "agent_step_completed"
HUMAN_REVIEW_SUBMITTED = "human_review_submitted"
SESSION_STARTED = "session_started"
SESSION_ENDED = "session_ended"
PAGE_VIEW = "page_view"
FEATURE_USED = "feature_used"
API_ERROR = "api_error"

# Categories keep the table queryable without an enum migration.
CATEGORY_BY_NAME = {
    CAMPAIGN_CREATED: "pipeline",
    CAMPAIGN_COMPLETED: "pipeline",
    CAMPAIGN_FAILED: "pipeline",
    AGENT_STEP_COMPLETED: "pipeline",
    HUMAN_REVIEW_SUBMITTED: "pipeline",
    SESSION_STARTED: "session",
    SESSION_ENDED: "session",
    PAGE_VIEW: "session",
    FEATURE_USED: "feature",
    API_ERROR: "error",
}

# Only these may be written by the browser. Pipeline/error events are
# server-authored so a client cannot inflate completion or failure counts.
CLIENT_WRITABLE_EVENTS = frozenset(
    {SESSION_STARTED, SESSION_ENDED, PAGE_VIEW, FEATURE_USED}
)

# Pipeline order, used to render the agent drop-off funnel.
AGENT_FUNNEL_ORDER = [
    "orchestrate",
    "strategise",
    "seo_research",
    "create_content",
    "write_ads",
    "human_review",
    "qa_check",
    "compile_output",
    "analytics",
]


def _as_uuid(value: Any) -> UUID | None:
    """Coerce ids that arrive as strings (JWT claims, request state)."""
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _build_event(
    *,
    name: str,
    org_id: UUID | str | None = None,
    user_id: UUID | str | None = None,
    session_id: str = "",
    path: str = "",
    campaign_id: UUID | str | None = None,
    duration_ms: int | None = None,
    properties: dict | None = None,
    occurred_at: datetime | None = None,
) -> ProductEvent:
    return ProductEvent(
        org_id=_as_uuid(org_id),
        user_id=_as_uuid(user_id),
        session_id=(session_id or "")[:64],
        name=name[:100],
        category=CATEGORY_BY_NAME.get(name, "feature"),
        path=(path or "")[:500],
        campaign_id=_as_uuid(campaign_id),
        duration_ms=duration_ms,
        properties=properties or {},
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )


async def track(db: AsyncSession, **kwargs: Any) -> None:
    """Record an event on the caller's session. The caller commits."""
    db.add(_build_event(**kwargs))
    await db.flush()


async def track_detached(**kwargs: Any) -> None:
    """Record an event on a dedicated session; never raises."""
    try:
        factory = get_session_factory()
        async with factory() as db:
            db.add(_build_event(**kwargs))
            await db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("product_event_write_failed", event=kwargs.get("name"), error=str(exc))


# --- Metrics -----------------------------------------------------------------


def _scope(stmt: Any, org_id: UUID | None, since: datetime):
    stmt = stmt.where(ProductEvent.occurred_at >= since)
    if org_id is not None:
        stmt = stmt.where(ProductEvent.org_id == org_id)
    return stmt


async def _count(db: AsyncSession, org_id: UUID | None, since: datetime, name: str) -> int:
    stmt = _scope(select(func.count(ProductEvent.id)), org_id, since).where(
        ProductEvent.name == name
    )
    return int((await db.execute(stmt)).scalar() or 0)


async def time_to_first_campaign(
    db: AsyncSession, org_id: UUID | None, since: datetime
) -> dict[str, Any]:
    """Signup → first campaign, in seconds. Beta target: < 5 minutes."""
    first_campaign = (
        _scope(
            select(
                ProductEvent.user_id.label("user_id"),
                func.min(ProductEvent.occurred_at).label("first_at"),
            ),
            org_id,
            since,
        )
        .where(ProductEvent.name == CAMPAIGN_CREATED, ProductEvent.user_id.isnot(None))
        .group_by(ProductEvent.user_id)
        .subquery()
    )

    seconds = func.extract("epoch", first_campaign.c.first_at - User.created_at)
    stmt = select(
        func.count(),
        func.percentile_cont(0.5).within_group(seconds),
        func.percentile_cont(0.9).within_group(seconds),
    ).select_from(first_campaign.join(User, User.id == first_campaign.c.user_id))

    count, median, p90 = (await db.execute(stmt)).one()
    return {
        "users_with_campaign": int(count or 0),
        "median_seconds": round(float(median), 1) if median is not None else None,
        "p90_seconds": round(float(p90), 1) if p90 is not None else None,
        "target_seconds": 300,
    }


async def campaign_outcomes(
    db: AsyncSession, org_id: UUID | None, since: datetime
) -> dict[str, Any]:
    """Completion and failure rates. Beta targets: > 80% and < 5%."""
    created = await _count(db, org_id, since, CAMPAIGN_CREATED)
    completed = await _count(db, org_id, since, CAMPAIGN_COMPLETED)
    failed = await _count(db, org_id, since, CAMPAIGN_FAILED)
    finished = completed + failed

    return {
        "created": created,
        "completed": completed,
        "failed": failed,
        "in_flight": max(created - finished, 0),
        "completion_rate": round(completed / created, 4) if created else None,
        "failure_rate": round(failed / finished, 4) if finished else None,
        "completion_target": 0.8,
        "failure_target": 0.05,
    }


async def agent_step_dropoff(
    db: AsyncSession, org_id: UUID | None, since: datetime
) -> list[dict[str, Any]]:
    """Distinct campaigns reaching each pipeline node — where confidence is lost."""
    stmt = (
        _scope(
            select(
                ProductEvent.properties["agent"].astext.label("agent"),
                func.count(distinct(ProductEvent.campaign_id)).label("campaigns"),
            ),
            org_id,
            since,
        )
        .where(ProductEvent.name == AGENT_STEP_COMPLETED)
        .group_by(ProductEvent.properties["agent"].astext)
    )
    reached = {row.agent: int(row.campaigns) for row in (await db.execute(stmt)).all()}

    started = await _count(db, org_id, since, CAMPAIGN_CREATED)
    funnel: list[dict[str, Any]] = []
    previous = started

    for agent in AGENT_FUNNEL_ORDER:
        count = reached.get(agent, 0)
        funnel.append(
            {
                "agent": agent,
                "campaigns_reached": count,
                "share_of_started": round(count / started, 4) if started else None,
                "dropped_from_previous": max(previous - count, 0),
            }
        )
        previous = count

    return funnel


async def feature_adoption(
    db: AsyncSession, org_id: UUID | None, since: datetime, limit: int = 25
) -> list[dict[str, Any]]:
    """Distinct users and total uses per feature — which features resonate."""
    stmt = (
        _scope(
            select(
                ProductEvent.properties["feature"].astext.label("feature"),
                func.count(distinct(ProductEvent.user_id)).label("users"),
                func.count(ProductEvent.id).label("uses"),
            ),
            org_id,
            since,
        )
        .where(ProductEvent.name == FEATURE_USED)
        .group_by(ProductEvent.properties["feature"].astext)
        .order_by(func.count(distinct(ProductEvent.user_id)).desc())
        .limit(limit)
    )
    return [
        {"feature": row.feature or "unknown", "users": int(row.users), "uses": int(row.uses)}
        for row in (await db.execute(stmt)).all()
    ]


async def session_duration(
    db: AsyncSession, org_id: UUID | None, since: datetime
) -> dict[str, Any]:
    """Engagement depth, from browser ``session_ended`` beacons."""
    stmt = _scope(
        select(
            func.count(ProductEvent.id),
            func.percentile_cont(0.5).within_group(cast(ProductEvent.duration_ms, Float)),
            func.avg(ProductEvent.duration_ms),
        ),
        org_id,
        since,
    ).where(ProductEvent.name == SESSION_ENDED, ProductEvent.duration_ms.isnot(None))

    count, median, mean = (await db.execute(stmt)).one()
    return {
        "sessions": int(count or 0),
        "median_seconds": round(float(median) / 1000, 1) if median is not None else None,
        "mean_seconds": round(float(mean) / 1000, 1) if mean is not None else None,
    }


async def return_rate(
    db: AsyncSession, org_id: UUID | None, days: tuple[int, ...] = (1, 7, 14)
) -> list[dict[str, Any]]:
    """D1/D7/D14 retention: of users old enough to qualify, share active on/after day N.

    Users who signed up too recently are excluded from the denominator rather
    than counted as churned.
    """
    now = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []

    for day in days:
        cohort = select(User.id, User.created_at).where(
            User.created_at <= now - timedelta(days=day)
        )
        if org_id is not None:
            cohort = cohort.where(User.org_id == org_id)
        cohort_sub = cohort.subquery()

        returned = (
            select(func.count(distinct(ProductEvent.user_id)))
            .select_from(cohort_sub)
            .join(
                ProductEvent,
                and_(
                    ProductEvent.user_id == cohort_sub.c.id,
                    ProductEvent.occurred_at
                    >= cohort_sub.c.created_at + timedelta(days=day),
                ),
            )
        )

        eligible = int(
            (await db.execute(select(func.count()).select_from(cohort_sub))).scalar() or 0
        )
        active = int((await db.execute(returned)).scalar() or 0)

        results.append(
            {
                "day": day,
                "eligible_users": eligible,
                "returned_users": active,
                "rate": round(active / eligible, 4) if eligible else None,
            }
        )

    return results


async def errors_by_endpoint(
    db: AsyncSession, org_id: UUID | None, since: datetime, limit: int = 25
) -> list[dict[str, Any]]:
    """Backend reliability — persisted 4xx/5xx counts per route template."""
    endpoint = ProductEvent.properties["endpoint"].astext
    status_code = ProductEvent.properties["status"].astext

    stmt = (
        _scope(
            select(
                endpoint.label("endpoint"),
                ProductEvent.properties["method"].astext.label("method"),
                func.count(ProductEvent.id).label("errors"),
                func.sum(
                    case((status_code.startswith("5"), 1), else_=0)
                ).label("server_errors"),
            ),
            org_id,
            since,
        )
        .where(ProductEvent.name == API_ERROR)
        .group_by(endpoint, ProductEvent.properties["method"].astext)
        .order_by(func.count(ProductEvent.id).desc())
        .limit(limit)
    )

    return [
        {
            "endpoint": row.endpoint or "unknown",
            "method": row.method or "",
            "errors": int(row.errors),
            "server_errors": int(row.server_errors or 0),
        }
        for row in (await db.execute(stmt)).all()
    ]


# --- In-process request counters ---------------------------------------------
# Error *rates* need a request denominator. Persisting a row per request is too
# expensive, so totals live in memory and reset on restart/redeploy. Reported
# separately from the DB-backed counts above, and labelled as such.

_request_totals: dict[tuple[str, str], int] = defaultdict(int)
_request_errors: dict[tuple[str, str], int] = defaultdict(int)


def record_request(method: str, endpoint: str, status_code: int) -> None:
    key = (method, endpoint)
    _request_totals[key] += 1
    if status_code >= 400:
        _request_errors[key] += 1


def request_rate_snapshot(limit: int = 25) -> dict[str, Any]:
    rows = [
        {
            "endpoint": endpoint,
            "method": method,
            "requests": total,
            "errors": _request_errors.get((method, endpoint), 0),
            "error_rate": round(_request_errors.get((method, endpoint), 0) / total, 4),
        }
        for (method, endpoint), total in _request_totals.items()
        if total
    ]
    rows.sort(key=lambda r: (-r["error_rate"], -r["requests"]))

    total_requests = sum(_request_totals.values())
    total_errors = sum(_request_errors.values())

    return {
        "note": "Counted in memory since process start; resets on restart or redeploy.",
        "total_requests": total_requests,
        "total_errors": total_errors,
        "error_rate": round(total_errors / total_requests, 4) if total_requests else None,
        "by_endpoint": rows[:limit],
    }


async def beta_metrics(
    db: AsyncSession, org_id: UUID | None, window_days: int = 28
) -> dict[str, Any]:
    """Assemble the full §7 table for the beta dashboard."""
    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    return {
        "window_days": window_days,
        "since": since.isoformat(),
        "scope": "organization" if org_id else "all_organizations",
        "time_to_first_campaign": await time_to_first_campaign(db, org_id, since),
        "campaign_outcomes": await campaign_outcomes(db, org_id, since),
        "agent_step_dropoff": await agent_step_dropoff(db, org_id, since),
        "feature_adoption": await feature_adoption(db, org_id, since),
        "session_duration": await session_duration(db, org_id, since),
        "return_rate": await return_rate(db, org_id),
        "errors_by_endpoint": await errors_by_endpoint(db, org_id, since),
        "request_rates": request_rate_snapshot(),
    }
