"""Webhooks configuration router — register and manage outbound webhook endpoints.

Thin by design: everything except HTTP shape lives in
``services/webhook_dispatcher.py``. Every query is scoped to ``org_id``; the
database has no row-level security, so a missing filter is a tenant leak.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.schemas import (
    WebhookCreate,
    WebhookCreatedResponse,
    WebhookDeliveryListResponse,
    WebhookDeliveryResponse,
    WebhookListResponse,
    WebhookResponse,
)
from agency.services import webhook_dispatcher

router = APIRouter(prefix="/integrations/webhooks", tags=["Webhooks"])


@router.post("", response_model=WebhookCreatedResponse, status_code=status.HTTP_201_CREATED)
async def register_webhook(
    body: WebhookCreate,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> WebhookCreatedResponse:
    """Register a webhook endpoint.

    The response is the **only** time the signing secret is returned — store it,
    it is never echoed again.
    """
    hook = await webhook_dispatcher.create_webhook(db, org_id, body.url, body.events)
    return WebhookCreatedResponse.model_validate(hook)


@router.get("", response_model=WebhookListResponse)
async def list_webhooks(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> WebhookListResponse:
    """List this org's webhooks. Secrets are deliberately omitted."""
    hooks = await webhook_dispatcher.list_webhooks(db, org_id)
    items = [WebhookResponse.model_validate(h) for h in hooks]
    return WebhookListResponse(items=items, total=len(items))


@router.get("/{webhook_id}/deliveries", response_model=WebhookDeliveryListResponse)
async def list_webhook_deliveries(
    webhook_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> WebhookDeliveryListResponse:
    """Recent delivery attempts — the audit trail for a customer endpoint."""
    if await webhook_dispatcher.get_webhook(db, org_id, webhook_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found")

    rows = await webhook_dispatcher.list_deliveries(db, org_id, webhook_id)
    items = [WebhookDeliveryResponse.model_validate(r) for r in rows]
    return WebhookDeliveryListResponse(items=items, total=len(items))


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, str]:
    """Remove a webhook endpoint. Another org's id is a 404, never a delete."""
    if not await webhook_dispatcher.delete_webhook(db, org_id, webhook_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found")
    return {"status": "deleted", "id": str(webhook_id)}
