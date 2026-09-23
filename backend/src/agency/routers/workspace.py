"""Settings screen data for the active client: activity log, export, posting prefs.

Thin router; every ``client_id`` is resolved against ``org_id`` before use.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agency.dependencies import get_current_user, get_db, get_org_id
from agency.services.activity import MAX_EVENTS, client_activity
from agency.services.brand_context import get_org_client
from agency.services.workspace_export import export_client

router = APIRouter(prefix="/workspace", tags=["Workspace"])

#: Cadence's VOICE_OPTIONS and CADENCE_OPTIONS, verbatim.
VoiceRegister = Literal[
    "Blunt & technical", "Friendly & casual", "Bold & punchy", "Calm & authoritative"
]
CadencePerWeek = Literal[3, 5, 7, 14]


@router.get("/activity")
async def activity_log(
    client_id: UUID,
    limit: int = Query(MAX_EVENTS, ge=1, le=MAX_EVENTS),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """The client's most recent events, newest first, derived from real rows."""
    client = await get_org_client(db, client_id, org_id)
    return {"items": await client_activity(db, org_id, client, limit)}


@router.get("/export")
async def export(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> Response:
    """Everything stored for this client as a downloadable JSON file."""
    client = await get_org_client(db, client_id, org_id)
    data = await export_client(db, org_id, client)
    slug = re.sub(r"[^a-z0-9]+", "-", (client.brand_name or "client").lower()).strip("-")
    filename = f"campaignforge-{slug or 'client'}-{datetime.now(UTC):%Y-%m-%d}.json"
    return Response(
        content=json.dumps(data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class PostingPrefs(BaseModel):
    voice_register: VoiceRegister | None = None
    cadence_per_week: CadencePerWeek | None = None


def _prefs(settings: Any) -> dict[str, Any]:
    prefs = (settings or {}).get("posting_prefs") if isinstance(settings, dict) else None
    return prefs if isinstance(prefs, dict) else {}


@router.get("/posting-prefs")
async def get_posting_prefs(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    client = await get_org_client(db, client_id, org_id)
    return {"posting_prefs": _prefs(client.settings)}


@router.put("/posting-prefs")
async def set_posting_prefs(
    client_id: UUID,
    body: PostingPrefs,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Stored in ``client.settings.posting_prefs``. ``brand_prompt_block`` feeds the
    voice register and cadence to every generator."""
    client = await get_org_client(db, client_id, org_id)
    settings: Any = client.settings
    merged = dict(settings) if isinstance(settings, dict) else {}
    prefs = {k: v for k, v in body.model_dump().items() if v is not None}
    prefs["updated_at"] = datetime.now(UTC).isoformat()
    merged["posting_prefs"] = prefs
    # Reassign (not mutate) so SQLAlchemy sees the JSONB change.
    client.settings = merged  # type: ignore[assignment]
    await db.commit()
    return {"posting_prefs": prefs}
