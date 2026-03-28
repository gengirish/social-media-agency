"""Client acquisition router — prospect outreach generation."""

from fastapi import APIRouter, Depends, HTTPException, status

from agency.dependencies import get_current_user

router = APIRouter(prefix="/acquisition", tags=["Client Acquisition"])


@router.post("/outreach")
async def generate_outreach_sequence(
    body: dict,
    user=Depends(get_current_user),
):
    """Generate an outreach sequence for a prospect."""
    prospect_name = body.get("prospect_name", "")
    prospect_industry = body.get("industry", "")
    pain_points = body.get("pain_points", [])

    if not prospect_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "prospect_name required")

    from agency.services.client_acquisition import generate_outreach

    result = await generate_outreach(prospect_name, prospect_industry, pain_points)
    return result
