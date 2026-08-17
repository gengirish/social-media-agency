"""Tests for the live analytics path (``services/analytics_fetcher.py``).

These cover the data-reliability contract that the ROI story depends on:

* a successful platform fetch persists the values the API actually returned;
* metrics the API does not expose stay SQL ``NULL`` — never a fabricated 0;
* an ``unavailable`` result persists **nothing** and surfaces the reason;
* the daily refresh job picks exactly the rows it should.

All outbound HTTP is monkeypatched at ``httpx.AsyncClient``; an autouse guard
fails any test that would otherwise reach the network.
"""

import uuid as uuid_module
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from agency.models.tables import (
    AnalyticsSnapshot,
    Base,
    Client,
    ContentPiece,
    Organization,
    PlatformAccount,
)
from agency.services.analytics_fetcher import (
    fetch_content_metrics,
    get_content_analytics,
    refresh_published_metrics,
    select_content_for_metrics_refresh,
)
from agency.utils.encryption import encrypt_token


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json(type_, compiler, **kw):  # type: ignore[no-untyped-def]
    """SQLite has no JSONB; the generic JSON type round-trips identically."""
    return "JSON"


_TABLES = [
    model.__table__
    for model in (Organization, Client, PlatformAccount, ContentPiece, AnalyticsSnapshot)
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
async def session_factory():
    """In-memory SQLite holding just the tables this module touches."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
async def db(session_factory):
    async with session_factory() as session:
        yield session


class FakeHTTP:
    """Records requests and replies from a URL-substring routing table."""

    def __init__(self):
        self.routes: list[tuple[str, int, dict]] = []
        self.calls: list[str] = []

    def on(self, url_fragment: str, payload: dict, status_code: int = 200) -> "FakeHTTP":
        self.routes.append((url_fragment, status_code, payload))
        return self

    def _respond(self, method: str, url: str) -> httpx.Response:
        self.calls.append(url)
        request = httpx.Request(method, url)
        for fragment, status_code, payload in self.routes:
            if fragment in url:
                return httpx.Response(status_code, json=payload, request=request)
        raise AssertionError(f"Unrouted {method} to {url}")


@pytest.fixture
def http(monkeypatch):
    """Replace httpx verbs so no test can reach the network."""
    fake = FakeHTTP()

    async def fake_get(self, url, **kwargs):
        return fake._respond("GET", str(url))

    async def fake_post(self, url, **kwargs):
        return fake._respond("POST", str(url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return fake


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    """Fail loudly if a test issues HTTP without opting into the ``http`` fixture."""
    if "http" in request.fixturenames:
        return

    async def blocked(self, url, **kwargs):
        raise AssertionError(f"Unexpected outbound HTTP to {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", blocked)
    monkeypatch.setattr(httpx.AsyncClient, "post", blocked)


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------
async def seed(
    session_factory,
    *,
    platform: str = "twitter",
    content_status: str = "published",
    post_id: str | None = "1750000000000000001",
    connect_account: bool = True,
    account_status: str = "connected",
    access_token: str | None = "live-token",
    published_at: datetime | None = None,
):
    """Create org + client (+ optional platform account) + one content piece."""
    org_id = uuid_module.uuid4()
    client_id = uuid_module.uuid4()
    content_id = uuid_module.uuid4()
    account_id = uuid_module.uuid4()

    metadata: dict = {}
    if post_id:
        metadata["post_id"] = post_id

    async with session_factory() as session:
        session.add(Organization(id=org_id, name="Acme"))
        session.add(Client(id=client_id, org_id=org_id, brand_name="Acme Brand"))
        await session.flush()
        if connect_account:
            session.add(
                PlatformAccount(
                    id=account_id,
                    client_id=client_id,
                    org_id=org_id,
                    platform=platform,
                    account_handle="acme",
                    access_token_enc=(encrypt_token(access_token) if access_token else None),
                    status=account_status,
                )
            )
        session.add(
            ContentPiece(
                id=content_id,
                client_id=client_id,
                org_id=org_id,
                platform=platform,
                title="Launch post",
                body="Hello world",
                hashtags=[],
                media_urls=[],
                metadata_=metadata,
                status=content_status,
                published_at=published_at
                or (datetime.now(UTC) - timedelta(days=1)),
            )
        )
        await session.commit()

    return {"org_id": org_id, "client_id": client_id, "content_id": content_id}


def tweet_payload(
    *, likes: int, retweets: int, replies: int, quotes: int, impressions: int, clicks: int
) -> dict:
    return {
        "data": {
            "id": "1750000000000000001",
            "public_metrics": {
                "like_count": likes,
                "retweet_count": retweets,
                "reply_count": replies,
                "quote_count": quotes,
            },
            "non_public_metrics": {
                "impression_count": impressions,
                "url_link_clicks": clicks,
            },
        }
    }


async def snapshot_rows(session_factory, content_id) -> list[AnalyticsSnapshot]:
    async with session_factory() as session:
        result = await session.execute(
            select(AnalyticsSnapshot).where(AnalyticsSnapshot.content_id == content_id)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# (a) A successful fetch persists the values the platform actually returned
# ---------------------------------------------------------------------------
async def test_successful_fetch_persists_live_values(db, session_factory, http):
    ids = await seed(session_factory)
    http.on(
        "api.x.com/2/tweets/",
        tweet_payload(likes=42, retweets=7, replies=3, quotes=2, impressions=5310, clicks=88),
    )

    result = await fetch_content_metrics(db, ids["content_id"])
    await db.commit()

    assert result["status"] == "ok"
    assert result["metrics"]["likes"] == 42
    assert result["metrics"]["shares"] == 7
    assert result["metrics"]["impressions"] == 5310
    assert result["metrics"]["clicks"] == 88
    assert result["metrics"]["engagement"] == 42 + 7 + 3 + 2

    rows = await snapshot_rows(session_factory, ids["content_id"])
    assert len(rows) == 1
    snapshot = rows[0]
    assert snapshot.impressions == 5310
    assert snapshot.likes == 42
    assert snapshot.shares == 7
    assert snapshot.clicks == 88
    assert snapshot.engagement == 54
    assert snapshot.date == datetime.now(UTC).date()
    assert snapshot.extra["post_id"] == "1750000000000000001"
    assert snapshot.extra["source"] == "x_api_v2"


async def test_unreported_metric_is_null_not_zero(db, session_factory, http):
    """X v2 exposes no per-post reach — it must stay NULL, never a measured 0."""
    ids = await seed(session_factory)
    http.on(
        "api.x.com/2/tweets/",
        tweet_payload(likes=1, retweets=0, replies=0, quotes=0, impressions=10, clicks=0),
    )

    result = await fetch_content_metrics(db, ids["content_id"])
    await db.commit()

    assert "reach" in result["not_available"]
    assert result["metrics"]["reach"] is None

    snapshot = (await snapshot_rows(session_factory, ids["content_id"]))[0]
    assert snapshot.reach is None
    assert snapshot.followers_delta is None
    # A genuine measured zero is preserved as 0, not collapsed into NULL.
    assert snapshot.shares == 0
    assert snapshot.clicks == 0


async def test_get_content_analytics_marks_measured_and_missing(db, session_factory, http):
    ids = await seed(session_factory)
    http.on(
        "api.x.com/2/tweets/",
        tweet_payload(likes=5, retweets=1, replies=0, quotes=0, impressions=100, clicks=4),
    )
    await fetch_content_metrics(db, ids["content_id"])
    await db.commit()

    items = await get_content_analytics(db, ids["content_id"])
    assert len(items) == 1
    item = items[0]
    assert item["reach"] is None
    assert item["impressions"] == 100
    assert "reach" in item["not_available"]
    assert "impressions" in item["measured"]
    assert item["source"] == "x_api_v2"


# ---------------------------------------------------------------------------
# (b) An unavailable result persists NOTHING and returns the reason
# ---------------------------------------------------------------------------
async def test_unauthorized_platform_writes_no_snapshot(db, session_factory, http):
    ids = await seed(session_factory)
    http.on("api.x.com/2/tweets/", {"title": "Unauthorized"}, status_code=401)

    result = await fetch_content_metrics(db, ids["content_id"])
    await db.commit()

    assert result["status"] == "unavailable"
    assert "401" in result["reason"]
    assert result["http_status"] == 401
    assert await snapshot_rows(session_factory, ids["content_id"]) == []


async def test_unsupported_platform_writes_no_snapshot(db, session_factory):
    ids = await seed(session_factory, platform="tiktok")

    result = await fetch_content_metrics(db, ids["content_id"])
    await db.commit()

    assert result["status"] == "unavailable"
    assert "tiktok" in result["reason"]
    assert await snapshot_rows(session_factory, ids["content_id"]) == []


async def test_missing_platform_post_id_writes_no_snapshot(db, session_factory):
    ids = await seed(session_factory, post_id=None)

    result = await fetch_content_metrics(db, ids["content_id"])
    await db.commit()

    assert result["status"] == "unavailable"
    assert "post id" in result["reason"]
    assert await snapshot_rows(session_factory, ids["content_id"]) == []


# ---------------------------------------------------------------------------
# (c) No connected account -> clear error, nothing persisted
# ---------------------------------------------------------------------------
async def test_no_connected_account_returns_clear_reason(db, session_factory):
    ids = await seed(session_factory, connect_account=False)

    result = await fetch_content_metrics(db, ids["content_id"])
    await db.commit()

    assert result["status"] == "unavailable"
    assert result["reason"] == "No connected twitter account for this content's client"
    assert result["error"] == result["reason"]
    assert await snapshot_rows(session_factory, ids["content_id"]) == []


async def test_revoked_account_is_not_treated_as_connected(db, session_factory):
    ids = await seed(session_factory, account_status="revoked")

    result = await fetch_content_metrics(db, ids["content_id"])

    assert result["status"] == "unavailable"
    assert "No connected twitter account" in result["reason"]


async def test_account_without_token_returns_reconnect_reason(db, session_factory):
    ids = await seed(session_factory, access_token=None)

    result = await fetch_content_metrics(db, ids["content_id"])

    assert result["status"] == "unavailable"
    assert "reconnect" in result["reason"]
    assert await snapshot_rows(session_factory, ids["content_id"]) == []


async def test_unpublished_content_is_an_error(db, session_factory):
    ids = await seed(session_factory, content_status="draft")

    result = await fetch_content_metrics(db, ids["content_id"])

    assert result["status"] == "error"
    assert result["reason"] == "Content not published"


async def test_missing_content_is_an_error(db):
    result = await fetch_content_metrics(db, uuid_module.uuid4())
    assert result["status"] == "error"
    assert result["reason"] == "Content not found"


# ---------------------------------------------------------------------------
# (d) The daily refresh job selects the right rows
# ---------------------------------------------------------------------------
async def test_refresh_selects_only_recent_published_unmeasured(db, session_factory):
    now = datetime.now(UTC)

    recent = await seed(session_factory, published_at=now - timedelta(days=2))
    await seed(session_factory, published_at=now - timedelta(days=45))
    await seed(session_factory, content_status="draft", published_at=None)
    measured = await seed(session_factory, published_at=now - timedelta(days=3))

    async with session_factory() as session:
        account = (
            await session.execute(select(PlatformAccount).limit(1))
        ).scalar_one()
        session.add(
            AnalyticsSnapshot(
                platform_account_id=account.id,
                content_id=measured["content_id"],
                date=now.date(),
            )
        )
        await session.commit()

    selected = await select_content_for_metrics_refresh(db, now=now)

    assert selected == [recent["content_id"]]


async def test_refresh_published_metrics_records_available_and_reports_rest(
    db, session_factory, http
):
    now = datetime.now(UTC)
    good = await seed(session_factory, published_at=now - timedelta(days=1))
    await seed(
        session_factory,
        platform="tiktok",
        published_at=now - timedelta(days=1),
    )

    http.on(
        "api.x.com/2/tweets/",
        tweet_payload(likes=9, retweets=2, replies=1, quotes=0, impressions=300, clicks=11),
    )

    summary = await refresh_published_metrics(db, now=now)
    await db.commit()

    assert summary["selected"] == 2
    assert summary["recorded"] == 1
    assert len(summary["unavailable"]) == 1
    assert "tiktok" in summary["unavailable"][0]["reason"]

    rows = await snapshot_rows(session_factory, good["content_id"])
    assert len(rows) == 1
    assert rows[0].impressions == 300


async def test_refresh_is_idempotent_within_a_day(db, session_factory, http):
    now = datetime.now(UTC)
    ids = await seed(session_factory, published_at=now - timedelta(days=1))
    http.on(
        "api.x.com/2/tweets/",
        tweet_payload(likes=4, retweets=0, replies=0, quotes=0, impressions=50, clicks=1),
    )

    first = await refresh_published_metrics(db, now=now)
    await db.commit()
    second = await refresh_published_metrics(db, now=now)
    await db.commit()

    assert first["recorded"] == 1
    assert second["selected"] == 0
    assert len(await snapshot_rows(session_factory, ids["content_id"])) == 1
    assert len(http.calls) == 1


async def test_skip_if_fetched_today_returns_existing_snapshot(db, session_factory, http):
    ids = await seed(session_factory)
    http.on(
        "api.x.com/2/tweets/",
        tweet_payload(likes=2, retweets=0, replies=0, quotes=0, impressions=20, clicks=0),
    )

    await fetch_content_metrics(db, ids["content_id"])
    await db.commit()
    again = await fetch_content_metrics(db, ids["content_id"], skip_if_fetched_today=True)

    assert again["status"] == "skipped"
    assert again["latest"]["impressions"] == 20
    assert len(http.calls) == 1


# ---------------------------------------------------------------------------
# Scheduler wiring — one pass per UTC day, on the existing loop
# ---------------------------------------------------------------------------
async def test_scheduler_refresh_runs_once_per_day(session_factory, monkeypatch, http):
    from agency.services import scheduler as scheduler_mod

    now = datetime.now(UTC)
    ids = await seed(session_factory, published_at=now - timedelta(days=1))
    http.on(
        "api.x.com/2/tweets/",
        tweet_payload(likes=6, retweets=1, replies=0, quotes=0, impressions=77, clicks=2),
    )
    monkeypatch.setattr(scheduler_mod, "get_session_factory", lambda: session_factory)

    engine = scheduler_mod.SchedulerEngine()
    first = await engine.refresh_analytics(now=now)
    second = await engine.refresh_analytics(now=now)

    assert first["status"] == "completed"
    assert first["recorded"] == 1
    assert second["status"] == "skipped"
    assert len(await snapshot_rows(session_factory, ids["content_id"])) == 1

    # A new UTC day re-opens the window; the per-content guard still applies.
    tomorrow = now + timedelta(days=1)
    third = await engine.refresh_analytics(now=tomorrow)
    assert third["status"] == "completed"


async def test_scheduler_marks_the_day_by_utc_date(session_factory, monkeypatch):
    from agency.services import scheduler as scheduler_mod

    monkeypatch.setattr(scheduler_mod, "get_session_factory", lambda: session_factory)
    today_utc = datetime.now(UTC).date()
    engine = scheduler_mod.SchedulerEngine()
    engine._last_metrics_refresh_day = today_utc

    out = await engine.refresh_analytics(
        now=datetime.combine(today_utc, datetime.min.time(), tzinfo=UTC)
    )
    assert out["status"] == "skipped"
