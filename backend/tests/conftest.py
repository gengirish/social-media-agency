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


def auth_header_for(
    org_id: UUID | str, role: str = "owner", *, user_id: UUID | str | None = None
) -> dict[str, str]:
    """A local HS256 bearer token scoped to ``org_id`` (the dev/CI auth mode).

    ``user_id`` pins the ``sub`` claim, which routers resolve through
    ``get_current_user_id`` — needed by anything scoped per user (comments, notifications).

    **This mints a token and nothing else — it does not create a ``users`` row.**
    ``agency.permissions.require_cap`` reads the role from the database and fails
    closed when no active row matches both the token's ``sub`` and the request's
    org, so a caller built here **cannot pass a capability gate**, whatever the
    ``role`` argument says (the claim is informational; the row is authoritative).
    Use it only for routes with no ``require_cap`` dependency. For anything gated,
    use :func:`auth_for`, which persists the matching row.
    """
    from jose import jwt

    token = jwt.encode(
        {
            "sub": str(user_id or uuid4()),
            "email": f"user-{org_id}@test.com",
            "role": role,
            "org_id": str(org_id),
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


async def auth_for(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID | str,
    role: str = "owner",
    *,
    account_type: str | None = None,
    user_id: UUID | str | None = None,
) -> dict[str, str]:
    """A bearer token **backed by a real ``users`` row** — the one capability gates accept.

    ``require_cap`` resolves the caller by loading the ``users`` row matching both
    the token's ``sub`` and the request's ``org_id`` (and ``is_active``), then reads
    ``organization.account_type``. This factory creates exactly that: it persists a
    ``User`` with ``role`` whose id becomes the token's ``sub``, so the row and the
    token agree.

    Args:
        session_factory: the ``session_factory`` fixture.
        org_id: an org created by :func:`create_org`; the user is created inside it.
        role: one of ``owner`` / ``admin`` / ``member`` / ``viewer``. Also written to
            the token's (informational) ``role`` claim. Pass a *different* value than
            the row's to test staleness — use ``user_id`` + ``auth_header_for`` for that.
        account_type: when given, the org's ``account_type`` column is updated to it
            (``personal`` or ``business``) before the header is returned. ``None``
            leaves whatever :func:`create_org` set (``business`` by default).
        user_id: pin the user's id (and therefore the ``sub`` claim); defaults to a
            fresh uuid4. Use it when the test also needs the id — e.g. to assert on
            per-user rows, or to reuse the same caller across two headers.

    Returns:
        ``{"Authorization": "Bearer <jwt>"}``, ready to pass as ``headers=``.
    """
    uid = UUID(str(user_id)) if user_id is not None else uuid4()
    oid = UUID(str(org_id))

    await create_user_row(session_factory, oid, user_id=uid, role=role)
    if account_type is not None:
        await set_account_type(session_factory, oid, account_type)

    return auth_header_for(oid, role, user_id=uid)


async def set_account_type(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    account_type: str,
) -> None:
    """Flip an existing org between ``personal`` and ``business``.

    Separate from :func:`create_org` because the account shape is sometimes changed
    after the org and its rows already exist (the B2C → B2B flip).
    """
    from agency.models.tables import Organization

    async with session_factory() as session:
        org = await session.get(Organization, org_id)
        assert org is not None, f"no organization {org_id}"
        org.account_type = account_type
        await session.commit()


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
    session_factory: async_sessionmaker[AsyncSession],
    name: str = "Test Org",
    *,
    slug: str | None = None,
    account_type: str = "business",
) -> UUID:
    """An organization row.

    ``account_type`` defaults to ``'business'`` — not to the column's own
    ``'personal'`` default — because the existing suites assume team seats and
    multiple clients, which is the business shape. Pass ``'personal'`` explicitly
    to exercise the solo account.

    ``account_type`` does **not** change capabilities: ``PERSONAL_DENIED`` is
    empty (see ``permissions.py``), so a personal org's owner keeps
    ``team.manage`` and can invite — which is exactly what flips the org to
    ``'business'``. It affects UI affordances and that one-way flip, nothing else.
    """
    from agency.models.tables import Organization
    from agency.utils.slug import slugify

    org = Organization(
        id=uuid4(),
        name=name,
        account_type=account_type,
        # Unique per org so the portal's slug lookup resolves exactly one row.
        slug=slug if slug is not None else f"{slugify(name)}-{uuid4().hex[:6]}",
        settings={},
        is_active=True,
    )
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
    generations_used: int = 0,
    generations_limit: int | None = None,
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
        generations_used=generations_used,
        generations_limit=(
            plan["generations_limit"] if generations_limit is None else generations_limit
        ),
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


async def create_user_row(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    *,
    user_id: UUID | None = None,
    email: str | None = None,
    full_name: str = "Test User",
    role: str = "admin",
) -> UUID:
    from agency.models.tables import User

    uid = user_id or uuid4()
    row = User(
        id=uid,
        org_id=org_id,
        email=email or f"user-{uid}@test.com",
        password_hash="x",
        full_name=full_name,
        role=role,
        is_active=True,
    )
    await _persist(session_factory, row)
    return uid


async def create_platform_account(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    client_id: UUID,
    *,
    platform: str = "linkedin",
    status: str = "connected",
    account_handle: str = "acct",
) -> UUID:
    from agency.models.tables import PlatformAccount

    row = PlatformAccount(
        id=uuid4(),
        client_id=client_id,
        org_id=org_id,
        platform=platform,
        account_handle=account_handle,
        display_name=account_handle,
        access_token_enc="enc-token",
        status=status,
    )
    await _persist(session_factory, row)
    return row.id


async def create_notification_row(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    user_id: UUID,
    *,
    read: bool = False,
) -> UUID:
    from agency.models.tables import Notification

    row = Notification(
        id=uuid4(),
        user_id=user_id,
        org_id=org_id,
        type="info",
        title="Test notification",
        body="",
        data={},
        read=read,
    )
    await _persist(session_factory, row)
    return row.id


async def create_white_label(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    *,
    portal_enabled: bool = True,
    is_active: bool = True,
    company_name: str = "Portal Co",
) -> UUID:
    from agency.models.tables import WhiteLabel

    row = WhiteLabel(
        id=uuid4(),
        org_id=org_id,
        company_name=company_name,
        primary_color="#4f46e5",
        portal_enabled=portal_enabled,
        is_active=is_active,
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
    body: str = "Test body",
    hashtags: list[str] | None = None,
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
        body=body,
        hashtags=list(hashtags or []),
        metadata_={},
        media_urls=[],
        ai_generated=True,
        status=status,
    )
    await _persist(session_factory, row)
    return row.id
