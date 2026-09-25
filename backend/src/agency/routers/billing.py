"""Billing API — plans, subscription, Stripe checkout and webhooks."""

from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from stripe import SignatureVerificationError

from agency.config import get_settings
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.permissions import Capability, require_cap
from agency.services.billing import (
    billing,
    plans_for_profile,
    workspace_profile_catalog,
)

router = APIRouter(prefix="/billing", tags=["Billing"])


class CheckoutRequest(BaseModel):
    plan_tier: str
    success_url: str | None = Field(
        default=None,
        description="Optional; defaults to {FRONTEND_URL}/settings?checkout=success",
    )
    cancel_url: str | None = Field(
        default=None,
        description="Optional; defaults to {FRONTEND_URL}/pricing?checkout=cancel",
    )


class WorkspaceProfileRequest(BaseModel):
    profile: str | None = Field(
        default=None,
        description=(
            "'product_owner' | 'freelancer' | 'organization', or null to clear the "
            "choice. Display only: it reshapes the pricing page and grants nothing."
        ),
    )


@router.get("/plans")
async def list_plans(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """The plans this workspace should be shown, shaped by its chosen profile.

    The full ``PLAN_CONFIG`` is still returned under ``all_plans``: the shaping is
    a storefront decision, and a client that wants every tier (an admin screen, a
    comparison view) should not have to guess at what was filtered out.
    """
    profile = await billing.get_workspace_profile(db, org_id)
    subscription = await billing.get_subscription(db, org_id)
    current_tier = str(subscription.get("plan_tier") or "free")
    return {
        "plans": plans_for_profile(profile, current_tier),
        "all_plans": billing.get_plans(),
        "profile": profile,
        "profiles": workspace_profile_catalog(),
    }


@router.get("/workspace-profile")
async def get_workspace_profile(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    return {
        "profile": await billing.get_workspace_profile(db, org_id),
        "profiles": workspace_profile_catalog(),
    }


@router.put(
    "/workspace-profile",
    dependencies=[Depends(require_cap(Capability.BILLING_MANAGE))],
)
async def set_workspace_profile(
    body: WorkspaceProfileRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Record how this workspace describes itself.

    Gated on ``billing.manage`` because it changes what every member of the org
    sees on the billing screen. It starts no subscription and moves no money --
    upgrading still goes through ``POST /billing/checkout``.
    """
    try:
        profile = await billing.set_workspace_profile(db, org_id, body.profile)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    subscription = await billing.get_subscription(db, org_id)
    return {
        "profile": profile,
        "plans": plans_for_profile(profile, str(subscription.get("plan_tier") or "free")),
    }


@router.get("/subscription")
async def get_subscription(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    return await billing.get_subscription(db, org_id)


@router.post("/checkout", dependencies=[Depends(require_cap(Capability.BILLING_MANAGE))])
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
    """Stripe's callback. **Deliberately ungated.**

    Stripe authenticates itself with the `stripe-signature` header, verified
    below; there is no bearer token, no user and no org on the request. A
    ``require_cap`` here would 403 every callback Stripe makes and silently
    strand every subscription change.
    """
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
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payload") from e
    except SignatureVerificationError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature") from e

    event_dict = event_obj.to_dict() if hasattr(event_obj, "to_dict") else dict(event_obj)
    result = await billing.handle_webhook(db, event_dict)
    return result
