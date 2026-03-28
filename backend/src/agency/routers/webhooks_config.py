"""Webhooks configuration router — register and manage webhook endpoints."""

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends

from agency.dependencies import get_current_user, get_org_id

router = APIRouter(prefix="/integrations/webhooks", tags=["Webhooks"])

_webhook_store: dict[str, list[dict]] = {}


@router.post("")
async def register_webhook(
    body: dict,
    user=Depends(get_current_user),
    org_id: UUID = Depends(get_org_id),
):
    """Register a webhook endpoint."""
    url = body.get("url", "")
    events = body.get("events", ["campaign.completed", "content.approved"])

    org_key = str(org_id)
    if org_key not in _webhook_store:
        _webhook_store[org_key] = []

    webhook_id = str(uuid.uuid4())
    _webhook_store[org_key].append(
        {
            "id": webhook_id,
            "url": url,
            "events": events,
            "active": True,
        }
    )
    return {"status": "registered", "id": webhook_id}


@router.get("")
async def list_webhooks(
    user=Depends(get_current_user),
    org_id: UUID = Depends(get_org_id),
):
    """List registered webhooks."""
    org_key = str(org_id)
    return {"items": _webhook_store.get(org_key, [])}


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    user=Depends(get_current_user),
    org_id: UUID = Depends(get_org_id),
):
    """Remove a webhook endpoint."""
    org_key = str(org_id)
    hooks = _webhook_store.get(org_key, [])
    _webhook_store[org_key] = [h for h in hooks if h["id"] != webhook_id]
    return {"status": "deleted"}
