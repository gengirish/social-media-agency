import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organization"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    domain = Column(String(255))
    settings = Column(JSONB, default={})
    agentmail_inbox_id = Column(String(255))
    agentmail_email = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="viewer")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Subscription(Base):
    __tablename__ = "subscription"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    stripe_customer_id = Column(String(255))
    stripe_subscription_id = Column(String(255))
    plan_tier = Column(String(50), nullable=False, default="free")
    clients_limit = Column(Integer, default=3)
    posts_limit = Column(Integer, default=30)
    posts_used = Column(Integer, default=0)
    current_period_start = Column(DateTime(timezone=True))
    current_period_end = Column(DateTime(timezone=True))
    status = Column(String(50), default="active")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Client(Base):
    __tablename__ = "client"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    brand_name = Column(String(255), nullable=False)
    industry = Column(String(100))
    description = Column(Text, default="")
    website_url = Column(String(500))
    contact_email = Column(String(255))
    logo_url = Column(Text)
    settings = Column(JSONB, default={})
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    brand_profile = relationship("BrandProfile", back_populates="client", uselist=False)
    campaigns = relationship("Campaign", back_populates="client")


class BrandProfile(Base):
    __tablename__ = "brand_profile"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("client.id"), nullable=False, unique=True)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    voice_description = Column(Text, default="")
    tone_attributes = Column(JSONB, default={})
    vocabulary_include = Column(ARRAY(Text), default=[])
    vocabulary_exclude = Column(ARRAY(Text), default=[])
    example_posts = Column(JSONB, default=[])
    style_rules = Column(ARRAY(Text), default=[])
    emoji_policy = Column(String(20), default="moderate")
    competitor_differentiation = Column(Text, default="")
    target_audience = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="brand_profile")


class PlatformAccount(Base):
    __tablename__ = "platform_account"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("client.id"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    platform = Column(String(50), nullable=False)
    account_handle = Column(String(255), nullable=False)
    display_name = Column(String(255))
    access_token_enc = Column(Text)
    refresh_token_enc = Column(Text)
    token_expires_at = Column(DateTime(timezone=True))
    followers_count = Column(Integer, default=0)
    status = Column(String(30), default="connected")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Campaign(Base):
    __tablename__ = "campaign"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("client.id"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    name = Column(String(255), nullable=False)
    objective = Column(Text, default="")
    channels = Column(ARRAY(Text), default=[])
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    budget = Column(JSONB, default={})
    status = Column(String(30), default="planning")
    agent_plan = Column(JSONB, default={})
    tags = Column(JSONB, default=[])
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="campaigns")
    content_pieces = relationship("ContentPiece", back_populates="campaign")
    agent_runs = relationship("AgentRun", back_populates="campaign")
    workflow = relationship("Workflow", back_populates="campaign", uselist=False)


class ContentPiece(Base):
    __tablename__ = "content_piece"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaign.id"), nullable=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("client.id"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    agent_run_id = Column(UUID(as_uuid=True), ForeignKey("agent_run.id"), nullable=True)
    content_type = Column(String(50), default="social_post")
    platform = Column(String(50), nullable=False)
    title = Column(String(500), default="")
    body = Column(Text, default="")
    hashtags = Column(JSONB, default=[])
    metadata_ = Column("metadata", JSONB, default={})
    media_urls = Column(JSONB, default=[])
    ai_generated = Column(Boolean, default=True)
    status = Column(String(30), default="draft")
    performance_score = Column(Float)
    scheduled_at = Column(DateTime(timezone=True))
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="content_pieces")


class AgentRun(Base):
    __tablename__ = "agent_run"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaign.id"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    agent_name = Column(String(50), nullable=False)
    input_summary = Column(Text, default="")
    output = Column(Text, default="")
    tokens_used = Column(Integer, default=0)
    model_used = Column(String(100), default="")
    duration_ms = Column(Integer, default=0)
    cost_usd = Column(Numeric(10, 6), default=0)
    status = Column(String(30), default="running")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="agent_runs")


class Workflow(Base):
    __tablename__ = "workflow"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaign.id"), nullable=False, unique=True)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    current_node = Column(String(50), default="")
    status = Column(String(30), default="running")
    total_duration_ms = Column(Integer, default=0)
    total_cost_usd = Column(Numeric(10, 6), default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True))

    campaign = relationship("Campaign", back_populates="workflow")


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshot"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform_account_id = Column(
        UUID(as_uuid=True), ForeignKey("platform_account.id"), nullable=False
    )
    content_id = Column(UUID(as_uuid=True), ForeignKey("content_piece.id"), nullable=True)
    date = Column(Date, nullable=False)
    impressions = Column(Integer, default=0)
    reach = Column(Integer, default=0)
    engagement = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    followers_delta = Column(Integer, default=0)
    extra = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ContentComment(Base):
    __tablename__ = "content_comment"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content_piece.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class WhiteLabel(Base):
    __tablename__ = "white_label"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, unique=True)
    custom_domain = Column(String(255))
    logo_url = Column(Text)
    primary_color = Column(String(7), default="#4f46e5")
    company_name = Column(String(255))
    support_email = Column(String(255))
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class CampaignTemplate(Base):
    __tablename__ = "campaign_template"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    category = Column(String(100), default="general")
    objective_template = Column(Text, default="")
    channels = Column(ARRAY(Text), default=[])
    content_directives = Column(JSONB, default={})
    is_public = Column(Boolean, default=False)
    uses_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ApiKey(Base):
    __tablename__ = "api_key"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(255), nullable=False)
    key_prefix = Column(String(10), nullable=False)
    permissions = Column(ARRAY(Text), default=["read"])
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
