"""Webhook dispatcher — send event notifications to registered webhook URLs."""

from uuid import UUID

import structlog

logger = structlog.get_logger()


async def dispatch_webhook(
    org_id: UUID,
    event_type: str,
    payload: dict,
) -> list[dict]:
    """Dispatch webhook event to all registered endpoints for an org.

    In production, webhook URLs are stored in a webhooks table.
    Currently logs the event for debugging.
    """
    logger.info(
        "webhook_dispatch",
        org_id=str(org_id),
        event_type=event_type,
        payload_keys=list(payload.keys()),
    )

    # When webhook URLs are registered, this will POST to each one:
    # async with httpx.AsyncClient() as client:
    #     for webhook in webhooks:
    #         signature = hmac.new(
    #             webhook.secret.encode(),
    #             json.dumps(payload).encode(),
    #             hashlib.sha256,
    #         ).hexdigest()
    #         await client.post(
    #             webhook.url,
    #             json={"event": event_type, "data": payload},
    #             headers={"X-Webhook-Signature": signature},
    #         )

    return [{"event_type": event_type, "status": "logged"}]
