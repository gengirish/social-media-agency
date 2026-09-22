"""The scheduler's publish step: which account it posts with, and what it refuses.

``_publish_piece`` is the path that posts to a live account with nobody watching, so
each test here asserts on what reached the publisher — not just on the final status.
"""

from typing import Any

import pytest
from sqlalchemy import select

from agency.models.tables import Client, ContentPiece
from agency.services.publishing import publisher
from agency.services.scheduler import SchedulerEngine
from tests.conftest import (
    create_client_row,
    create_content_row,
    create_org,
    create_platform_account,
    create_subscription,
)


@pytest.fixture
def published(monkeypatch) -> list[dict[str, Any]]:
    """Record every call that reaches the platform publisher, and report success."""
    calls: list[dict[str, Any]] = []

    async def _record(platform: str, content: dict, credentials: dict) -> dict:
        calls.append({"platform": platform, "credentials": credentials})
        return {"success": True, "post_id": "p1", "url": "https://example.com/p1"}

    monkeypatch.setattr(publisher, "publish", _record)
    return calls


@pytest.fixture
async def tenants(session_factory):
    org_a = await create_org(session_factory, "Org A")
    org_b = await create_org(session_factory, "Org B")
    await create_subscription(session_factory, org_a, plan_tier="growth", posts_limit=1000)
    client_a = await create_client_row(session_factory, org_a, "Brand A")
    content_a = await create_content_row(
        session_factory, org_a, client_a, status="scheduled"
    )
    return {"org_a": org_a, "org_b": org_b, "client_a": client_a, "content_a": content_a}


async def _run(session_factory, content_id) -> ContentPiece:
    async with session_factory() as db:
        piece = (
            await db.execute(select(ContentPiece).where(ContentPiece.id == content_id))
        ).scalar_one()
        await SchedulerEngine()._publish_piece(db, piece)
    async with session_factory() as db:
        return await db.get(ContentPiece, content_id)


async def test_ignores_other_orgs_account_for_same_client(session_factory, tenants, published):
    """Org B holds an account row carrying org A's client id — it must not be used."""
    await create_platform_account(
        session_factory, tenants["org_b"], tenants["client_a"], account_handle="org-b"
    )

    piece = await _run(session_factory, tenants["content_a"])

    assert published == []
    assert piece.status == "failed"
    assert piece.metadata_["publish_error"] == "No connected platform account"


async def test_duplicate_accounts_do_not_crash(session_factory, tenants, published):
    """Two matching rows used to hit ``scalar_one_or_none`` and raise."""
    for handle in ("first", "second"):
        await create_platform_account(
            session_factory, tenants["org_a"], tenants["client_a"], account_handle=handle
        )

    piece = await _run(session_factory, tenants["content_a"])

    assert piece.status == "published"
    assert len(published) == 1


async def test_archived_client_is_not_published(session_factory, tenants, published):
    await create_platform_account(session_factory, tenants["org_a"], tenants["client_a"])
    async with session_factory() as db:
        (await db.get(Client, tenants["client_a"])).is_active = False
        await db.commit()

    piece = await _run(session_factory, tenants["content_a"])

    assert published == []
    assert piece.status == "failed"
    assert piece.metadata_["publish_error"] == "Client is archived"
