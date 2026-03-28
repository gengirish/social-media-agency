"""Reports router — generate and retrieve client reports."""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.services.reporting import generate_report_data

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("/clients/{client_id}")
async def create_report(
    client_id: UUID,
    body: dict | None = Body(default=None),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Generate a report for a client."""
    period = (body or {}).get("period", "monthly")
    report = await generate_report_data(db, client_id, org_id, period)
    if "error" in report:
        raise HTTPException(status.HTTP_404_NOT_FOUND, report["error"])
    return report


@router.get("/clients/{client_id}")
async def list_reports(
    client_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """List available report periods for a client."""
    return {
        "items": [
            {"period": "weekly", "label": "Last 7 days"},
            {"period": "monthly", "label": "Last 30 days"},
            {"period": "quarterly", "label": "Last 90 days"},
        ]
    }
