"""Team API — members, invites, role updates."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from agency.dependencies import get_current_user, get_db, get_org_id
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
    invited_by = user.get("email") or str(user.get("sub", ""))
    result = await invite_team_member(
        db, org_id, body.email, body.role, invited_by
    )
    if result.get("error"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result["error"])
    return result


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
