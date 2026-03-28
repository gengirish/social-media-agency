from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


# --- Enums ---


class ContentStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    REJECTED = "rejected"


class CampaignStatus(str, Enum):
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class WorkflowStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentName(str, Enum):
    ORCHESTRATOR = "orchestrator"
    STRATEGY = "strategy"
    SEO = "seo"
    CONTENT = "content"
    AD_COPY = "ad_copy"
    QA_BRAND = "qa_brand"
    ANALYTICS = "analytics"


# --- Auth ---


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2, max_length=255)
    org_name: str = Field(..., min_length=2, max_length=255)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    org_id: str


# --- Client ---


class ClientCreate(BaseModel):
    brand_name: str = Field(..., min_length=2, max_length=255)
    industry: str = Field(..., min_length=2, max_length=100)
    description: str = ""
    website_url: str | None = None
    contact_email: str | None = None


class BrandProfileCreate(BaseModel):
    voice_description: str = ""
    tone_attributes: dict = Field(default_factory=dict)
    vocabulary_include: list[str] = Field(default_factory=list)
    vocabulary_exclude: list[str] = Field(default_factory=list)
    example_posts: list[dict] = Field(default_factory=list)
    style_rules: list[str] = Field(default_factory=list)
    emoji_policy: str = "moderate"
    competitor_differentiation: str = ""
    target_audience: str = ""


class ClientResponse(BaseModel):
    id: UUID
    org_id: UUID
    brand_name: str
    industry: str | None
    description: str
    website_url: str | None
    contact_email: str | None
    logo_url: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ClientListResponse(BaseModel):
    items: list[ClientResponse]
    total: int
    page: int
    per_page: int


# --- Campaign ---


class CampaignCreate(BaseModel):
    client_id: UUID
    name: str = Field(..., min_length=3, max_length=255)
    objective: str = ""
    channels: list[str] = Field(default_factory=lambda: ["linkedin", "twitter"])
    start_date: date
    end_date: date
    budget: dict = Field(default_factory=dict)


class CampaignBrief(BaseModel):
    """The client brief that kicks off the LangGraph pipeline."""

    client_id: UUID
    campaign_name: str = Field(..., min_length=3)
    objective: str = Field(..., min_length=10)
    channels: list[str] = Field(default_factory=lambda: ["linkedin", "twitter"])
    target_audience: str = ""
    key_messages: list[str] = Field(default_factory=list)
    budget_usd: float = 0
    start_date: date
    end_date: date
    additional_context: str = ""
    languages: list[str] = Field(default_factory=list)


class CampaignResponse(BaseModel):
    id: UUID
    client_id: UUID
    org_id: UUID
    name: str
    objective: str
    channels: list[str]
    start_date: date
    end_date: date
    budget: dict
    status: str
    agent_plan: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int
    page: int
    per_page: int


# --- Content ---


class ContentPieceResponse(BaseModel):
    id: UUID
    campaign_id: UUID | None
    client_id: UUID
    content_type: str
    platform: str
    title: str
    body: str
    hashtags: list
    status: str
    ai_generated: bool
    performance_score: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ContentUpdateRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    hashtags: list[str] | None = None
    status: str | None = None


# --- Agent Stream Events ---


class AgentStreamEvent(BaseModel):
    type: str  # step_start, step_update, step_complete, waiting_human, error, complete
    agent: str = ""
    content: str = ""
    progress: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# --- Workflow ---


class WorkflowResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    current_node: str
    status: str
    total_duration_ms: int
    total_cost_usd: float
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# --- Stats ---


class DashboardStats(BaseModel):
    total_clients: int = 0
    total_campaigns: int = 0
    total_content_pieces: int = 0
    total_agent_runs: int = 0
    campaigns_running: int = 0
    content_drafts: int = 0
