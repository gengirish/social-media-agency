"""Product analytics — browser event ingest and the beta metrics dashboard.

Metrics are always scoped to the caller's organization. The programme-wide
rollup (`org_id=None` in the service layer) is deliberately not reachable from
the API so no tenant can read another tenant's usage.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi import Query as QueryParam

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.schemas import ProductEventAck, ProductEventBatch
from agency.services import product_analytics as pa

router = APIRouter(tags=["Product Analytics"])


def _user_uuid(user: dict) -> UUID | None:
    try:
        return UUID(str(user.get("sub")))
    except (TypeError, ValueError):
        return None


@router.post("/events", response_model=ProductEventAck)
async def ingest_events(
    batch: ProductEventBatch,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Accept a batch of browser events.

    Only names in ``CLIENT_WRITABLE_EVENTS`` are stored — pipeline and error
    events are server-authored, so a client cannot inflate completion or
    failure counts. Unknown names are counted as rejected, not an error, so a
    stale frontend build never breaks tracking for the rest of the batch.
    """
    user_id = _user_uuid(user)
    now = datetime.now(timezone.utc)
    accepted = 0
    rejected = 0

    for event in batch.events:
        if event.name not in pa.CLIENT_WRITABLE_EVENTS:
            rejected += 1
            continue

        properties = dict(event.properties)
        if event.feature:
            properties["feature"] = event.feature

        # Never trust a client clock for future timestamps.
        occurred_at = event.occurred_at or now
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        occurred_at = min(occurred_at, now)

        await pa.track(
            db,
            name=event.name,
            org_id=org_id,
            user_id=user_id,
            session_id=event.session_id,
            path=event.path,
            duration_ms=event.duration_ms,
            properties=properties,
            occurred_at=occurred_at,
        )
        accepted += 1

    await db.commit()
    return ProductEventAck(accepted=accepted, rejected=rejected)


@router.get("/beta-metrics")
async def get_beta_metrics(
    window_days: int = QueryParam(28, ge=1, le=180),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """The metrics table from ``docs/beta-testing-plan.md`` §7, for this org."""
    return await pa.beta_metrics(db, org_id, window_days=window_days)
