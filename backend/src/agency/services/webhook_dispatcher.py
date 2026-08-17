"""Outbound webhooks — registration, signing, delivery, and the delivery log.

Design notes that matter:

- **The signature covers the exact bytes that are sent.** :func:`serialise_event`
  produces the body once; that same ``bytes`` object is both HMAC'd and handed to
  ``httpx`` as ``content=``. Re-serialising for the request (e.g. ``json=``)
  would let key ordering or separators drift and every signature would fail
  verification on the receiver.
- **Dispatch never raises into the caller.** A customer endpoint that is down,
  slow, or returning 500s must not abort a campaign pipeline. Everything is
  wrapped; failures are logged and recorded, then swallowed.
- **Delivery logging uses its own session**, mirroring
  :func:`agency.services.product_analytics.track_detached`, so a write failure
  cannot poison the caller's transaction.
"""

import asyncio
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.database import get_session_factory
from agency.models.tables import Webhook, WebhookDelivery

logger = structlog.get_logger()

# Events a tenant may subscribe to. Keep in sync with the fire points in
# routers/campaigns.py and routers/content.py.
EVENT_CAMPAIGN_COMPLETED = "campaign.completed"
EVENT_CONTENT_APPROVED = "content.approved"

SUPPORTED_EVENTS = frozenset({EVENT_CAMPAIGN_COMPLETED, EVENT_CONTENT_APPROVED})

MAX_ATTEMPTS = 3
RETRY_BACKOFF_BASE_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 10.0
SIGNATURE_HEADER = "X-Webhook-Signature"
SECRET_BYTES = 32


# --- Signing -----------------------------------------------------------------


def generate_secret() -> str:
    """A fresh per-webhook signing key (hex, 64 chars)."""
    return secrets.token_hex(SECRET_BYTES)


def serialise_event(event_type: str, payload: dict[str, Any], sent_at: str) -> bytes:
    """Serialise the event body **once**. These bytes are what gets signed and sent."""
    return json.dumps(
        {"event": event_type, "sent_at": sent_at, "data": payload},
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def sign_body(secret: str, body: bytes) -> str:
    """HMAC-SHA256 over the raw request body, prefixed with the algorithm."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Constant-time check — the same computation a receiver performs."""
    return hmac.compare_digest(sign_body(secret, body), signature)


# --- Registration (called by the thin router) --------------------------------


async def create_webhook(
    db: AsyncSession, org_id: UUID, url: str, events: list[str]
) -> Webhook:
    """Register an endpoint for ``org_id``. The caller's session is committed here.

    The returned instance carries the generated ``secret``; it is the only time
    the plaintext is available to a response.
    """
    hook = Webhook(
        org_id=org_id,
        url=url,
        events=list(events) or sorted(SUPPORTED_EVENTS),
        secret=generate_secret(),
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(hook)
    await db.commit()
    await db.refresh(hook)
    logger.info("webhook_registered", org_id=str(org_id), webhook_id=str(hook.id))
    return hook


async def list_webhooks(db: AsyncSession, org_id: UUID) -> list[Webhook]:
    """Every webhook belonging to ``org_id`` — and only to ``org_id``."""
    result = await db.execute(
        select(Webhook)
        .where(Webhook.org_id == org_id)
        .order_by(Webhook.created_at.desc())
    )
    return list(result.scalars().all())


async def get_webhook(db: AsyncSession, org_id: UUID, webhook_id: UUID) -> Webhook | None:
    """Fetch one webhook, scoped to the org. Another org's id resolves to ``None``."""
    result = await db.execute(
        select(Webhook).where(Webhook.id == webhook_id, Webhook.org_id == org_id)
    )
    return result.scalar_one_or_none()


async def delete_webhook(db: AsyncSession, org_id: UUID, webhook_id: UUID) -> bool:
    """Delete a webhook owned by ``org_id``. Returns ``False`` if it is not theirs."""
    hook = await get_webhook(db, org_id, webhook_id)
    if hook is None:
        return False
    await db.delete(hook)
    await db.commit()
    logger.info("webhook_deleted", org_id=str(org_id), webhook_id=str(webhook_id))
    return True


async def list_deliveries(
    db: AsyncSession, org_id: UUID, webhook_id: UUID, limit: int = 50
) -> list[WebhookDelivery]:
    """Delivery attempts for one webhook, scoped to the org on both tables."""
    result = await db.execute(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.webhook_id == webhook_id,
            WebhookDelivery.org_id == org_id,
        )
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# --- Dispatch ----------------------------------------------------------------


def _build_client() -> httpx.AsyncClient:
    """Isolated so tests can inject an ``httpx.MockTransport``."""
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False)


async def _load_targets(org_id: UUID, event_type: str) -> list[tuple[UUID, str, str]]:
    """Active endpoints for the org subscribed to ``event_type``.

    Returns plain tuples so nothing depends on a session that has been closed.
    Subscription is filtered in Python: ``events`` is a Postgres ``text[]`` and
    keeping the predicate dialect-neutral costs nothing at this cardinality.
    """
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(Webhook.id, Webhook.url, Webhook.secret, Webhook.events).where(
                Webhook.org_id == org_id,
                Webhook.is_active.is_(True),
            )
        )
        return [
            (row.id, row.url, row.secret)
            for row in result.all()
            if not row.events or event_type in row.events
        ]


async def _record_attempt(
    *,
    webhook_id: UUID,
    org_id: UUID,
    event_type: str,
    attempt: int,
    status: str,
    response_code: int | None,
    error: str,
) -> None:
    """Persist one attempt on a dedicated session; never raises."""
    try:
        factory = get_session_factory()
        async with factory() as db:
            db.add(
                WebhookDelivery(
                    webhook_id=webhook_id,
                    org_id=org_id,
                    event_type=event_type,
                    attempt=attempt,
                    status=status,
                    response_code=response_code,
                    error=error[:2000],
                    created_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "webhook_delivery_log_failed",
            webhook_id=str(webhook_id),
            event_type=event_type,
            error=str(exc),
        )


async def _deliver(
    client: httpx.AsyncClient,
    *,
    webhook_id: UUID,
    org_id: UUID,
    url: str,
    secret: str,
    event_type: str,
    body: bytes,
) -> dict[str, Any]:
    """POST ``body`` with retries. One ``webhook_delivery`` row per attempt."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "CampaignForge-Webhooks/1.0",
        "X-Webhook-Event": event_type,
        "X-Webhook-Id": str(webhook_id),
        # Signed over `body` exactly as sent — see module docstring.
        SIGNATURE_HEADER: sign_body(secret, body),
    }

    response_code: int | None = None
    error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        status = "failed"
        response_code = None
        error = ""
        try:
            response = await client.post(url, content=body, headers=headers)
            response_code = response.status_code
            if 200 <= response.status_code < 300:
                status = "delivered"
            else:
                error = f"HTTP {response.status_code}"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:2000]

        await _record_attempt(
            webhook_id=webhook_id,
            org_id=org_id,
            event_type=event_type,
            attempt=attempt,
            status=status,
            response_code=response_code,
            error=error,
        )

        if status == "delivered":
            return {
                "webhook_id": str(webhook_id),
                "event_type": event_type,
                "status": "delivered",
                "attempts": attempt,
                "response_code": response_code,
            }

        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))

    logger.warning(
        "webhook_delivery_failed",
        webhook_id=str(webhook_id),
        event_type=event_type,
        attempts=MAX_ATTEMPTS,
        error=error,
    )
    return {
        "webhook_id": str(webhook_id),
        "event_type": event_type,
        "status": "failed",
        "attempts": MAX_ATTEMPTS,
        "response_code": response_code,
        "error": error,
    }


async def dispatch_webhook(
    org_id: UUID | str,
    event_type: str,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Deliver ``event_type`` to every active endpoint registered by ``org_id``.

    Returns one result dict per endpoint. **Never raises** — a broken customer
    endpoint must not break the campaign pipeline, so every failure path returns
    a value instead of propagating.
    """
    try:
        org_uuid = org_id if isinstance(org_id, UUID) else UUID(str(org_id))
    except (TypeError, ValueError):
        logger.warning("webhook_dispatch_bad_org", org_id=str(org_id))
        return []

    try:
        targets = await _load_targets(org_uuid, event_type)
    except Exception as exc:
        logger.warning(
            "webhook_targets_load_failed",
            org_id=str(org_uuid),
            event_type=event_type,
            error=str(exc),
        )
        return []

    if not targets:
        return []

    body = serialise_event(event_type, payload, datetime.now(timezone.utc).isoformat())

    results: list[dict[str, Any]] = []
    try:
        client = _build_client()
        async with client:
            for webhook_id, url, secret in targets:
                results.append(
                    await _deliver(
                        client,
                        webhook_id=webhook_id,
                        org_id=org_uuid,
                        url=url,
                        secret=secret,
                        event_type=event_type,
                        body=body,
                    )
                )
    except Exception as exc:  # pragma: no cover - last-resort guard
        logger.warning(
            "webhook_dispatch_failed",
            org_id=str(org_uuid),
            event_type=event_type,
            error=str(exc),
        )

    logger.info(
        "webhook_dispatch",
        org_id=str(org_uuid),
        event_type=event_type,
        endpoints=len(targets),
        delivered=sum(1 for r in results if r.get("status") == "delivered"),
    )
    return results
