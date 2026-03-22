"""CampaignForge LangGraph — Multi-Agent Campaign Pipeline.

Architecture:
  Orchestrator → [Strategy ∥ SEO] → [Content ∥ Ad Copy] → Human Review → QA/Brand → Output

- Strategy and SEO run in parallel (no dependency on each other)
- Content and Ad Copy run in parallel (both consume strategy + SEO output)
- Human review is an interrupt point before QA
- QA failures can loop back to Content or Ad Copy for revision
"""

from langgraph.graph import END, START, StateGraph

from agency.agents.ad_copy import ad_copy_node
from agency.agents.content_writer import content_writer_node
from agency.agents.orchestrator import orchestrator_node
from agency.agents.qa_brand import qa_brand_node
from agency.agents.seo import seo_node
from agency.agents.state import CampaignState
from agency.agents.strategy import strategy_node


def _merge_after_strategy_seo(state: CampaignState) -> str:
    """After Strategy and SEO complete, route to content generation phase."""
    return "create_content"


def _route_after_human_review(state: CampaignState) -> str:
    """Route based on human review decision."""
    review = state.get("human_review", "pending")
    if review == "approved":
        return "qa_check"
    if review == "revise_content":
        return "create_content"
    if review == "revise_ads":
        return "write_ads"
    # Default: if pending or unknown, go to QA (auto-approve path)
    return "qa_check"


def _route_after_qa(state: CampaignState) -> str:
    """Route based on QA results — pass or loop back."""
    qa = state.get("qa_feedback", {})
    if not qa.get("pass", True):
        retry = state.get("retry_count", 0)
        if retry >= 2:
            return "compile_output"

        issues = qa.get("issues", [])
        has_content_issues = any(i.get("type") == "content" and i.get("severity") == "critical" for i in issues)
        has_ad_issues = any(i.get("type") == "ad" and i.get("severity") == "critical" for i in issues)

        if has_content_issues:
            return "create_content"
        if has_ad_issues:
            return "write_ads"

    return "compile_output"


def compile_output_node(state: CampaignState) -> dict:
    """Compile all agent outputs into the final campaign deliverable."""
    return {
        "status": "completed",
        "current_agent": "complete",
    }


def human_review_node(state: CampaignState) -> dict:
    """Placeholder node for human-in-the-loop. Execution pauses here via interrupt_before."""
    review = state.get("human_review", "pending")
    if review == "pending":
        return {"human_review": "approved"}
    return {}


def build_campaign_graph() -> StateGraph:
    """Construct the CampaignForge multi-agent graph."""

    graph = StateGraph(CampaignState)

    # --- Add nodes ---
    graph.add_node("orchestrate", orchestrator_node)
    graph.add_node("strategise", strategy_node)
    graph.add_node("seo_research", seo_node)
    graph.add_node("create_content", content_writer_node)
    graph.add_node("write_ads", ad_copy_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("qa_check", qa_brand_node)
    graph.add_node("compile_output", compile_output_node)

    # --- Define edges ---

    # Entry: start with orchestrator
    graph.add_edge(START, "orchestrate")

    # Orchestrator fans out to Strategy AND SEO (parallel)
    graph.add_edge("orchestrate", "strategise")
    graph.add_edge("orchestrate", "seo_research")

    # Strategy and SEO both feed into Content AND Ad Copy (parallel)
    graph.add_edge("strategise", "create_content")
    graph.add_edge("seo_research", "create_content")
    graph.add_edge("strategise", "write_ads")
    graph.add_edge("seo_research", "write_ads")

    # Content and Ad Copy both feed into human review
    graph.add_edge("create_content", "human_review")
    graph.add_edge("write_ads", "human_review")

    # Human review routes conditionally
    graph.add_conditional_edges("human_review", _route_after_human_review, {
        "qa_check": "qa_check",
        "create_content": "create_content",
        "write_ads": "write_ads",
    })

    # QA routes conditionally (pass or loop back)
    graph.add_conditional_edges("qa_check", _route_after_qa, {
        "compile_output": "compile_output",
        "create_content": "create_content",
        "write_ads": "write_ads",
    })

    # Final output
    graph.add_edge("compile_output", END)

    return graph


def get_compiled_graph(checkpointer=None):
    """Compile the graph with optional checkpointer and human-in-the-loop interrupt."""
    graph = build_campaign_graph()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],
    )
