"""Smoke test for graph compilation."""

from agency.agents.graph import build_campaign_graph, get_compiled_graph


def test_graph_builds():
    graph = build_campaign_graph()
    assert graph is not None


def test_graph_compiles():
    compiled = get_compiled_graph()
    assert compiled is not None
