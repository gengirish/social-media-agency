"""Create › Launch — Product launch (+ PRFAQ stress-test), Community kit, Partnership outreach.

Kits are stored as ``creative_asset`` rows (kinds ``launch_kit``,
``community_kit``, ``outreach_pitch``) and listed/deleted through ``/assets``.

The PRFAQ stress-test is not a list item: like Cadence's ``profile.prfaq`` it is
one current critique per client, replaced on regenerate. It lives at
``client.settings["prfaq"]`` next to ``campaign_focus``, and the launch-kit
generator reads it so the kit addresses the weak spot it named. Each launch
kit's payload records ``prfaq_addressed`` so the card can say which kits were
written with a stress-test in hand.

Nothing here is submitted or sent anywhere — no Product Hunt, press-list,
Discord/Slack or CRM integration exists. These are drafts.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents.launch_pr import (
    generate_community_kit,
    generate_launch_kit,
    generate_outreach_pitch,
    generate_prfaq,
)
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import Client
from agency.services.brand_context import get_org_client, load_brand_context
from agency.services.create_kits import (
    generate_asset,
    require_brand_profile,
    run_generation,
    validate_community_kit,
    validate_launch_kit,
    validate_outreach_pitch,
    validate_prfaq,
)
from agency.services.generation_quota import charge_generation, require_generation_quota

router = APIRouter(prefix="/create/launch", tags=["Create › Launch"])

LaunchMode = Literal["launch_kit", "community_kit", "outreach_pitch"]


class ClientRequest(BaseModel):
    client_id: UUID


class PrfaqRequest(BaseModel):
    client_id: UUID
    #: What is being launched, in the user's own words (CF-13). Optional, and a
    #: real source of facts — unlike anything the model supplies, it comes from
    #: the person who knows. The brand profile alone does not say what the launch
    #: *is*, which is part of why the stress-test filled that gap itself.
    note: str = ""


class LaunchGenerateRequest(BaseModel):
    client_id: UUID
    mode: LaunchMode


def _settings(client: Client) -> dict[str, Any]:
    raw: Any = client.settings
    return dict(raw) if isinstance(raw, dict) else {}


def _stored_prfaq(client: Client) -> dict[str, Any] | None:
    prfaq = _settings(client).get("prfaq")
    return prfaq if isinstance(prfaq, dict) else None


@router.get("/prfaq")
async def get_prfaq(
    client_id: UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """The client's current stress-test, or ``null`` when none has been run."""
    client = await get_org_client(db, client_id, org_id)
    return {"prfaq": _stored_prfaq(client)}


@router.post("/prfaq")
async def run_prfaq(
    body: PrfaqRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """Run (or re-run) the stress-test. Replaces the previous one; charges one generation.

    ``note`` is optional context about what is being launched. The UI asks for it
    on the confirm step that now precedes this call (CF-13) — one click used to
    spend a generation with no warning and no way to say what the launch was.
    """
    client = await get_org_client(db, body.client_id, org_id)
    await require_brand_profile(db, client, org_id)
    await require_generation_quota(db, org_id)
    brand = await load_brand_context(db, client, org_id)

    async def produce() -> Any:
        return await generate_prfaq(brand, body.note)

    prfaq = await run_generation(
        org_id=org_id, label="prfaq", produce=produce, validate=validate_prfaq
    )
    prfaq["generated_at"] = datetime.now(UTC).isoformat()
    merged = _settings(client)
    merged["prfaq"] = prfaq
    # Reassign (not mutate) so SQLAlchemy sees the JSONB change.
    client.settings = merged  # type: ignore[assignment]
    await charge_generation(db, org_id)
    await db.commit()
    return {"prfaq": prfaq}


@router.post("/generate")
async def generate(
    body: LaunchGenerateRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(get_org_id),
) -> dict[str, Any]:
    """One kit for the chosen mode. Charges one generation only on a complete kit."""
    client = await get_org_client(db, body.client_id, org_id)
    await require_brand_profile(db, client, org_id)
    brand = await load_brand_context(db, client, org_id)

    prfaq = _stored_prfaq(client) if body.mode == "launch_kit" else None
    producers: dict[str, Callable[[], Awaitable[Any]]] = {
        "launch_kit": lambda: generate_launch_kit(brand, prfaq),
        "community_kit": lambda: generate_community_kit(brand),
        "outreach_pitch": lambda: generate_outreach_pitch(brand),
    }
    validators: dict[str, Callable[[Any], dict[str, Any]]] = {
        "launch_kit": lambda raw: {
            **validate_launch_kit(raw),
            "prfaq_addressed": prfaq is not None,
        },
        "community_kit": validate_community_kit,
        "outreach_pitch": validate_outreach_pitch,
    }

    return await generate_asset(
        db,
        org_id=org_id,
        client=client,
        kind=body.mode,
        produce=producers[body.mode],
        validate=validators[body.mode],
        created_by=user.get("sub"),
    )
