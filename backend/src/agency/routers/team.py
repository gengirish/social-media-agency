"""Team API — members, invites, role updates."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from agency.config import get_settings
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import Organization
from agency.services.team import invite_team_member, list_team_members, update_member_role

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

    Invitation email is best-effort via AgentMail when configured (see inline logic).
    """
    # TODO: Replace temp-password flow with signed invite links and org-branded AgentMail templates.
    # TODO: No invitation email is sent unless agentmail_api_key is set and org.agentmail_inbox_id exists;
    # otherwise share credentials out of band until AgentMail is fully wired.
    invited_by = user.get("email") or str(user.get("sub", ""))
    result = await invite_team_member(
        db, org_id, body.email, body.role, invited_by
    )
    if result.get("error"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result["error"])

    settings = get_settings()
    email_sent = False
    if settings.agentmail_api_key:
        try:
            import agentmail

            # Best-effort invite email (SDK client is agentmail.AgentMail; there is no agentmail.Client).
            org_row = await db.execute(select(Organization).where(Organization.id == org_id))
            org = org_row.scalar_one_or_none()
            inbox_id = org.agentmail_inbox_id if org else None
            if inbox_id:
                client = agentmail.AgentMail(api_key=settings.agentmail_api_key)
                temp_password = result.get("temp_password", "")
                client.inboxes.messages.send(
                    inbox_id=inbox_id,
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
                    labels=["team-invite"],
                )
                email_sent = True
        except Exception:
            pass  # AgentMail not configured, missing inbox, or send failed

    message = (
        "User account created. Invitation email sent."
        if email_sent
        else "User account created. Email invitation pending AgentMail integration."
    )
    return {
        "status": "user_created",
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
