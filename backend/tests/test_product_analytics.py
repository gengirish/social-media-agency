"""Product analytics — DB-free unit tests for the pure pieces.

Metric aggregations are SQL and are covered by the E2E suite against Postgres;
these cover the logic that guards data quality: what a browser may write, how
ids are coerced, and how request outcomes are counted.
"""

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import URL

from agency.middleware.request_metrics import _route_template
from agency.services import product_analytics as pa


def test_client_writable_excludes_server_authored_events():
    """A browser must not be able to inflate completion or failure counts."""
    assert pa.CAMPAIGN_COMPLETED not in pa.CLIENT_WRITABLE_EVENTS
    assert pa.CAMPAIGN_FAILED not in pa.CLIENT_WRITABLE_EVENTS
    assert pa.CAMPAIGN_CREATED not in pa.CLIENT_WRITABLE_EVENTS
    assert pa.AGENT_STEP_COMPLETED not in pa.CLIENT_WRITABLE_EVENTS
    assert pa.API_ERROR not in pa.CLIENT_WRITABLE_EVENTS
    assert pa.FEATURE_USED in pa.CLIENT_WRITABLE_EVENTS


def test_every_known_event_has_a_category():
    for name in pa.CLIENT_WRITABLE_EVENTS:
        assert name in pa.CATEGORY_BY_NAME


def test_as_uuid_coerces_strings_and_rejects_garbage():
    value = uuid4()
    assert pa._as_uuid(str(value)) == value
    assert pa._as_uuid(value) == value
    assert pa._as_uuid(None) is None
    assert pa._as_uuid("not-a-uuid") is None


def test_build_event_truncates_and_categorises():
    event = pa._build_event(
        name=pa.FEATURE_USED,
        org_id=str(uuid4()),
        session_id="s" * 200,
        path="/p" * 500,
        properties={"feature": "campaign-create"},
    )
    assert event.category == "feature"
    assert len(event.session_id) == 64
    assert len(event.path) == 500
    assert isinstance(event.org_id, UUID)


def test_agent_funnel_matches_graph_node_names():
    """The drop-off funnel is meaningless if it drifts from the real graph."""
    from agency.agents.graph import build_campaign_graph

    nodes = set(build_campaign_graph().nodes)
    assert set(pa.AGENT_FUNNEL_ORDER) <= nodes


def test_request_counters_produce_a_rate():
    pa._request_totals.clear()
    pa._request_errors.clear()

    for _ in range(8):
        pa.record_request("GET", "/api/v1/campaigns", 200)
    pa.record_request("GET", "/api/v1/campaigns", 500)
    pa.record_request("GET", "/api/v1/campaigns", 404)

    snapshot = pa.request_rate_snapshot()
    assert snapshot["total_requests"] == 10
    assert snapshot["total_errors"] == 2
    assert snapshot["error_rate"] == 0.2

    row = snapshot["by_endpoint"][0]
    assert row["endpoint"] == "/api/v1/campaigns"
    assert row["errors"] == 2

    pa._request_totals.clear()
    pa._request_errors.clear()


def test_request_rate_snapshot_is_empty_without_traffic():
    pa._request_totals.clear()
    pa._request_errors.clear()
    snapshot = pa.request_rate_snapshot()
    assert snapshot["total_requests"] == 0
    assert snapshot["error_rate"] is None


class _FakeRequest:
    """Minimal stand-in: _route_template only reads scope and url."""

    def __init__(self, path: str, route=None):
        self.scope = {"route": route} if route else {}
        self.url = URL(f"http://test{path}")


def test_route_template_masks_uuids_when_route_is_unmatched():
    request = _FakeRequest(f"/api/v1/campaigns/{uuid4()}/content")
    assert _route_template(request) == "/api/v1/campaigns/{id}/content"


def test_route_template_prefers_the_matched_route():
    class _Route:
        path = "/api/v1/campaigns/{campaign_id}"

    request = _FakeRequest(f"/api/v1/campaigns/{uuid4()}", route=_Route())
    assert _route_template(request) == "/api/v1/campaigns/{campaign_id}"


@pytest.mark.asyncio
async def test_event_ingest_requires_auth():
    from agency.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/events",
            json={"events": [{"name": "page_view", "path": "/campaigns"}]},
        )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_beta_metrics_requires_auth():
    from agency.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/beta-metrics")
    assert response.status_code in (401, 403)
