"""Industry-benchmark privacy floor.

``get_industry_benchmarks`` is the one query in the codebase that deliberately
crosses tenant boundaries. These tests pin the floor that makes that safe: below
:data:`MIN_CONTRIBUTING_ORGS` distinct organisations, the average is close enough
to a single account's numbers to be an inference channel, so nothing is returned.

The floor counts *organisations*, not snapshots — see
``test_one_org_with_many_snapshots_is_still_suppressed``, which guards against
someone "optimising" it into a sample-size check.
"""

from datetime import date
from uuid import uuid4

import pytest

from agency.models.tables import AnalyticsSnapshot
from agency.services.cross_learning import (
    MIN_CONTRIBUTING_ORGS,
    get_industry_benchmarks,
)
from tests.conftest import (
    create_client_row,
    create_content_row,
    create_org,
    create_platform_account,
)

INDUSTRY = "Coffee Roasting"


async def _snapshot(
    session_factory, account_id, content_id, *, impressions=1000, engagement=50
):
    async with session_factory() as db:
        db.add(
            AnalyticsSnapshot(
                id=uuid4(),
                platform_account_id=account_id,
                content_id=content_id,
                date=date.today(),
                impressions=impressions,
                engagement=engagement,
                clicks=10,
                likes=25,
            )
        )
        await db.commit()


async def _seed_orgs(session_factory, count: int, *, snapshots_per_org: int = 1):
    """Create ``count`` orgs, each with one client in INDUSTRY and snapshots."""
    for i in range(count):
        org_id = await create_org(session_factory, f"Org {i}")
        client_id = await create_client_row(session_factory, org_id, industry=INDUSTRY)
        account_id = await create_platform_account(session_factory, org_id, client_id)
        for _ in range(snapshots_per_org):
            content_id = await create_content_row(
                session_factory, org_id, client_id, status="published"
            )
            await _snapshot(session_factory, account_id, content_id)


async def test_no_snapshots_reports_no_data(db, session_factory):
    result = await get_industry_benchmarks(db, INDUSTRY)

    assert result["status"] == "unavailable"
    assert "No analytics snapshots" in result["reason"]
    assert result["sample_size"] == 0
    assert result["avg_impressions"] is None


async def test_below_floor_is_suppressed(db, session_factory):
    await _seed_orgs(session_factory, MIN_CONTRIBUTING_ORGS - 1)

    result = await get_industry_benchmarks(db, INDUSTRY)

    assert result["status"] == "unavailable"
    assert str(MIN_CONTRIBUTING_ORGS) in result["reason"]
    assert result["avg_impressions"] is None
    assert result["avg_engagement"] is None


async def test_suppressed_response_leaks_no_counts(db, session_factory):
    """Returning the real sample size would leak what the floor protects."""
    await _seed_orgs(session_factory, MIN_CONTRIBUTING_ORGS - 1, snapshots_per_org=7)

    result = await get_industry_benchmarks(db, INDUSTRY)

    assert result["status"] == "unavailable"
    assert result["sample_size"] == 0
    assert result["contributing_orgs"] == 0


async def test_at_floor_returns_the_benchmark(db, session_factory):
    await _seed_orgs(session_factory, MIN_CONTRIBUTING_ORGS)

    result = await get_industry_benchmarks(db, INDUSTRY)

    assert result["status"] == "available"
    assert result["contributing_orgs"] == MIN_CONTRIBUTING_ORGS
    assert result["sample_size"] == MIN_CONTRIBUTING_ORGS
    assert result["avg_impressions"] == pytest.approx(1000.0)


async def test_one_org_with_many_snapshots_is_still_suppressed(db, session_factory):
    """The floor counts orgs, not rows. One account is one account."""
    await _seed_orgs(session_factory, 1, snapshots_per_org=50)

    result = await get_industry_benchmarks(db, INDUSTRY)

    assert result["status"] == "unavailable"
    assert result["contributing_orgs"] == 0


async def test_other_industries_do_not_count_toward_the_floor(db, session_factory):
    await _seed_orgs(session_factory, 2)
    for i in range(5):
        org_id = await create_org(session_factory, f"Other {i}")
        client_id = await create_client_row(session_factory, org_id, industry="Fintech")
        account_id = await create_platform_account(session_factory, org_id, client_id)
        content_id = await create_content_row(
            session_factory, org_id, client_id, status="published"
        )
        await _snapshot(session_factory, account_id, content_id)

    result = await get_industry_benchmarks(db, INDUSTRY)

    assert result["status"] == "unavailable"
