"""services/web_search.py — request shape, normalization, and the unavailable contract.

The request-shape tests are the point of this file. Exa's own guidance is that
over-decorating the recommended request is the most common integration mistake,
so the payload is asserted field by field: anything that appears without a
deliberate reason should fail here rather than quietly costing quality.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from agency.services import web_search


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Capture the payload sent to Exa and return a canned body."""
    seen: dict[str, Any] = {}

    async def _fake_search(api_key: str, payload: dict[str, Any], *, label: str = "", **_: Any):
        seen["api_key"] = api_key
        seen["payload"] = payload
        seen["label"] = label
        return seen.get("body", {"results": []})

    monkeypatch.setattr(web_search.exa_client, "search", _fake_search)
    monkeypatch.setattr(web_search.exa_client, "get_api_key", lambda: "test-key")
    return seen


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------
async def test_sends_the_recommended_request_and_nothing_else(captured):
    await web_search.gather_sources("latest developments in LLMs")

    payload = captured["payload"]
    assert payload["query"] == "latest developments in LLMs"
    assert payload["type"] == "auto"
    assert payload["contents"] == {"highlights": True}
    # numResults is a deliberate budget; everything else must be absent.
    assert set(payload) == {"query", "type", "contents", "numResults"}


@pytest.mark.parametrize(
    "forbidden",
    [
        "category",
        "includeDomains",
        "excludeDomains",
        "startPublishedDate",
        "maxAgeHours",
        "summary",
        "text",
    ],
)
async def test_does_not_decorate_the_request(captured, forbidden: str):
    """Each of these needs an explicit task requirement; none is one by default."""
    await web_search.gather_sources("anything")
    assert forbidden not in captured["payload"]


async def test_highlights_live_inside_contents_not_at_top_level(captured):
    """On /search, content controls are nested. Top-level `highlights` is ignored by Exa."""
    await web_search.gather_sources("anything")
    assert "highlights" not in captured["payload"]
    assert captured["payload"]["contents"]["highlights"] is True


async def test_published_after_is_sent_only_when_asked(captured):
    await web_search.gather_sources("q", published_after=datetime(2026, 1, 2, tzinfo=UTC))
    assert captured["payload"]["startPublishedDate"] == "2026-01-02T00:00:00.000Z"


async def test_limit_is_clamped(captured):
    await web_search.gather_sources("q", limit=9999)
    assert captured["payload"]["numResults"] == web_search.MAX_RESULTS

    await web_search.gather_sources("q", limit=0)
    assert captured["payload"]["numResults"] == 1


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
async def test_normalizes_results(captured):
    captured["body"] = {
        "results": [
            {
                "title": "  Exa ships something  ",
                "url": "https://www.example.com/post/",
                "publishedDate": "2026-09-01T10:00:00Z",
                "highlights": ["  a real excerpt  ", "", 42, "another"],
            }
        ]
    }
    out = await web_search.gather_sources("q")

    assert out["status"] == "ok"
    assert out["provenance"] == "exa_search"
    [source] = out["sources"]
    assert source["title"] == "Exa ships something"
    assert source["publisher"] == "example.com"
    assert source["published_at"] == "2026-09-01T10:00:00+00:00"
    # Blanks and non-strings dropped; real excerpts kept in order.
    assert source["highlights"] == ["a real excerpt", "another"]


async def test_drops_results_without_a_citable_url(captured):
    captured["body"] = {
        "results": [
            {"title": "no url"},
            {"title": "junk url", "url": "not-a-url"},
            {"title": "good", "url": "https://example.com/a"},
        ]
    }
    out = await web_search.gather_sources("q")
    assert [s["title"] for s in out["sources"]] == ["good"]


async def test_missing_title_falls_back_to_the_url(captured):
    captured["body"] = {"results": [{"url": "https://example.com/a"}]}
    out = await web_search.gather_sources("q")
    assert out["sources"][0]["title"] == "https://example.com/a"


async def test_no_results_is_ok_not_unavailable(captured):
    """An empty web is a real answer. Callers must tell it apart from a failure."""
    captured["body"] = {"results": []}
    out = await web_search.gather_sources("q")
    assert out["status"] == "ok"
    assert out["sources"] == []


# ---------------------------------------------------------------------------
# The unavailable contract — never invented content
# ---------------------------------------------------------------------------
async def test_missing_key_is_unavailable_with_setup_hint(monkeypatch):
    monkeypatch.setattr(web_search.exa_client, "get_api_key", lambda: "")
    out = await web_search.gather_sources("q")
    assert out["status"] == "unavailable"
    assert "EXA_API_KEY" in out["reason"]
    assert "sources" not in out


async def test_blank_query_is_unavailable(captured):
    out = await web_search.gather_sources("   ")
    assert out["status"] == "unavailable"
    assert "payload" not in captured  # never called Exa


async def test_http_error_becomes_unavailable(monkeypatch):
    monkeypatch.setattr(web_search.exa_client, "get_api_key", lambda: "k")

    async def _boom(*_a: Any, **_k: Any):
        raise httpx.HTTPStatusError(
            "401", request=httpx.Request("POST", "https://api.exa.ai/search"),
            response=httpx.Response(401),
        )

    monkeypatch.setattr(web_search.exa_client, "search", _boom)
    out = await web_search.gather_sources("q")
    assert out["status"] == "unavailable"
    assert "key" in out["reason"].lower()


async def test_network_error_becomes_unavailable(monkeypatch):
    monkeypatch.setattr(web_search.exa_client, "get_api_key", lambda: "k")

    async def _boom(*_a: Any, **_k: Any):
        raise httpx.ConnectError("dns")

    monkeypatch.setattr(web_search.exa_client, "search", _boom)
    out = await web_search.gather_sources("q")
    assert out["status"] == "unavailable"


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------
async def test_format_for_prompt_numbers_sources_with_urls(captured):
    captured["body"] = {
        "results": [
            {
                "title": "A",
                "url": "https://example.com/a",
                "publishedDate": "2026-09-01T00:00:00Z",
                "highlights": ["excerpt one"],
            }
        ]
    }
    text = web_search.format_for_prompt(await web_search.gather_sources("q"))
    assert "[1] A" in text
    assert "https://example.com/a" in text
    assert "> excerpt one" in text
    assert "example.com" in text


def test_format_for_prompt_states_absence_rather_than_going_blank():
    """A blank section reads as 'nothing to say'; a stated absence discourages invention."""
    unavailable = web_search.format_for_prompt({"status": "unavailable", "reason": "no key"})
    assert "NO WEB SOURCES AVAILABLE" in unavailable
    assert "Do not invent" in unavailable

    empty = web_search.format_for_prompt({"status": "ok", "query": "q", "sources": []})
    assert "NO WEB SOURCES FOUND" in empty
    assert "Do not invent" in empty
