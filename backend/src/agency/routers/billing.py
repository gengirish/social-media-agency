"""Billing API — plans, subscription, Stripe checkout and webhooks."""

from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from stripe import SignatureVerificationError
from pydantic import BaseModel

from agency.config import get_settings
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.services.billing import billing

router = APIRouter(prefix="/billing", tags=["Billing"])


class CheckoutRequest(BaseModel):
    plan_tier: str
    success_url: str
    cancel_url: str


@router.get("/plans")
async def list_plans(user=Depends(get_current_user)):
    return {"plans": billing.get_plans()}


@router.get("/subscription")
async def get_subscription(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    return await billing.get_subscription(db, org_id)


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await billing.create_checkout_session(
        db,
        org_id,
        body.plan_tier,
        body.success_url,
        body.cancel_url,
    )
    if result.get("error"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result["error"])
    return result


@router.post("/webhook")
async def stripe_webhook(request: Request, db=Depends(get_db)):
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Stripe webhook secret not configured",
        )

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing stripe-signature header")

    try:
        event_obj = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.stripe_webhook_secret,
        )
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payload")
    except SignatureVerificationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature")

    event_dict = event_obj.to_dict() if hasattr(event_obj, "to_dict") else dict(event_obj)
    result = await billing.handle_webhook(db, event_dict)
    return result
