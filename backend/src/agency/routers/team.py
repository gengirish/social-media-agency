"""Team API — members, invites, role updates."""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from agency.dependencies import get_current_user, get_current_user_id, get_db, get_org_id
from agency.permissions import Capability, require_cap
from agency.services.email_service import send_email
from agency.services.team import (
    invite_team_member,
    list_team_members,
    reset_invite_password,
    update_member_role,
)

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


async def _send_invite_email(
    *, db, org_id: UUID, email: str, temp_password: str, invited_by: str
):
    """Mail one invitation. Shared by the first invite and every resend.

    Both paths must produce identical mail, so the body lives here rather than
    being written twice. Best-effort by `email_service` contract: it returns a
    `SendResult` and never raises, so a dead API key or an unverified sending
    domain cannot fail the request that created the account.
    """
    send = await send_email(
        to=email,
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
        logger.warning("team_invite_email_not_sent", email=email, reason=send.reason)
    return send


@router.post("/invite", dependencies=[Depends(require_cap(Capability.TEAM_MANAGE))])
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

    A successful invite also flips the org from ``personal`` to ``business``
    (`services.team.invite_team_member`, in the invite's own transaction).
    """
    # TODO: Replace the temp-password flow with signed invite links and
    # org-branded templates. Mailing a password is a stopgap.
    invited_by = user.get("email") or str(user.get("sub", ""))
    result = await invite_team_member(
        db, org_id, body.email, body.role, invited_by
    )
    if result.get("error"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result["error"])

    send = await _send_invite_email(
        db=db,
        org_id=org_id,
        email=body.email,
        temp_password=result.get("temp_password", ""),
        invited_by=invited_by,
    )

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


@router.patch(
    "/{user_id}/role", dependencies=[Depends(require_cap(Capability.TEAM_MANAGE))]
)
async def patch_member_role(
    user_id: UUID,
    body: RoleUpdateRequest,
    user=Depends(get_current_user),
    caller_id: UUID = Depends(get_current_user_id),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Change a team member's role.

    Two blocks live here rather than in ``services.team.update_member_role``:

    * **Nobody edits their own role.** Until this route was gated, any
      authenticated user in an org could PATCH themselves to ``admin``. The
      capability gate closes that for members and viewers; this stops an admin
      quietly self-promoting to ``owner`` — or demoting the last one, themselves.
    * **No update assigns ``owner``.** An org has one owner, established at
      provisioning. The service layer stays permissive on purpose so a real
      ownership *transfer* (demote the incumbent and promote the successor in one
      operation) stays expressible later; the policy belongs at the edge.
    """
    if user_id == caller_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {"code": "cannot_change_own_role"},
        )
    if body.role == "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {"code": "cannot_assign_owner"},
        )

    result = await update_member_role(db, org_id, user_id, body.role)
    if result.get("error"):
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in result["error"].lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(code, result["error"])
    return result


@router.post(
    "/{user_id}/resend-invite",
    dependencies=[Depends(require_cap(Capability.TEAM_MANAGE))],
)
async def resend_member_invite(
    user_id: UUID,
    user=Depends(get_current_user),
    caller_id: UUID = Depends(get_current_user_id),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Re-send an invitation, rotating the member's temporary password.

    This exists because a failed *email* still leaves a real account behind:
    ``POST /team/invite`` then rejects that address forever with "User with this
    email already exists", so an invitee whose mail never arrived had no route
    back. Production ran without ``AGENTMAIL_API_KEY`` and stranded invitees
    exactly that way.

    Self-resend is refused for the same reason ``PATCH /{user_id}/role`` refuses
    self-edits: rotating your own password hash on the local-JWT login path would
    lock you out of your own account for no benefit.
    """
    if user_id == caller_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {"code": "cannot_resend_own_invite"},
        )

    result = await reset_invite_password(db, org_id, user_id)
    if result.get("error"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, result["error"])

    invited_by = user.get("email") or str(user.get("sub", ""))
    send = await _send_invite_email(
        db=db,
        org_id=org_id,
        email=result["email"],
        temp_password=result["temp_password"],
        invited_by=invited_by,
    )

    message = (
        "Invitation email re-sent."
        if send.sent
        else (
            f"Password reset, but NO invitation email was sent. {send.reason} "
            "Share the temporary password out of band."
        )
    )
    return {
        "status": "invite_resent",
        # Same contract as the invite route: authoritative, never inferred from copy.
        "email_sent": send.sent,
        "message": message,
        "email": result["email"],
        "role": result["role"],
        "temp_password": result["temp_password"],
        "user_id": result["user_id"],
    }
