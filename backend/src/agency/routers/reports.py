"""Reports router — generate and retrieve client reports."""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import Client
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
    """List the report periods that can be generated for a client.

    These are the fixed periods ``POST /reports/clients/{client_id}`` accepts —
    NOT a list of reports already generated and stored. Nothing is persisted;
    reports are computed on request.

    The response body carries no client data, so there is nothing to leak — but the
    route still resolves ``client_id`` against ``org_id`` so that probing it cannot be
    used to confirm whether a client id exists in another tenant.
    """
    owner = await db.execute(
        select(Client.id).where(Client.id == client_id, Client.org_id == org_id)
    )
    if owner.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    return {
        "kind": "available_periods",
        "items": [
            {"period": "weekly", "label": "Last 7 days"},
            {"period": "monthly", "label": "Last 30 days"},
            {"period": "quarterly", "label": "Last 90 days"},
        ]
    }
