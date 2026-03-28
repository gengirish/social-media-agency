"""CampaignForge LangGraph state definition.

The CampaignState flows through all agents, accumulating outputs from each node.
Agents read what they need and write their outputs to specific keys.
"""

from typing import Annotated, TypedDict

from langgraph.graph import add_messages


class BrandContext(TypedDict, total=False):
    brand_name: str
    industry: str
    description: str
    voice_description: str
    tone_attributes: dict
    target_audience: str
    style_rules: list[str]
    vocabulary_include: list[str]
    vocabulary_exclude: list[str]
    emoji_policy: str
    competitor_differentiation: str


class CampaignState(TypedDict, total=False):
    # --- Input (set at campaign creation) ---
    client_brief: str
    client_id: str
    campaign_id: str
    org_id: str
    channels: list[str]
    budget_usd: float
    target_languages: list[str]
    brand_context: BrandContext

    # --- Agent outputs (filled progressively) ---
    execution_plan: dict           # Orchestrator output
    strategy: dict                 # Strategy Agent output
    seo_keywords: list[dict]       # SEO Agent output
    content_pieces: list[dict]     # Content Agent output
    ad_variants: list[dict]        # Ad Copy Agent output
    qa_feedback: dict              # QA/Brand Agent output

    # --- Analytics Agent ---
    engagement_data: dict          # Per-post / per-platform metrics for analysis
    analytics_insights: dict       # Recommendations and narrative insights

    # --- Human-in-the-loop ---
    human_review: str              # "pending" | "approved" | "revision_needed"
    human_feedback: str

    # --- Control flow ---
    status: str
    errors: list[str]
    current_agent: str
    retry_count: int

    # --- Messages for streaming ---
    messages: Annotated[list, add_messages]
