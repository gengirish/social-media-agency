"""Shared fixtures + row factories for the backend suite.

Everything here runs against a throwaway SQLite database so the billing, quota
and tenancy suites exercise **real SQL** — real ``WHERE org_id = ...`` clauses,
real rows — rather than stubs. A tenant-isolation test that never touches a
database can only ever pass vacuously.

``models/tables.py`` already ships a ``PortableUUID``/``PortableTextArray``
trick: a Postgres-native type carrying a SQLite variant, so the webhook tables
can be created in-memory. The rest of the schema still uses bare ``UUID``,
``JSONB`` and ``ARRAY(Text)``, none of which SQLite can render.
:func:`_install_sqlite_variants` applies exactly the same ``with_variant``
treatment to those columns from the test harness instead of the model module —
Postgres behaviour is untouched (a variant only ever fires for its own
dialect), and ``src/agency`` stays unmodified.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON as SA_JSON
from sqlalchemy import Uuid as GenericUuid
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.types import TypeEngine

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/campaignforge_test"
)

JWT_SECRET = "test-secret"

# Modules that bound ``get_session_factory`` at import time. Services which open
# their own session (the ``track_detached`` precedent) resolve it through their
# own module global, so each one has to be redirected at the test database.
_SESSION_FACTORY_CONSUMERS = (
    "agency.models.database",
    "agency.dependencies",
    "agency.middleware.api_key_auth",
    "agency.routers.campaigns",
    "agency.services.product_analytics",
    "agency.services.scheduler",
    "agency.services.webhook_dispatcher",
)

_variants_installed = False


def _sqlite_variant(type_: TypeEngine[Any]) -> TypeEngine[Any] | None:
    """Return the SQLite stand-in for a Postgres-only type, or ``None``."""
    if "sqlite" in getattr(type_, "_variant_mapping", {}):
        return None  # already portable (PortableUUID / PortableTextArray)
    if isinstance(type_, JSONB | PG_ARRAY):
        return SA_JSON()
    if isinstance(type_, PG_UUID):
        return GenericUuid(as_uuid=True)
    return None


def _install_sqlite_variants() -> None:
    """Attach SQLite variants to every Postgres-only column type, once."""
    global _variants_installed
    if _variants_installed:
        return

    from agency.models.tables import Base

    for table in Base.metadata.tables.values():
        for column in table.columns:
            variant = _sqlite_variant(column.type)
            if variant is not None:
                column.type = column.type.with_variant(variant, "sqlite")
    _variants_installed = True


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db_engine(tmp_path: Any) -> AsyncIterator[Engine]:
    """A fresh, file-backed SQLite database with the full schema."""
    _install_sqlite_variants()
    from agency.models.tables import Base

    url = f"sqlite+aiosqlite:///{(tmp_path / 'campaignforge_test.db').as_posix()}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(
    db_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> async_sessionmaker[AsyncSession]:
    """Session factory for the test database, wired into the app's globals."""
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        db_engine, expire_on_commit=False
    )

    for module_path in _SESSION_FACTORY_CONSUMERS:
        module = importlib.import_module(module_path)
        monkeypatch.setattr(module, "get_session_factory", lambda: factory)

    return factory


@pytest.fixture
async def db(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """A plain session on the test database, for service-level tests."""
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """HTTP client with ``get_db`` bound to the test database."""
    from agency.dependencies import get_db
    from agency.main import app

    async def _override_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


def auth_header_for(org_id: UUID | str, role: str = "admin") -> dict[str, str]:
    """A local HS256 bearer token scoped to ``org_id`` (the dev/CI auth mode)."""
    from jose import jwt

    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "email": f"user-{org_id}@test.com",
            "role": role,
            "org_id": str(org_id),
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return auth_header_for("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


# ---------------------------------------------------------------------------
# Row factories — each commits in its own session so the row is visible to the
# request under test, and returns the primary key.
# ---------------------------------------------------------------------------
async def _persist(factory: async_sessionmaker[AsyncSession], row: Any) -> None:
    async with factory() as session:
        session.add(row)
        await session.commit()


async def create_org(
    session_factory: async_sessionmaker[AsyncSession], name: str = "Test Org"
) -> UUID:
    from agency.models.tables import Organization

    org = Organization(id=uuid4(), name=name, settings={}, is_active=True)
    await _persist(session_factory, org)
    return org.id


async def create_subscription(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    *,
    plan_tier: str = "free",
    clients_limit: int | None = None,
    posts_limit: int | None = None,
    posts_used: int = 0,
    status: str = "active",
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
) -> UUID:
    from agency.models.tables import Subscription
    from agency.services.billing import PLAN_CONFIG

    plan = PLAN_CONFIG.get(plan_tier, PLAN_CONFIG["free"])
    sub = Subscription(
        id=uuid4(),
        org_id=org_id,
        plan_tier=plan_tier,
        clients_limit=plan["clients_limit"] if clients_limit is None else clients_limit,
        posts_limit=plan["posts_limit"] if posts_limit is None else posts_limit,
        posts_used=posts_used,
        status=status,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
    )
    await _persist(session_factory, sub)
    return sub.id


async def create_client_row(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    brand_name: str = "Test Brand",
    *,
    industry: str = "saas",
) -> UUID:
    from agency.models.tables import Client

    row = Client(
        id=uuid4(),
        org_id=org_id,
        brand_name=brand_name,
        industry=industry,
        description="",
        settings={},
        is_active=True,
    )
    await _persist(session_factory, row)
    return row.id


async def create_campaign_row(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    client_id: UUID,
    name: str = "Test Campaign",
    *,
    status: str = "planning",
    channels: list[str] | None = None,
) -> UUID:
    from agency.models.tables import Campaign

    today = date.today()
    row = Campaign(
        id=uuid4(),
        org_id=org_id,
        client_id=client_id,
        name=name,
        objective="",
        channels=list(channels or ["linkedin"]),
        start_date=today,
        end_date=today,
        budget={},
        agent_plan={},
        status=status,
    )
    await _persist(session_factory, row)
    return row.id


async def create_content_row(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    client_id: UUID,
    campaign_id: UUID | None = None,
    *,
    platform: str = "linkedin",
    status: str = "draft",
) -> UUID:
    from agency.models.tables import ContentPiece

    row = ContentPiece(
        id=uuid4(),
        org_id=org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        content_type="social_post",
        platform=platform,
        title="Test piece",
        body="Test body",
        hashtags=[],
        metadata_={},
        media_urls=[],
        ai_generated=True,
        status=status,
    )
    await _persist(session_factory, row)
    return row.id
