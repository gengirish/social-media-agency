"""Pipeline nodes must never crash a campaign on malformed model JSON.

Regression for production 260923: campaign c0f57466 failed with
"Expecting ',' delimiter" because strategy/seo did a bare second json.loads on
the model's {...} slice. Now: cheap parses, then one lite-tier repair call,
then the node's own fallback shape.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from agency.agents import utils
from agency.agents.utils import parse_agent_json, text_of

GOOD = {"positioning": "fast", "pillars": ["a", "b"], "calendar": [{"day": 1}]}
STATE: Any = {"brand_context": {}, "execution_plan": {}, "client_brief": "x"}
# Missing comma between two keys — the production failure shape.
BROKEN = '{"positioning": "fast"\n "pillars": ["a", "b"], "calendar": [{"day": 1}]}'


class _Stub:
    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.calls: list[Any] = []

    async def ainvoke(self, prompt: Any) -> SimpleNamespace:
        self.calls.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(content=self.reply)


@pytest.fixture
def lite(monkeypatch):
    def install(reply: str | Exception) -> _Stub:
        stub = _Stub(reply)
        monkeypatch.setattr("agency.services.llm_provider.get_lite_llm", lambda *_a, **_k: stub)
        return stub

    return install


async def test_valid_json_needs_no_repair_call(lite):
    stub = lite(RuntimeError("must not be called"))
    assert await parse_agent_json(json.dumps(GOOD), agent="t") == GOOD
    assert await parse_agent_json(f"```json\n{json.dumps(GOOD)}\n```", agent="t") == GOOD
    assert await parse_agent_json(f"Here you go:\n{json.dumps(GOOD)}\nThanks", agent="t") == GOOD
    assert stub.calls == []


async def test_broken_json_is_repaired_once(lite):
    stub = lite(json.dumps(GOOD))
    assert await parse_agent_json(BROKEN, agent="strategy") == GOOD
    assert len(stub.calls) == 1
    assert "delimiter" in str(stub.calls[0])  # the parse error is passed to the repairer


async def test_unrepairable_returns_none_not_raise(lite):
    lite("still {not json")
    assert await parse_agent_json(BROKEN, agent="strategy") is None


async def test_repair_call_failure_returns_none(lite):
    lite(RuntimeError("provider down"))
    assert await parse_agent_json(BROKEN, agent="strategy") is None


async def test_list_expectation_accepts_array_or_single_object(lite):
    lite(RuntimeError("must not be called"))
    assert await parse_agent_json('[{"a": 1}]', agent="t", expect=list) == [{"a": 1}]
    assert await parse_agent_json('{"a": 1}', agent="t", expect=list) == {"a": 1}


def test_text_of_handles_block_lists():
    assert text_of([{"type": "text", "text": "ab"}, {"type": "text", "text": "c"}]) == "abc"
    assert text_of("x") == "x"


async def test_strategy_node_survives_the_production_failure(monkeypatch, lite):
    """End to end through the real node: malformed model output no longer raises."""
    from agency.agents import strategy

    monkeypatch.setattr(strategy, "get_worker_llm", lambda *_a, **_k: _Stub(BROKEN))

    async def _no_knowledge(*_a: Any, **_k: Any) -> list[Any]:
        return []

    monkeypatch.setattr(strategy, "retrieve_knowledge", _no_knowledge)
    lite(json.dumps(GOOD))
    out = await strategy.strategy_node(STATE)
    assert out["strategy"] == GOOD

    lite("nope")  # repair fails too → node's own fallback, still no exception
    out = await strategy.strategy_node(STATE)
    assert out["strategy"] == {"raw_output": BROKEN}


def test_utils_module_keeps_legacy_parser():
    # parse_llm_json is used by the Create-screen agents; it must stay synchronous.
    assert utils.parse_llm_json('{"a": 1}') == {"a": 1}
