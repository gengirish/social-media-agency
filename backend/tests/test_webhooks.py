"""Outbound webhooks — persistence, tenant scoping, signing, and retries.

Runs against an in-memory SQLite database (the webhook tables carry SQLite
variants for exactly this reason) so the org-scoping assertions exercise real
SQL rather than a stub. All outbound HTTP goes through ``httpx.MockTransport``:
no socket is ever opened.
"""

import json
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agency.models.tables import Base, Webhook, WebhookDelivery
from agency.services import webhook_dispatcher as wd

API = "/api/v1/integrations/webhooks"


def auth_header_for(org_id: UUID, role: str = "admin") -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "email": f"user-{org_id}@test.com",
            "role": role,
            "org_id": str(org_id),
        },
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def session_factory(monkeypatch):
    """In-memory SQLite holding only the two webhook tables."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Webhook.__table__, WebhookDelivery.__table__],
        )

    factory = async_sessionmaker(engine, expire_on_commit=False)

    # The dispatcher opens its own sessions (the track_detached precedent).
    monkeypatch.setattr(wd, "get_session_factory", lambda: factory)
    # Keep retry tests fast; the backoff shape is asserted separately.
    monkeypatch.setattr(wd, "RETRY_BACKOFF_BASE_SECONDS", 0)

    yield factory
    await engine.dispose()


@pytest.fixture
async def api(session_factory):
    """HTTP client with ``get_db`` bound to the SQLite session factory."""
    from agency.dependencies import get_db
    from agency.main import app

    async def _override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


def mock_transport(handler):
    """Patch the dispatcher's client factory with a mocked transport."""

    def _build() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return _build


# ---------------------------------------------------------------------------
# Registration + persistence
# ---------------------------------------------------------------------------
async def test_register_persists_webhook_scoped_to_org(api, session_factory):
    org = uuid4()
    resp = await api.post(
        API,
        json={"url": "https://hooks.example.com/cf", "events": ["campaign.completed"]},
        headers=auth_header_for(org),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["url"] == "https://hooks.example.com/cf"
    assert body["events"] == ["campaign.completed"]
    assert body["is_active"] is True
    assert body["org_id"] == str(org)
    # The secret is returned exactly once, here.
    assert len(body["secret"]) == wd.SECRET_BYTES * 2

    # It is a database row, not process memory — it survives a restart.
    async with session_factory() as db:
        stored = await db.get(Webhook, UUID(body["id"]))
    assert stored is not None
    assert stored.org_id == org
    assert stored.secret == body["secret"]


async def test_register_rejects_unknown_event(api):
    resp = await api.post(
        API,
        json={"url": "https://hooks.example.com/cf", "events": ["campaign.exploded"]},
        headers=auth_header_for(uuid4()),
    )
    assert resp.status_code == 422


async def test_register_rejects_non_http_url(api):
    resp = await api.post(
        API,
        json={"url": "ftp://hooks.example.com/cf", "events": []},
        headers=auth_header_for(uuid4()),
    )
    assert resp.status_code == 422


async def test_empty_events_subscribes_to_everything(api):
    resp = await api.post(
        API, json={"url": "https://hooks.example.com/cf"}, headers=auth_header_for(uuid4())
    )
    assert resp.status_code == 201
    assert sorted(resp.json()["events"]) == sorted(wd.SUPPORTED_EVENTS)


async def test_unauthenticated_registration_rejected(api):
    resp = await api.post(API, json={"url": "https://hooks.example.com/cf"})
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------
@pytest.fixture
async def two_orgs(api):
    org_a, org_b = uuid4(), uuid4()
    headers_a, headers_b = auth_header_for(org_a), auth_header_for(org_b)

    resp_a = await api.post(
        API, json={"url": "https://a.example.com/hook"}, headers=headers_a
    )
    resp_b = await api.post(
        API, json={"url": "https://b.example.com/hook"}, headers=headers_b
    )
    assert resp_a.status_code == 201 and resp_b.status_code == 201

    return {
        "org_a": org_a,
        "org_b": org_b,
        "headers_a": headers_a,
        "headers_b": headers_b,
        "hook_a": resp_a.json(),
        "hook_b": resp_b.json(),
    }


async def test_list_only_returns_own_orgs_webhooks(api, two_orgs):
    resp = await api.get(API, headers=two_orgs["headers_a"])
    assert resp.status_code == 200
    data = resp.json()

    ids = {item["id"] for item in data["items"]}
    assert two_orgs["hook_a"]["id"] in ids
    assert two_orgs["hook_b"]["id"] not in ids
    assert data["total"] == 1


async def test_secret_is_never_echoed_by_list(api, two_orgs):
    resp = await api.get(API, headers=two_orgs["headers_a"])
    payload = resp.json()

    for item in payload["items"]:
        assert "secret" not in item
    # Belt and braces: the plaintext must not appear anywhere in the response.
    assert two_orgs["hook_a"]["secret"] not in resp.text


async def test_cannot_delete_other_orgs_webhook(api, two_orgs, session_factory):
    resp = await api.delete(f"{API}/{two_orgs['hook_b']['id']}", headers=two_orgs["headers_a"])
    assert resp.status_code == 404

    # And B's webhook is still there.
    async with session_factory() as db:
        survivor = await db.get(Webhook, UUID(two_orgs["hook_b"]["id"]))
    assert survivor is not None

    # B can delete its own.
    resp = await api.delete(f"{API}/{two_orgs['hook_b']['id']}", headers=two_orgs["headers_b"])
    assert resp.status_code == 200


async def test_cannot_read_other_orgs_deliveries(api, two_orgs):
    resp = await api.get(
        f"{API}/{two_orgs['hook_b']['id']}/deliveries", headers=two_orgs["headers_a"]
    )
    assert resp.status_code == 404


async def test_dispatch_only_reaches_the_owning_org(api, two_orgs, monkeypatch):
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        return httpx.Response(200)

    monkeypatch.setattr(wd, "_build_client", mock_transport(handler))

    await wd.dispatch_webhook(two_orgs["org_a"], wd.EVENT_CAMPAIGN_COMPLETED, {"id": "1"})

    assert hits == ["https://a.example.com/hook"]


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------
async def test_signature_verifies_against_the_bytes_actually_sent(api, monkeypatch):
    org = uuid4()
    created = await api.post(
        API,
        json={"url": "https://hooks.example.com/cf", "events": ["campaign.completed"]},
        headers=auth_header_for(org),
    )
    secret = created.json()["secret"]

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        seen["signature"] = request.headers[wd.SIGNATURE_HEADER]
        seen["content_type"] = request.headers["content-type"]
        return httpx.Response(200)

    monkeypatch.setattr(wd, "_build_client", mock_transport(handler))

    results = await wd.dispatch_webhook(
        org, wd.EVENT_CAMPAIGN_COMPLETED, {"campaign_id": "abc", "name": "Launch"}
    )
    assert results[0]["status"] == "delivered"

    body = seen["body"]
    assert isinstance(body, bytes)
    # A receiver recomputes the HMAC over the raw bytes it received.
    assert wd.verify_signature(secret, body, str(seen["signature"]))
    assert seen["content_type"] == "application/json"

    decoded = json.loads(body)
    assert decoded["event"] == "campaign.completed"
    assert decoded["data"] == {"campaign_id": "abc", "name": "Launch"}


async def test_signature_fails_if_the_body_is_reserialised(api, monkeypatch):
    """The classic bug: sign one serialisation, send another."""
    org = uuid4()
    created = await api.post(
        API, json={"url": "https://hooks.example.com/cf"}, headers=auth_header_for(org)
    )
    secret = created.json()["secret"]

    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["signature"] = request.headers[wd.SIGNATURE_HEADER].encode()
        return httpx.Response(200)

    monkeypatch.setattr(wd, "_build_client", mock_transport(handler))
    await wd.dispatch_webhook(org, wd.EVENT_CONTENT_APPROVED, {"content_id": "z"})

    signature = captured["signature"].decode()
    # httpx's default `json=` serialisation differs (spaces, key order) — and so
    # would the signature if the dispatcher had signed that instead.
    reserialised = json.dumps(json.loads(captured["body"])).encode()
    assert reserialised != captured["body"]
    assert not wd.verify_signature(secret, reserialised, signature)
    assert wd.verify_signature(secret, captured["body"], signature)


async def test_wrong_secret_does_not_verify():
    body = wd.serialise_event("campaign.completed", {"a": 1}, "2026-01-01T00:00:00+00:00")
    signature = wd.sign_body("secret-one", body)
    assert not wd.verify_signature("secret-two", body, signature)


async def test_generated_secrets_are_unique():
    assert len({wd.generate_secret() for _ in range(50)}) == 50


# ---------------------------------------------------------------------------
# Retries + failure containment
# ---------------------------------------------------------------------------
async def test_failing_endpoint_retries_logs_and_never_raises(api, session_factory, monkeypatch):
    org = uuid4()
    created = await api.post(
        API, json={"url": "https://down.example.com/hook"}, headers=auth_header_for(org)
    )
    webhook_id = UUID(created.json()["id"])

    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(500, text="boom")

    monkeypatch.setattr(wd, "_build_client", mock_transport(handler))

    # Must return normally — a broken customer endpoint cannot break a campaign.
    results = await wd.dispatch_webhook(org, wd.EVENT_CAMPAIGN_COMPLETED, {"id": "1"})

    assert len(attempts) == wd.MAX_ATTEMPTS
    assert results[0]["status"] == "failed"
    assert results[0]["attempts"] == wd.MAX_ATTEMPTS

    async with session_factory() as db:
        rows = await wd.list_deliveries(db, org, webhook_id)

    assert len(rows) == wd.MAX_ATTEMPTS
    assert sorted(r.attempt for r in rows) == [1, 2, 3]
    assert {r.status for r in rows} == {"failed"}
    assert {r.response_code for r in rows} == {500}
    assert all(r.error == "HTTP 500" for r in rows)


async def test_connection_error_is_contained(api, session_factory, monkeypatch):
    org = uuid4()
    created = await api.post(
        API, json={"url": "https://unreachable.example.com/hook"}, headers=auth_header_for(org)
    )
    webhook_id = UUID(created.json()["id"])

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(wd, "_build_client", mock_transport(handler))

    results = await wd.dispatch_webhook(org, wd.EVENT_CONTENT_APPROVED, {"id": "1"})
    assert results[0]["status"] == "failed"

    async with session_factory() as db:
        rows = await wd.list_deliveries(db, org, webhook_id)
    assert len(rows) == wd.MAX_ATTEMPTS
    assert all(r.response_code is None for r in rows)
    assert all("ConnectError" in (r.error or "") for r in rows)


async def test_success_stops_retrying_and_logs_one_row(api, session_factory, monkeypatch):
    org = uuid4()
    created = await api.post(
        API, json={"url": "https://ok.example.com/hook"}, headers=auth_header_for(org)
    )
    webhook_id = UUID(created.json()["id"])

    monkeypatch.setattr(
        wd, "_build_client", mock_transport(lambda request: httpx.Response(204))
    )

    results = await wd.dispatch_webhook(org, wd.EVENT_CAMPAIGN_COMPLETED, {"id": "1"})
    assert results[0] == {
        "webhook_id": str(webhook_id),
        "event_type": wd.EVENT_CAMPAIGN_COMPLETED,
        "status": "delivered",
        "attempts": 1,
        "response_code": 204,
    }

    async with session_factory() as db:
        rows = await wd.list_deliveries(db, org, webhook_id)
    assert len(rows) == 1
    assert rows[0].status == "delivered"


async def test_inactive_and_unsubscribed_webhooks_are_skipped(api, session_factory, monkeypatch):
    org = uuid4()
    subscribed = await api.post(
        API,
        json={"url": "https://yes.example.com/hook", "events": ["campaign.completed"]},
        headers=auth_header_for(org),
    )
    await api.post(
        API,
        json={"url": "https://no.example.com/hook", "events": ["content.approved"]},
        headers=auth_header_for(org),
    )

    # Deactivate the subscribed one and nothing at all should be delivered.
    hits: list[str] = []
    monkeypatch.setattr(
        wd,
        "_build_client",
        mock_transport(lambda request: (hits.append(str(request.url)), httpx.Response(200))[1]),
    )

    await wd.dispatch_webhook(org, wd.EVENT_CAMPAIGN_COMPLETED, {"id": "1"})
    assert hits == ["https://yes.example.com/hook"]

    async with session_factory() as db:
        hook = await db.get(Webhook, UUID(subscribed.json()["id"]))
        hook.is_active = False
        await db.commit()

    hits.clear()
    await wd.dispatch_webhook(org, wd.EVENT_CAMPAIGN_COMPLETED, {"id": "2"})
    assert hits == []


async def test_dispatch_with_no_registrations_is_a_noop(api, monkeypatch):
    called: list[int] = []
    monkeypatch.setattr(
        wd,
        "_build_client",
        mock_transport(lambda request: (called.append(1), httpx.Response(200))[1]),
    )
    assert await wd.dispatch_webhook(uuid4(), wd.EVENT_CAMPAIGN_COMPLETED, {}) == []
    assert called == []


async def test_dispatch_survives_a_dead_database(monkeypatch):
    """If the webhook lookup itself fails, the caller still gets a value."""

    def exploding_factory():
        raise RuntimeError("connection pool exhausted")

    monkeypatch.setattr(wd, "get_session_factory", exploding_factory)
    assert await wd.dispatch_webhook(uuid4(), wd.EVENT_CAMPAIGN_COMPLETED, {}) == []


async def test_dispatch_ignores_a_malformed_org_id():
    assert await wd.dispatch_webhook("not-a-uuid", wd.EVENT_CAMPAIGN_COMPLETED, {}) == []


# ---------------------------------------------------------------------------
# Delivery audit endpoint
# ---------------------------------------------------------------------------
async def test_deliveries_endpoint_returns_the_attempt_log(api, monkeypatch):
    org = uuid4()
    created = await api.post(
        API, json={"url": "https://down.example.com/hook"}, headers=auth_header_for(org)
    )
    webhook_id = created.json()["id"]

    monkeypatch.setattr(
        wd, "_build_client", mock_transport(lambda request: httpx.Response(503))
    )
    await wd.dispatch_webhook(org, wd.EVENT_CAMPAIGN_COMPLETED, {"id": "1"})

    resp = await api.get(f"{API}/{webhook_id}/deliveries", headers=auth_header_for(org))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == wd.MAX_ATTEMPTS
    assert {item["response_code"] for item in data["items"]} == {503}
    assert "secret" not in resp.text
