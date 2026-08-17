"""Trend intelligence must come from Exa or say it is unavailable — never invented.

All HTTP is mocked; these tests never touch the network.
"""

import httpx
import pytest

from agency.config import get_settings
from agency.services import trends


@pytest.fixture
def exa_env(monkeypatch):
    """Reset the cached settings around each test and expose an EXA_API_KEY setter."""
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    get_settings.cache_clear()

    def set_key(value: str) -> None:
        monkeypatch.setenv("EXA_API_KEY", value)
        get_settings.cache_clear()

    yield set_key
    get_settings.cache_clear()


@pytest.fixture
def exa_calls(monkeypatch):
    """Record every outbound Exa POST and drive the response from a queue."""
    calls: list[dict] = []
    responses: list = []

    async def fake_post(self, url, *, json=None, headers=None, **kwargs):
        calls.append({"url": url, "json": json, "headers": headers})
        if not responses:
            raise AssertionError("unexpected outbound call")
        result = responses[0] if len(responses) == 1 else responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    # Keep retry backoff from actually sleeping.
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(trends.asyncio, "sleep", no_sleep)

    def queue(*items):
        responses.extend(items)

    queue.calls = calls  # type: ignore[attr-defined]
    return queue


def _response(status: int, body: dict | None = None) -> httpx.Response:
    request = httpx.Request("POST", trends.EXA_SEARCH_URL)
    return httpx.Response(status, json=body if body is not None else {}, request=request)


EXA_BODY = {
    "requestId": "abc123",
    "results": [
        {
            "title": "LinkedIn creators lean into long-form video",
            "url": "https://www.example-news.com/linkedin-video",
            "publishedDate": "2026-08-10T00:00:00.000Z",
            "score": 0.42,
        },
        {
            "title": "B2B buyers shift research to social feeds",
            "url": "https://another-site.io/b2b-social",
            "publishedDate": None,
            "score": None,
        },
        # Unusable — no title; must be dropped, not padded with a placeholder.
        {"title": "", "url": "https://example.com/empty"},
    ],
}


# --- (a) key present + mocked Exa response ---


async def test_key_present_maps_exa_results_to_topics(exa_env, exa_calls):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))

    result = await trends.get_trending_topics("linkedin")

    assert result["status"] == "ok"
    assert result["source"] == "exa_search"
    assert result["platform"] == "linkedin"

    items = result["items"]
    assert len(items) == 2  # the title-less result is dropped
    assert items[0]["topic"] == "LinkedIn creators lean into long-form video"
    assert items[0]["url"] == "https://www.example-news.com/linkedin-video"
    assert items[0]["source"] == "example-news.com"
    assert items[0]["platform"] == "linkedin"
    assert items[0]["relevance_score"] == 0.42
    assert items[0]["provenance"] == "exa_search"
    assert isinstance(items[0]["recency_days"], int)

    # A result without a published date gets no derived recency — not a guess.
    assert items[1]["recency_days"] is None
    assert items[1]["published_date"] is None
    assert items[1]["relevance_score"] is None


async def test_volume_and_category_are_declared_missing_not_invented(exa_env, exa_calls):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))

    result = await trends.get_trending_topics("twitter")

    assert result["fields_not_provided"] == ["volume", "category"]
    for item in result["items"]:
        assert "volume" not in item
        assert "category" not in item


async def test_query_and_auth_header_are_sent_to_exa(exa_env, exa_calls):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))

    await trends.get_trending_topics("instagram")

    call = exa_calls.calls[0]
    assert call["url"] == "https://api.exa.ai/search"
    assert call["headers"]["x-api-key"] == "test-exa-key"
    assert "Instagram" in call["json"]["query"]
    assert call["json"]["numResults"] == trends._RESULT_LIMIT


async def test_query_varies_by_platform(exa_env, exa_calls):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY), _response(200, EXA_BODY))

    await trends.get_trending_topics("twitter")
    await trends.get_trending_topics("facebook")

    first, second = exa_calls.calls[0]["json"]["query"], exa_calls.calls[1]["json"]["query"]
    assert first != second
    assert "X (Twitter)" in first
    assert "Facebook" in second


# --- (b) key blank ---


async def test_blank_key_returns_unavailable_and_makes_no_call(exa_env, exa_calls):
    result = await trends.get_trending_topics("linkedin")

    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert "EXA_API_KEY" in result["reason"]
    assert "exa.ai" in result["reason"]
    assert exa_calls.calls == []  # no outbound request attempted


async def test_blank_key_unavailable_for_all_platforms_view(exa_env, exa_calls):
    result = await trends.get_trending_topics(None)

    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert exa_calls.calls == []


# --- (c) Exa errors ---


async def test_auth_error_returns_unavailable_with_setup_hint(exa_env, exa_calls):
    exa_env("bad-key")
    exa_calls(_response(401))

    result = await trends.get_trending_topics("twitter")

    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert result["http_status"] == 401
    assert "EXA_API_KEY" in result["reason"]
    assert len(exa_calls.calls) == 1  # 4xx is permanent, not retried


async def test_server_error_is_retried_then_reported_unavailable(exa_env, exa_calls):
    exa_env("test-exa-key")
    exa_calls(_response(503))

    result = await trends.get_trending_topics("linkedin")

    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert result["http_status"] == 503
    assert len(exa_calls.calls) == trends._MAX_RETRIES + 1


async def test_transient_network_error_recovers_on_retry(exa_env, exa_calls):
    exa_env("test-exa-key")
    exa_calls(httpx.ConnectError("boom"), _response(200, EXA_BODY))

    result = await trends.get_trending_topics("linkedin")

    assert result["status"] == "ok"
    assert len(result["items"]) == 2
    assert len(exa_calls.calls) == 2


async def test_network_failure_returns_unavailable_not_fabricated_topics(exa_env, exa_calls):
    exa_env("test-exa-key")
    exa_calls(httpx.ConnectError("dns down"))

    result = await trends.get_trending_topics("facebook")

    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert "request failed" in result["reason"]


async def test_empty_exa_results_are_reported_not_padded(exa_env, exa_calls):
    exa_env("test-exa-key")
    exa_calls(_response(200, {"results": []}))

    result = await trends.get_trending_topics("twitter")

    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert "no usable results" in result["reason"]


async def test_unsupported_platform_is_rejected_without_a_call(exa_env, exa_calls):
    exa_env("test-exa-key")

    result = await trends.get_trending_topics("myspace")

    assert result["status"] == "unavailable"
    assert "Unsupported platform" in result["reason"]
    assert exa_calls.calls == []


# --- no hardcoded data may reappear ---


def _contains_topic_record(value) -> bool:
    """True if the value is (or nests) a dict that looks like a canned trend row."""
    if isinstance(value, dict):
        if "topic" in value:
            return True
        return any(_contains_topic_record(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_topic_record(v) for v in value)
    return False


def test_module_exposes_no_hardcoded_trend_table():
    """The deleted PLATFORM_TRENDS dict must not come back in any shape."""
    assert not hasattr(trends, "PLATFORM_TRENDS")
    for name in dir(trends):
        if name.startswith("__"):
            continue
        assert not _contains_topic_record(getattr(trends, name)), (
            f"trends.{name} holds hardcoded topic data"
        )
