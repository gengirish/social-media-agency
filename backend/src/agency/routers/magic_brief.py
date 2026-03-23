"""Magic Brief API — brand extraction from a URL."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from agency.dependencies import get_current_user
from agency.services.magic_brief import extract_brand_from_url

router = APIRouter(prefix="/magic-brief", tags=["Magic Brief"])


class MagicBriefRequest(BaseModel):
    url: str


@router.post("")
async def create_magic_brief(
    body: MagicBriefRequest,
    user=Depends(get_current_user),
):
    profile = await extract_brand_from_url(body.url)
    if profile.get("error"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, profile["error"])
    return profile
