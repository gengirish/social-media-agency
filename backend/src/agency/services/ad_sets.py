"""Create › Ads orchestration: generate → guardrails → advisory moderation → payload.

The router stays thin; the pure checks live in :mod:`agency.services.ad_guardrails`
and the prompts in :mod:`agency.agents.ads`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.agents.ads import generate_ad_set, moderate_ad_copy
from agency.models.tables import CreativeAsset
from agency.services.ad_guardrails import (
    ad_copy_text,
    collect_competitor_names,
    find_personal_attribute_risks,
    find_trademark_risks,
    validate_ad_assets,
)

#: Asset kinds whose payloads name this client's competitors.
COMPETITOR_SOURCE_KINDS = ("comparison_page", "niche_scan")


async def known_competitor_names(db: AsyncSession, org_id: UUID, client_id: UUID) -> list[str]:
    """Every competitor already named for this client (comparison pages, niche scans).

    ``client_id`` must already be org-resolved; the ``org_id`` filter is kept
    anyway because there is no row-level security.
    """
    payloads = (
        await db.execute(
            select(CreativeAsset.payload).where(
                CreativeAsset.org_id == org_id,
                CreativeAsset.client_id == client_id,
                CreativeAsset.kind.in_(COMPETITOR_SOURCE_KINDS),
            )
        )
    ).scalars()
    return collect_competitor_names(payloads)


async def build_ad_set(
    network: str, brand: dict[str, Any], competitor_names: list[str]
) -> dict[str, Any]:
    """Generate one ad set and attach every guardrail result.

    Raises whatever generation raises (the caller turns it into a 502 with no
    quota charged). Moderation never raises — it fails open.
    """
    assets = await generate_ad_set(network, brand)
    copy = ad_copy_text(network, assets)
    moderation = await moderate_ad_copy(copy, network)
    payload: dict[str, Any] = {
        "network": network,
        **assets,
        "limit_warnings": validate_ad_assets(network, assets),
        "trademark_risks": find_trademark_risks(copy, competitor_names),
        "moderation": moderation,
    }
    if network == "meta":
        payload["personal_attribute_risks"] = find_personal_attribute_risks(copy)
    return payload
