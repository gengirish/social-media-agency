"""Manual posts in Insights and in the metrics path — an unknown is never a zero.

Manual mode (``docs/manual-publish-plan-260929.md``) records that a human posted a
piece by hand. Nothing was sent, so no platform ``post_id`` exists, and with no link
recorded there is not even a URL to identify the post by. **There is therefore no
number to fetch, now or ever** — which makes this the exact place product rule 4 gets
tested: a missing metric must stay missing, not become a 0 that reads as "nobody
engaged".

Two groups of tests, and they exist for opposite reasons:

1. **Averages exclude a link-less manual post** (``services/insights.py``). A zero in
   an average is indistinguishable from a measurement once divided, so the exclusion is
   the only place it can be caught. ``engagement.manual_unlinked`` is the count the UI
   renders "Posted manually — no link, metrics unavailable" from.

2. **A ``status = 'manual'`` ``platform_account`` is refused by every path that needs a
   token** (``services/insights.py``, ``services/analytics_fetcher.py`). These filters
   already read ``status == "connected"`` and nothing here changes them. The tests exist
   because the plan's §1 risk table names exactly this failure — "a filter gets widened
   by reflex and a tokenless row reaches a publisher" — and nothing in the suite was
   holding these two down. A manual row has ``access_token_enc IS NULL``, so a widened
   filter here means an API call with no credentials, reported as an error the operator
   cannot act on.
"""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from agency.models.tables import AnalyticsSnapshot, Client, ContentPiece
from agency.services.insights import build_summary, is_unmeasurable_manual
from tests.conftest import (
    _persist,
    auth_header_for,
    create_client_row,
    create_content_row,
    create_org,
    create_platform_account,
    create_subscription,
    create_user_row,
)

API = "/api/v1"

POST_URL = "https://www.linkedin.com/feed/update/urn:li:activity:1/"


# ---------------------------------------------------------------------------
# The predicate itself
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({"publish_mode": "manual"}, True),
        ({"publish_mode": "manual", "post_url": None}, True),
        ({"publish_mode": "manual", "post_url": ""}, True),
        ({"publish_mode": "manual", "post_url": POST_URL}, False),
        # Product-published: the platform returned an id, so metrics have a path.
        ({"post_id": "p1", "post_url": POST_URL}, False),
        # No link either, but the product published it — the post_id is the handle, so
        # this one is a genuine gap in measurement, not an impossibility.
        ({"post_id": "p1"}, False),
        ({}, False),
        (None, False),
    ],
)
def test_is_unmeasurable_manual(metadata, expected):
    assert is_unmeasurable_manual(metadata) is expected


# ---------------------------------------------------------------------------
# Insights averages
# ---------------------------------------------------------------------------
@pytest.fixture
async def tenant(session_factory):
    org_id = await create_org(session_factory, "Manual Insights Org")
    await create_subscription(session_factory, org_id, plan_tier="growth", posts_limit=100)
    client_id = await create_client_row(session_factory, org_id, "Manual Insights Brand")
    user_id = await create_user_row(session_factory, org_id)
    return SimpleNamespace(
        org_id=org_id,
        client_id=client_id,
        headers=auth_header_for(org_id, user_id=user_id),
    )


async def _client_row(session_factory, client_id: UUID) -> Client:
    async with session_factory() as s:
        return (await s.execute(select(Client).where(Client.id == client_id))).scalar_one()


async def _published(session_factory, tenant, metadata: dict[str, Any]) -> UUID:
    content_id = await create_content_row(
        session_factory,
        tenant.org_id,
        tenant.client_id,
        platform="linkedin",
        status="published",
        metadata=metadata,
    )
    async with session_factory() as s:
        row = await s.get(ContentPiece, content_id)
        assert row is not None
        row.published_at = datetime.now(UTC)
        await s.commit()
    return content_id


async def _snapshot(session_factory, account_id: UUID, content_id: UUID, engagement: int) -> None:
    await _persist(
        session_factory,
        AnalyticsSnapshot(
            id=uuid4(),
            platform_account_id=account_id,
            content_id=content_id,
            date=date.today(),
            engagement=engagement,
        ),
    )


async def test_a_linkless_manual_post_is_excluded_from_averages(
    client, session_factory, tenant, db
):
    """The load-bearing test. A 0 on the link-less post and a 10 on the linked one: the
    average must be 10 over one post, not 5 over two.

    The zero snapshot is deliberately implausible — nothing should ever write one for a
    post with no platform id — because that is the failure this guards. Averaged in, it
    would halve the platform's engagement and there would be no way to tell from the
    number that it had happened.
    """
    account_id = await create_platform_account(
        session_factory, tenant.org_id, tenant.client_id, platform="linkedin", status="connected"
    )
    linkless = await _published(session_factory, tenant, {"publish_mode": "manual"})
    linked = await _published(
        session_factory, tenant, {"publish_mode": "manual", "post_url": POST_URL}
    )
    await _snapshot(session_factory, account_id, linkless, 0)
    await _snapshot(session_factory, account_id, linked, 10)

    row = await _client_row(session_factory, tenant.client_id)
    summary = await build_summary(db, tenant.org_id, row)

    assert summary["engagement"]["by_platform"] == [
        {"platform": "linkedin", "posts": 1, "avg_engagement": 10, "total_engagement": 10}
    ]
    assert summary["engagement"]["posts_measured"] == 1
    # And the excluded post is reported rather than silently dropped: this is what the
    # UI renders "Posted manually — no link, metrics unavailable" from.
    assert summary["engagement"]["manual_unlinked"] == 1


async def test_manual_unlinked_count_over_the_api(client, session_factory, tenant):
    """The count reaches the client, since the Insights screen is what explains the gap."""
    await _published(session_factory, tenant, {"publish_mode": "manual"})
    await _published(session_factory, tenant, {"publish_mode": "manual", "post_url": POST_URL})
    # A product-published post is not a manual one, however unmeasured it is.
    await _published(session_factory, tenant, {"post_id": "p1"})

    resp = await client.get(
        f"{API}/insights/summary?client_id={tenant.client_id}", headers=tenant.headers
    )

    assert resp.status_code == 200, resp.text
    engagement = resp.json()["engagement"]
    assert engagement["manual_unlinked"] == 1
    # Nothing was measured, so the panel says unavailable — not zero engagement.
    assert engagement["status"] == "unavailable"
    assert engagement["posts_measured"] == 0
    assert engagement["by_platform"] == []


async def test_a_linkless_manual_post_still_counts_as_published(
    client, session_factory, tenant, db
):
    """Excluded from *averages*, not from the record. It really was published, the
    billing meter charged for it, and pretending otherwise would make Insights and
    Billing disagree (the plan's §5 open question, answered this way here)."""
    await _published(session_factory, tenant, {"publish_mode": "manual"})

    row = await _client_row(session_factory, tenant.client_id)
    summary = await build_summary(db, tenant.org_id, row)

    assert summary["funnel"]["published"] == 1
    assert summary["total_posts"] == 1


# ---------------------------------------------------------------------------
# A manual channel is not a connected one — the filters the plan's §1 table says
# must stay narrow. Nothing here changes them; these tests make widening them loud.
# ---------------------------------------------------------------------------
async def test_insights_does_not_report_a_manual_channel_as_connected(
    client, session_factory, tenant, db
):
    """``services/insights.py``'s ``status == "connected"`` filter.

    A manual channel has no token and no metrics path, so counting it as connected
    would make the "neglected platform" recommendation nag about a channel the product
    cannot measure, and the Accounts-facing count would claim a connection that does
    not exist.
    """
    await create_platform_account(
        session_factory, tenant.org_id, tenant.client_id, platform="instagram", status="manual"
    )
    await create_platform_account(
        session_factory, tenant.org_id, tenant.client_id, platform="linkedin", status="connected"
    )

    row = await _client_row(session_factory, tenant.client_id)
    summary = await build_summary(db, tenant.org_id, row)

    assert summary["connected_platforms"] == ["linkedin"]
    assert {row["platform"]: row["connected"] for row in summary["by_platform"]} == {
        "linkedin": True
    }


async def test_analytics_fetcher_refuses_a_manual_channel(session_factory, db):
    """``services/analytics_fetcher.py``'s ``status == "connected"`` filter.

    A manual row carries ``access_token_enc IS NULL``. Widen this filter and the fetcher
    selects it and calls the platform API with no credentials — so the honest
    "no connected account" answer becomes an auth error nobody can act on, and the
    premise of manual mode (the product never touches these pages) is gone.
    """
    from agency.services import analytics_fetcher

    org_id = await create_org(session_factory, "Fetcher Org")
    client_id = await create_client_row(session_factory, org_id, "Fetcher Brand")
    await create_platform_account(
        session_factory, org_id, client_id, platform="linkedin", status="manual"
    )
    content_id = await create_content_row(
        session_factory,
        org_id,
        client_id,
        platform="linkedin",
        status="published",
        metadata={"publish_mode": "manual", "post_url": POST_URL, "post_id": "should-not-be-used"},
    )

    result = await analytics_fetcher.fetch_content_metrics(db, content_id)

    assert result["status"] == "unavailable"
    assert "No connected linkedin account" in result["reason"]

    # And nothing was persisted, so no snapshot exists to be averaged later.
    async with session_factory() as s:
        rows = await s.execute(
            select(AnalyticsSnapshot).where(AnalyticsSnapshot.content_id == content_id)
        )
        assert rows.scalars().all() == []


async def test_analytics_fetcher_positive_control(session_factory, db, monkeypatch):
    """Guards the test above from passing because the fetcher refuses everything.

    The same piece on a *connected* channel reaches the platform call — stubbed, since
    the point is which rows the filter admits, not the HTTP.
    """
    from agency.services import analytics_fetcher

    org_id = await create_org(session_factory, "Fetcher OK Org")
    client_id = await create_client_row(session_factory, org_id, "Fetcher OK Brand")
    await create_platform_account(
        session_factory, org_id, client_id, platform="linkedin", status="connected"
    )
    content_id = await create_content_row(
        session_factory,
        org_id,
        client_id,
        platform="linkedin",
        status="published",
        metadata={"post_id": "p1"},
    )

    async def _fake(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"status": "ok", "engagement": 7, "extra": {"source": "stub"}}

    monkeypatch.setattr(analytics_fetcher, "fetch_post_metrics", _fake)

    result = await analytics_fetcher.fetch_content_metrics(db, content_id)

    assert result["status"] == "ok", result
