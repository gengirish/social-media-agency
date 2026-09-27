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
    # Not published, and not attributed to any account: the row belongs to org B.
    assert piece.status != "published"
    assert piece.metadata_["publish_blocked"]["code"] == "no_connected_account"


# ---------------------------------------------------------------------------
# CF-01 — nothing connected is a workspace gap, not a failed post
# ---------------------------------------------------------------------------
async def test_no_connected_account_returns_the_post_to_approved(
    session_factory, tenants, published
):
    """It used to land in Failed, whose only action was Delete.

    The post is fine; there is simply nowhere to send it — which for most orgs
    means the platform's app credentials are not set on the server at all, so no
    Connect button can even be pressed.
    """
    piece = await _run(session_factory, tenants["content_a"])

    assert published == []
    assert piece.status == "approved"
    # The schedule is cleared, or the once-a-minute sweep picks it up forever.
    assert piece.scheduled_at is None

    blocked = piece.metadata_["publish_blocked"]
    assert blocked["code"] == "no_connected_account"
    assert blocked["platform"] == piece.platform
    assert "Setup" in blocked["reason"]
    # Nothing about this is a publish failure, so the Failed banner must stay off.
    assert "publish_error" not in piece.metadata_


async def test_rescheduling_clears_the_blocked_notice(session_factory, tenants, published):
    """Otherwise a queued post keeps showing why it was blocked last time."""
    from datetime import UTC, datetime, timedelta

    await _run(session_factory, tenants["content_a"])

    async with session_factory() as db:
        await SchedulerEngine().schedule_content(
            db, tenants["content_a"], datetime.now(UTC) + timedelta(days=1)
        )

    async with session_factory() as db:
        piece = await db.get(ContentPiece, tenants["content_a"])

    assert piece.status == "scheduled"
    assert "publish_blocked" not in piece.metadata_


async def test_publishing_clears_the_blocked_notice(session_factory, tenants, published):
    """A live post must not carry a warning from an earlier blocked attempt."""
    await _run(session_factory, tenants["content_a"])
    await create_platform_account(session_factory, tenants["org_a"], tenants["client_a"])

    async with session_factory() as db:
        piece = await db.get(ContentPiece, tenants["content_a"])
        piece.status = "scheduled"
        await db.commit()

    piece = await _run(session_factory, tenants["content_a"])

    assert piece.status == "published"
    assert "publish_blocked" not in piece.metadata_


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
