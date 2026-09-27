"""CF-07 — a failed campaign records why, and which agent it can be blamed on.

Four of five campaigns showed "Failed" with no error anywhere in the UI. The
pipeline logged the exception and dropped it; nothing was written to the row.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from agency.models.tables import AgentRun, Campaign
from agency.routers.campaigns import _failing_agents, _mark_campaign_failed
from tests.conftest import create_campaign_row, create_client_row, create_org


class TestFailingAgents:
    """Attribution is inferred from which nodes finished — astream does not say."""

    def test_nothing_finished_blames_the_first_node(self):
        assert _failing_agents(set()) == ["orchestrate"]

    def test_a_parallel_pair_in_flight_reports_both_candidates(self):
        # Strategy and SEO run in parallel. Naming one would be a guess.
        assert _failing_agents({"orchestrate"}) == ["strategise", "seo_research"]

    def test_one_branch_of_a_pair_done_names_the_other(self):
        assert _failing_agents({"orchestrate", "strategise"}) == ["seo_research"]

    def test_the_second_parallel_stage_is_handled_the_same(self):
        completed = {"orchestrate", "strategise", "seo_research", "create_content"}
        assert _failing_agents(completed) == ["write_ads"]

    def test_a_single_node_stage_is_named_exactly(self):
        completed = {
            "orchestrate", "strategise", "seo_research",
            "create_content", "write_ads", "human_review",
        }
        assert _failing_agents(completed) == ["qa_check"]

    def test_everything_done_blames_no_agent(self):
        # The crash was in the bookkeeping after the graph, not in an agent.
        completed = {
            "orchestrate", "strategise", "seo_research", "create_content",
            "write_ads", "human_review", "qa_check", "compile_output", "analytics",
        }
        assert _failing_agents(completed) == []


@pytest.fixture
async def failed_campaign(session_factory):
    """An org with one campaign, ready to be failed."""
    org_id = await create_org(session_factory, "Failure Org")
    client_id = await create_client_row(session_factory, org_id, "Failure Brand")
    campaign_id = await create_campaign_row(session_factory, org_id, client_id, status="running")
    return org_id, client_id, campaign_id


async def _campaign(session_factory, campaign_id: UUID) -> Campaign:
    async with session_factory() as db:
        return (
            await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        ).scalar_one()


async def test_failure_reason_is_stored_on_the_campaign(session_factory, failed_campaign):
    org_id, _, campaign_id = failed_campaign

    await _mark_campaign_failed(
        str(campaign_id),
        str(org_id),
        "Connection refused to the model provider",
        error_type="APIConnectionError",
        completed={"orchestrate", "strategise"},
    )

    campaign = await _campaign(session_factory, campaign_id)
    assert campaign.status == "failed"
    assert campaign.failure["error"] == "Connection refused to the model provider"
    assert campaign.failure["error_type"] == "APIConnectionError"
    assert campaign.failure["agents"] == ["seo_research"]
    # The last agent that did finish — the honest anchor for the UI.
    assert campaign.failure["after"] == "strategise"
    assert campaign.failure["at"]


async def test_a_failed_agent_run_row_is_written_so_the_dashboard_can_show_it(
    session_factory, failed_campaign
):
    """Without this the live dashboard leaves the failing step on "queued"."""
    org_id, _, campaign_id = failed_campaign

    await _mark_campaign_failed(
        str(campaign_id), str(org_id), "boom", completed={"orchestrate"}
    )

    async with session_factory() as db:
        rows = (
            await db.execute(
                select(AgentRun.agent_name, AgentRun.status).where(
                    AgentRun.campaign_id == campaign_id
                )
            )
        ).all()

    # Both branches of the parallel stage are marked: either could have thrown.
    assert sorted(rows) == [("seo_research", "failed"), ("strategise", "failed")]


async def test_recording_a_failure_never_raises_on_a_missing_campaign(session_factory):
    """Bookkeeping must not turn one failure into two."""
    await _mark_campaign_failed(str(uuid4()), str(uuid4()), "boom", completed=set())
