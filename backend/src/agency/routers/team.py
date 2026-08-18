"""Team API — members, invites, role updates."""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.services.email_service import send_email
from agency.services.team import invite_team_member, list_team_members, update_member_role

logger = structlog.get_logger()

router = APIRouter(prefix="/team", tags=["Team"])


class InviteRequest(BaseModel):
    email: str
    role: str


class RoleUpdateRequest(BaseModel):
    role: str


@router.get("")
async def get_team(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    return {"members": await list_team_members(db, org_id)}


@router.post("/invite")
async def invite_member(
    body: InviteRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Create a team member user with a temporary password.

    The invitation email is best-effort: it sends from the shared AgentMail
    sender (or the org's own inbox when it has one) and the response reports
    honestly via `email_sent` whether anything actually went out.
    """
    # TODO: Replace the temp-password flow with signed invite links and
    # org-branded templates. Mailing a password is a stopgap.
    invited_by = user.get("email") or str(user.get("sub", ""))
    result = await invite_team_member(
        db, org_id, body.email, body.role, invited_by
    )
    if result.get("error"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result["error"])

    temp_password = result.get("temp_password", "")
    send = await send_email(
        to=body.email,
        subject="You've been invited to CampaignForge",
        text=(
            f"You have been invited by {invited_by}. "
            f"Your temporary password is: {temp_password}. "
            "Please sign in and change your password."
        ),
        html=(
            f"<p>You have been invited by {invited_by}.</p>"
            f"<p>Your temporary password is: <strong>{temp_password}</strong>.</p>"
            "<p>Please sign in and change your password.</p>"
        ),
        db=db,
        org_id=org_id,
        labels=["team-invite"],
    )
    if not send.sent:
        logger.warning("team_invite_email_not_sent", email=body.email, reason=send.reason)

    message = (
        "User account created. Invitation email sent."
        if send.sent
        else (
            f"User account created, but NO invitation email was sent. {send.reason} "
            "Share the temporary password out of band."
        )
    )
    return {
        "status": "user_created",
        # Explicit so the UI never claims an email went out that did not.
        "email_sent": send.sent,
        "message": message,
        "email": body.email,
        "role": result["role"],
        "temp_password": result["temp_password"],
        "user_id": result["user_id"],
    }


@router.patch("/{user_id}/role")
async def patch_member_role(
    user_id: UUID,
    body: RoleUpdateRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    result = await update_member_role(db, org_id, user_id, body.role)
    if result.get("error"):
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in result["error"].lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(code, result["error"])
    return result
