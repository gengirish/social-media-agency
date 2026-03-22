from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.schemas import DashboardStats
from agency.models.tables import AgentRun, Campaign, Client, ContentPiece

router = APIRouter(prefix="/stats", tags=["Stats"])


@router.get("", response_model=DashboardStats)
async def get_dashboard_stats(
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    clients = (
        await db.execute(
            select(func.count(Client.id)).where(Client.org_id == org_id, Client.is_active == True)
        )
    ).scalar() or 0

    campaigns = (
        await db.execute(
            select(func.count(Campaign.id)).where(Campaign.org_id == org_id)
        )
    ).scalar() or 0

    content = (
        await db.execute(
            select(func.count(ContentPiece.id)).where(ContentPiece.org_id == org_id)
        )
    ).scalar() or 0

    agent_runs = (
        await db.execute(
            select(func.count(AgentRun.id)).where(AgentRun.org_id == org_id)
        )
    ).scalar() or 0

    running = (
        await db.execute(
            select(func.count(Campaign.id)).where(
                Campaign.org_id == org_id, Campaign.status == "running"
            )
        )
    ).scalar() or 0

    drafts = (
        await db.execute(
            select(func.count(ContentPiece.id)).where(
                ContentPiece.org_id == org_id, ContentPiece.status == "draft"
            )
        )
    ).scalar() or 0

    return DashboardStats(
        total_clients=clients,
        total_campaigns=campaigns,
        total_content_pieces=content,
        total_agent_runs=agent_runs,
        campaigns_running=running,
        content_drafts=drafts,
    )
