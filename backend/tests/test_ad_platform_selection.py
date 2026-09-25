"""CF-04 — ad copy is written only for ad networks the campaign selected.

A campaign whose channels were `["linkedin", "twitter"]` came back with
`google_ad` and `meta_ad` drafts. The Ad Copy agent read
`execution_plan.ad_directives.platforms`, which the orchestrator writes freely,
and fell back to a hardcoded `["google", "meta"]` that ignored the brief.
"""

from types import SimpleNamespace

import pytest

from agency.agents.ad_copy import ad_copy_node, selected_ad_platforms


class TestSelectedAdPlatforms:
    def test_organic_channels_alone_select_no_ad_network(self):
        # The exact case from the report.
        assert selected_ad_platforms(["linkedin", "twitter"], ["google", "meta"]) == []

    def test_an_opted_in_ad_channel_is_selected(self):
        assert selected_ad_platforms(["linkedin", "google_ads"], []) == ["google"]

    def test_several_ad_channels_keep_their_order(self):
        channels = ["meta_ads", "linkedin", "google_ads"]
        assert selected_ad_platforms(channels, []) == ["meta", "google"]

    def test_the_orchestrator_may_narrow_the_selection(self):
        # It has the strategy in hand, so dropping one of the chosen networks is
        # a judgement worth honouring.
        assert selected_ad_platforms(["google_ads", "meta_ads"], ["google"]) == ["google"]

    def test_the_orchestrator_may_not_widen_it(self):
        # Suggesting a network nobody ticked would spend a budget nobody approved.
        assert selected_ad_platforms(["google_ads"], ["google", "meta", "linkedin"]) == ["google"]

    def test_a_suggestion_that_overlaps_nothing_falls_back_to_the_brief(self):
        # The user's selection wins over an orchestrator that ignored it.
        assert selected_ad_platforms(["google_ads"], ["meta"]) == ["google"]

    def test_meta_aliases_all_map_to_meta(self):
        for alias in ("meta_ads", "facebook_ads", "instagram_ads"):
            assert selected_ad_platforms([alias], []) == ["meta"]

    def test_empty_and_malformed_channels_select_nothing(self):
        assert selected_ad_platforms([], ["google"]) == []
        assert selected_ad_platforms(["", "  ", "nonsense"], ["google"]) == []


@pytest.fixture
def never_called_llm(monkeypatch):
    """A model that fails the test if the node calls it."""

    class Boom:
        async def ainvoke(self, _messages):
            raise AssertionError("the ad copy model must not be called")

    monkeypatch.setattr("agency.agents.ad_copy.get_ad_copy_llm", lambda *a, **k: Boom())


async def test_node_writes_nothing_and_spends_nothing_when_no_ad_channel(never_called_llm):
    """No selected network means no model call — not an empty call."""
    state = {
        "channels": ["linkedin", "twitter"],
        "execution_plan": {"ad_directives": {"platforms": ["google", "meta"]}},
    }

    out = await ad_copy_node(state)  # type: ignore[arg-type]

    assert out["ad_variants"] == []
    assert out["current_agent"] == "ad_copy"


async def test_node_drops_a_variant_for_a_network_that_was_not_selected(monkeypatch):
    """The model occasionally volunteers an extra network; it must not reach the queue."""
    reply = """[
        {"platform": "google", "variant": 1, "headlines": ["Kept"], "descriptions": ["d"]},
        {"platform": "meta", "variant": 1, "primary_text": "Dropped — not selected"}
    ]"""

    class Stub:
        async def ainvoke(self, _messages):
            return SimpleNamespace(content=reply)

    monkeypatch.setattr("agency.agents.ad_copy.get_ad_copy_llm", lambda *a, **k: Stub())

    state = {
        "channels": ["linkedin", "google_ads"],
        "execution_plan": {"ad_directives": {"platforms": ["google"]}},
    }

    out = await ad_copy_node(state)  # type: ignore[arg-type]

    assert [v["platform"] for v in out["ad_variants"]] == ["google"]


async def test_unparseable_output_falls_back_to_a_selected_network(monkeypatch):
    """The fallback variant used to be hardcoded to google whatever was selected."""

    class Stub:
        async def ainvoke(self, _messages):
            return SimpleNamespace(content="not json at all")

    monkeypatch.setattr("agency.agents.ad_copy.get_ad_copy_llm", lambda *a, **k: Stub())

    state = {"channels": ["meta_ads"], "execution_plan": {"ad_directives": {}}}

    out = await ad_copy_node(state)  # type: ignore[arg-type]

    assert [v["platform"] for v in out["ad_variants"]] == ["meta"]
