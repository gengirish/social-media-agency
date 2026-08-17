"""Competitive intel must be retrieved, cited and dated — or reported unavailable.

Every HTTP call and every LLM call is mocked; these tests never touch the network.
The load-bearing assertion is (b): a claim the model invents, with a URL that was
never retrieved, must be absent from the output.
"""

import json
from uuid import uuid4

import httpx
import pytest

from agency.agents import competitive_intel
from agency.config import get_settings
from agency.services import exa_client

# --------------------------------------------------------------------------
# fixtures (self-contained — this module does not rely on conftest.py)
# --------------------------------------------------------------------------


@pytest.fixture
def exa_env(monkeypatch):
    """Reset cached settings around each test and expose an EXA_API_KEY setter."""
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

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(exa_client.asyncio, "sleep", no_sleep)

    def queue(*items):
        responses.extend(items)

    queue.calls = calls  # type: ignore[attr-defined]
    return queue


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the worker LLM with a spy; ``.invocations`` proves whether it ran."""
    state = {"payload": "{}", "invocations": 0, "prompts": []}

    class _FakeLLM:
        async def ainvoke(self, prompt):
            state["invocations"] += 1
            state["prompts"].append(prompt)
            payload = state["payload"]
            if isinstance(payload, Exception):
                raise payload
            return _FakeResponse(payload)

    monkeypatch.setattr(competitive_intel, "get_worker_llm", lambda *a, **k: _FakeLLM())
    return state


def _response(status: int, body: dict | None = None) -> httpx.Response:
    request = httpx.Request("POST", exa_client.EXA_SEARCH_URL)
    return httpx.Response(status, json=body if body is not None else {}, request=request)


# --------------------------------------------------------------------------
# canned Exa material
# --------------------------------------------------------------------------

URL_A = "https://www.acme-news.com/acme-launches-pro-tier"
URL_B = "https://blog.acme.com/2026/positioning-update"

EXA_BODY = {
    "results": [
        {
            "title": "Acme launches a Pro tier aimed at agencies",
            "url": URL_A,
            "publishedDate": "2026-07-02T00:00:00.000Z",
            "text": "Acme announced a Pro tier priced for mid-size agencies.",
        },
        {
            "title": "Acme repositions around speed",
            "url": URL_B,
            "publishedDate": None,
            "text": "Acme's new site copy leads with turnaround time.",
        },
        # Unusable: no URL. Must be dropped, never padded with a placeholder.
        {"title": "Untraceable rumour", "url": "", "text": "something"},
    ]
}

GOOD_FINDINGS = {
    "findings": [
        {
            "source_id": "S1",
            "source_url": URL_A,
            "competitor": "Acme",
            "category": "launch",
            "claim": "Acme launched a Pro tier targeted at mid-size agencies.",
            "evidence": "Acme announced a Pro tier priced for mid-size agencies.",
        },
        {
            "source_id": "S2",
            "source_url": URL_B,
            "competitor": "Acme",
            "category": "positioning",
            "claim": "Acme now leads with turnaround time.",
            "evidence": "new site copy leads with turnaround time",
        },
    ],
    "counter_campaigns": [
        {
            "name": "Faster than fast",
            "objective": "Defend the speed claim",
            "channels": ["linkedin"],
            "key_message": "Same day, every day",
            "based_on": ["S2"],
        }
    ],
    "strategy": "Contrast our turnaround with theirs.",
}


def _retrieved_urls(result: dict) -> set[str]:
    return {s["url"] for s in result.get("sources", [])}


# --------------------------------------------------------------------------
# (a) retrieved sources → findings that each carry a real source_url
# --------------------------------------------------------------------------


async def test_retrieved_sources_produce_sourced_dated_findings(exa_env, exa_calls, fake_llm):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))
    fake_llm["payload"] = json.dumps(GOOD_FINDINGS)

    result = await competitive_intel.run_competitive_scan("Acme", {"industry": "martech"})

    assert result["status"] == "ok"
    assert result["source"] == "exa_search"
    assert result["competitors"] == ["Acme"]

    # The url-less Exa result was dropped, not turned into a source.
    assert len(result["sources"]) == 2
    assert _retrieved_urls(result) == {URL_A, URL_B}

    findings = result["findings"]
    assert len(findings) == 2
    for finding in findings:
        assert finding["source_url"] in _retrieved_urls(result)
        assert exa_client.normalize_url(finding["source_url"]) is not None
        assert finding["retrieved_at"]  # retrieval date on every finding
        assert finding["source_domain"]
    assert findings[0]["published_date"] == "2026-07-02T00:00:00.000Z"
    assert findings[1]["published_date"] is None  # not invented when absent
    assert result["dropped_unsourced_count"] == 0


async def test_llm_only_sees_retrieved_text_and_exa_gets_the_key(exa_env, exa_calls, fake_llm):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))
    fake_llm["payload"] = json.dumps(GOOD_FINDINGS)

    result = await competitive_intel.run_competitive_scan("Acme", {"industry": "martech"})

    call = exa_calls.calls[0]
    assert call["url"] == exa_client.EXA_SEARCH_URL
    assert call["headers"]["x-api-key"] == "test-exa-key"
    assert "Acme" in call["json"]["query"]
    assert call["json"]["contents"]["text"]["maxCharacters"] == competitive_intel.EXCERPT_CHARS

    prompt = fake_llm["prompts"][0]
    assert URL_A in prompt and URL_B in prompt
    assert "Acme announced a Pro tier" in prompt
    assert result["queries"]["Acme"] == call["json"]["query"]


async def test_counter_campaigns_resolve_to_retrieved_urls(exa_env, exa_calls, fake_llm):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))
    fake_llm["payload"] = json.dumps(GOOD_FINDINGS)

    result = await competitive_intel.run_competitive_scan("Acme", {})

    campaigns = result["recommendations"]["counter_campaigns"]
    assert campaigns[0]["based_on_urls"] == [URL_B]
    assert result["recommendations"]["strategy"] == "Contrast our turnaround with theirs."


# --------------------------------------------------------------------------
# (b) a model-invented finding with no matching source is DROPPED
# --------------------------------------------------------------------------

INVENTED_CLAIM = "Acme spends $4M a year on paid search."
INVENTED_URL = "https://acme-news.com/never-retrieved-press-release"
HOMEPAGE_CLAIM = "Acme is the market leader in agency tooling."


async def test_model_invented_finding_is_dropped_not_emitted(exa_env, exa_calls, fake_llm):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))
    fake_llm["payload"] = json.dumps(
        {
            "findings": [
                GOOD_FINDINGS["findings"][0],
                {
                    # Plausible-looking URL on a retrieved domain that was never fetched.
                    "source_id": "S1",
                    "source_url": INVENTED_URL,
                    "competitor": "Acme",
                    "category": "offer",
                    "claim": INVENTED_CLAIM,
                },
                {
                    # Generic homepage stand-in for a real document.
                    "source_url": "https://acme.com",
                    "competitor": "Acme",
                    "claim": HOMEPAGE_CLAIM,
                },
                {
                    # No citation at all.
                    "competitor": "Acme",
                    "claim": "Acme is hiring aggressively in EMEA.",
                },
            ]
        }
    )

    result = await competitive_intel.run_competitive_scan("Acme", {})

    assert result["status"] == "ok"
    assert len(result["findings"]) == 1
    assert result["findings"][0]["source_url"] == URL_A
    assert result["dropped_unsourced_count"] == 3

    # The invented claim and its URL appear nowhere in the emitted findings.
    assert INVENTED_CLAIM not in json.dumps(result["findings"])
    assert INVENTED_URL not in json.dumps(result["findings"])
    for finding in result["findings"]:
        assert finding["source_url"] in _retrieved_urls(result)
    assert INVENTED_URL not in {f["source_url"] for f in result["findings"]}
    assert HOMEPAGE_CLAIM not in {f["claim"] for f in result["findings"]}
    assert "https://acme.com" not in _retrieved_urls(result)


async def test_dropped_claims_are_reported_but_never_as_findings(exa_env, exa_calls, fake_llm):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))
    fake_llm["payload"] = json.dumps(
        {
            "findings": [
                GOOD_FINDINGS["findings"][0],
                {"source_url": INVENTED_URL, "claim": INVENTED_CLAIM},
            ]
        }
    )

    result = await competitive_intel.run_competitive_scan("Acme", {})

    dropped = result["dropped_unsourced"]
    assert dropped == [{"claim": INVENTED_CLAIM, "claimed_source_url": INVENTED_URL}]
    assert INVENTED_CLAIM not in {f["claim"] for f in result["findings"]}


async def test_source_url_is_copied_from_the_retrieved_record(exa_env, exa_calls, fake_llm):
    """A near-miss citation still resolves, but the emitted URL is the fetched one."""
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))
    fake_llm["payload"] = json.dumps(
        {
            "findings": [
                {
                    "source_url": "HTTPS://acme-news.com/acme-launches-pro-tier/",
                    "claim": "Acme launched a Pro tier.",
                }
            ]
        }
    )

    result = await competitive_intel.run_competitive_scan("Acme", {})

    assert len(result["findings"]) == 1
    assert result["findings"][0]["source_url"] == URL_A  # exact retrieved URL, not the model's


async def test_all_findings_unsourced_yields_unavailable_not_partial_intel(
    exa_env, exa_calls, fake_llm
):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))
    fake_llm["payload"] = json.dumps(
        {"findings": [{"source_url": INVENTED_URL, "claim": INVENTED_CLAIM}]}
    )

    result = await competitive_intel.run_competitive_scan("Acme", {})

    assert result["status"] == "unavailable"
    assert result["findings"] == []
    assert result["dropped_unsourced_count"] == 1
    assert len(result["sources"]) == 2  # real retrieved material is still shown


async def test_unparseable_model_output_is_unavailable(exa_env, exa_calls, fake_llm):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))
    fake_llm["payload"] = "Sure! Here is my analysis of Acme: they are doing well."

    result = await competitive_intel.run_competitive_scan("Acme", {})

    assert result["status"] == "unavailable"
    assert result["findings"] == []
    assert "did not return usable JSON" in result["reason"]
    # The old behaviour leaked raw model prose into the payload as "strategy".
    assert "strategy" not in result


async def test_llm_failure_does_not_become_fabricated_intel(exa_env, exa_calls, fake_llm):
    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))
    fake_llm["payload"] = RuntimeError("model down")

    result = await competitive_intel.run_competitive_scan("Acme", {})

    assert result["status"] == "unavailable"
    assert result["findings"] == []
    assert "model failed" in result["reason"]


# --------------------------------------------------------------------------
# (c) blank key → unavailable, zero LLM calls
# --------------------------------------------------------------------------


async def test_blank_key_returns_unavailable_with_no_llm_and_no_http(
    exa_env, exa_calls, fake_llm
):
    result = await competitive_intel.run_competitive_scan("Acme, Globex", {})

    assert result["status"] == "unavailable"
    assert result["findings"] == []
    assert "EXA_API_KEY" in result["reason"]
    assert exa_calls.calls == []
    assert fake_llm["invocations"] == 0


async def test_whitespace_key_is_treated_as_unconfigured(exa_env, exa_calls, fake_llm):
    exa_env("   ")

    result = await competitive_intel.run_competitive_scan("Acme", {})

    assert result["status"] == "unavailable"
    assert exa_calls.calls == []
    assert fake_llm["invocations"] == 0


async def test_rejected_key_is_unavailable_without_llm(exa_env, exa_calls, fake_llm):
    exa_env("bad-key")
    exa_calls(_response(401))

    result = await competitive_intel.run_competitive_scan("Acme", {})

    assert result["status"] == "unavailable"
    assert result["http_status"] == 401
    assert "EXA_API_KEY" in result["reason"]
    assert len(exa_calls.calls) == 1  # 4xx is permanent, not retried
    assert fake_llm["invocations"] == 0


# --------------------------------------------------------------------------
# (d) Exa returns nothing usable → unavailable, not invented findings
# --------------------------------------------------------------------------


async def test_empty_exa_results_are_unavailable_and_skip_the_llm(exa_env, exa_calls, fake_llm):
    exa_env("test-exa-key")
    exa_calls(_response(200, {"results": []}))

    result = await competitive_intel.run_competitive_scan("Acme", {})

    assert result["status"] == "unavailable"
    assert result["findings"] == []
    assert result["sources"] == []
    assert "no usable sources" in result["reason"]
    assert fake_llm["invocations"] == 0


async def test_results_without_urls_are_not_usable_sources(exa_env, exa_calls, fake_llm):
    exa_env("test-exa-key")
    exa_calls(
        _response(200, {"results": [{"title": "Acme rumour", "url": "", "text": "hearsay"}]})
    )

    result = await competitive_intel.run_competitive_scan("Acme", {})

    assert result["status"] == "unavailable"
    assert result["sources"] == []
    assert fake_llm["invocations"] == 0


async def test_network_failure_is_unavailable_not_invented(exa_env, exa_calls, fake_llm):
    exa_env("test-exa-key")
    exa_calls(httpx.ConnectError("dns down"))

    result = await competitive_intel.run_competitive_scan("Acme", {})

    assert result["status"] == "unavailable"
    assert result["findings"] == []
    assert len(exa_calls.calls) == exa_client.MAX_RETRIES + 1
    assert fake_llm["invocations"] == 0


async def test_prose_input_names_no_competitor_and_makes_no_calls(exa_env, exa_calls, fake_llm):
    exa_env("test-exa-key")

    result = await competitive_intel.run_competitive_scan(
        "We differentiate by offering white glove onboarding and faster turnaround "
        "than the incumbents in our space",
        {},
    )

    assert result["status"] == "unavailable"
    assert "No competitor names" in result["reason"]
    assert exa_calls.calls == []
    assert fake_llm["invocations"] == 0


# --------------------------------------------------------------------------
# unit: competitor parsing and the citation filter
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Acme, Globex", ["Acme", "Globex"]),
        ("- Acme\n- Globex\n- Initech", ["Acme", "Globex", "Initech"]),
        ("1. Acme\n2) Globex", ["Acme", "Globex"]),
        ("Acme - the incumbent; Globex: cheap tier", ["Acme", "Globex"]),
        ("Acme, acme, ACME", ["Acme"]),
        ("", []),
        ("   ", []),
    ],
)
def test_parse_competitors(raw, expected):
    assert competitive_intel.parse_competitors(raw) == expected


def test_parse_competitors_caps_the_list():
    parsed = competitive_intel.parse_competitors("A1, B2, C3, D4, E5")
    assert len(parsed) == competitive_intel.MAX_COMPETITORS


def test_ground_findings_is_the_enforcement_point():
    sources = [
        {
            "id": "S1",
            "competitor": "Acme",
            "title": "t",
            "url": URL_A,
            "domain": "acme-news.com",
            "published_date": None,
            "retrieved_at": "2026-08-17T00:00:00+00:00",
            "excerpt": None,
        }
    ]
    kept, dropped = competitive_intel.ground_findings(
        [
            {"source_url": URL_A, "claim": "real"},
            {"source_url": "https://elsewhere.com/x", "claim": "invented"},
            {"source_id": "S9", "claim": "bad id"},
            {"source_url": URL_A, "claim": ""},  # empty claim is not a finding
            "not a dict",
        ],
        sources,
    )

    assert [f["claim"] for f in kept] == ["real"]
    assert kept[0]["source_url"] == URL_A
    assert [d["claim"] for d in dropped] == ["invented", "bad id"]


def test_normalize_url_keeps_distinct_pages_distinct():
    assert exa_client.normalize_url("https://acme.com") != exa_client.normalize_url(
        "https://acme.com/news/pro-tier"
    )
    assert exa_client.normalize_url("https://WWW.Acme.com/a/") == exa_client.normalize_url(
        "https://acme.com/a"
    )
    assert exa_client.normalize_url("not a url") is None
    assert exa_client.normalize_url("") is None


# --------------------------------------------------------------------------
# router: the endpoint passes the grounded payload through, unavailable included
# --------------------------------------------------------------------------


class _StubResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _StubDB:
    def __init__(self, value):
        self._value = value

    async def execute(self, *_args, **_kwargs):
        return _StubResult(self._value)


class _StubProfile:
    competitor_differentiation = "Acme"


class _StubClient:
    brand_name = "Our Brand"
    industry = "martech"
    brand_profile = _StubProfile()


async def test_endpoint_returns_unavailable_without_a_key(exa_env, exa_calls, fake_llm):
    from agency.routers.competitive import trigger_competitive_scan

    client_id = uuid4()
    payload = await trigger_competitive_scan(
        client_id=client_id,
        body=None,
        user=object(),
        db=_StubDB(_StubClient()),
        org_id=uuid4(),
    )

    assert payload["status"] == "unavailable"
    assert payload["findings"] == []
    assert payload["client_id"] == str(client_id)
    assert exa_calls.calls == []
    assert fake_llm["invocations"] == 0


async def test_endpoint_returns_only_sourced_findings(exa_env, exa_calls, fake_llm):
    from agency.routers.competitive import trigger_competitive_scan

    exa_env("test-exa-key")
    exa_calls(_response(200, EXA_BODY))
    fake_llm["payload"] = json.dumps(
        {
            "findings": [
                GOOD_FINDINGS["findings"][0],
                {"source_url": INVENTED_URL, "claim": INVENTED_CLAIM},
            ]
        }
    )

    payload = await trigger_competitive_scan(
        client_id=uuid4(),
        body={"competitors": "Acme"},
        user=object(),
        db=_StubDB(_StubClient()),
        org_id=uuid4(),
    )

    assert payload["status"] == "ok"
    assert payload["client_name"] == "Our Brand"
    assert len(payload["findings"]) == 1
    for finding in payload["findings"]:
        assert finding["source_url"] in {s["url"] for s in payload["sources"]}
        assert finding["retrieved_at"]


async def test_endpoint_404s_for_a_missing_client(exa_env, exa_calls, fake_llm):
    from fastapi import HTTPException

    from agency.routers.competitive import trigger_competitive_scan

    with pytest.raises(HTTPException) as excinfo:
        await trigger_competitive_scan(
            client_id=uuid4(),
            body=None,
            user=object(),
            db=_StubDB(None),
            org_id=uuid4(),
        )
    assert excinfo.value.status_code == 404
