import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.types import UserDefinedType

# Postgres-native types carrying a SQLite variant. Behaviour on Postgres is
# byte-for-byte the same as the bare types used elsewhere in this module (uuid,
# text[]); the variant only exists so the webhook tables can be exercised
# against an in-memory SQLite database in unit tests, where the rest of the
# schema (JSONB, arrays) cannot be created.
PortableUUID = UUID(as_uuid=True).with_variant(Uuid(as_uuid=True), "sqlite")
PortableTextArray = ARRAY(Text).with_variant(JSON(), "sqlite")
PortableJSONB = JSONB().with_variant(JSON(), "sqlite")

# Every embedding column is this wide regardless of which provider produced the
# vector. pgvector fixes the dimension per column, but the configured embedding
# provider can change (Google returns 768, OpenAI 1536), so shorter vectors are
# zero-padded to this width on write and on query. Cosine similarity is
# unchanged by padding both operands with the same trailing zeros — the dot
# product and both norms are identical — so this costs storage, not accuracy.
# ``knowledge_embedding.embedding_dim`` records the true, unpadded width and
# every query filters on the model that produced the row, so vectors from two
# different providers are never compared.
EMBEDDING_STORAGE_DIM = 1536


class PgVector(UserDefinedType[list[float]]):
    """Minimal ``pgvector`` column type.

    Hand-rolled rather than imported from the ``pgvector`` package so the schema
    adds no Python dependency: the single prerequisite is
    ``CREATE EXTENSION IF NOT EXISTS vector`` on the database. Values move over
    the wire in pgvector's text form (``[0.1,0.2]``).
    """

    cache_ok = True

    def __init__(self, dim: int = EMBEDDING_STORAGE_DIM) -> None:
        self.dim = dim

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dim})"

    def bind_processor(self, dialect: Any) -> Any:
        def process(value: Any) -> Any:
            if value is None:
                return None
            return "[" + ",".join(repr(float(v)) for v in value) + "]"

        return process

    def result_processor(self, dialect: Any, coltype: Any) -> Any:
        def process(value: Any) -> Any:
            if value is None:
                return None
            if isinstance(value, list | tuple):
                return [float(v) for v in value]
            return [float(v) for v in str(value).strip("[] ").split(",") if v.strip()]

        return process


# SQLite has no vector type; the variant stores the same list as JSON so the
# retrieval path can be exercised in unit tests (similarity is then computed in
# Python — see ``services/knowledge_base.py``).
PortableVector = PgVector(EMBEDDING_STORAGE_DIM).with_variant(JSON(), "sqlite")


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
    clients_limit = Column(Integer, default=1)
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

    # Mirrors db/init.sql — the campaign list endpoint filters (org_id, status).
    __table_args__ = (Index("idx_campaign_org_status", "org_id", "status"),)


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

    # Mirrors db/init.sql. The partial index serves the scheduler's once-a-minute
    # sweep for due content — the highest-frequency query in the system.
    __table_args__ = (
        Index(
            "idx_content_piece_due",
            "status",
            "scheduled_at",
            postgresql_where=text("status = 'scheduled'"),
        ),
        Index("idx_content_piece_org_status", "org_id", "status"),
    )


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
    portal_enabled = Column(Boolean, default=False)
    email_from_name = Column(String(255))
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


class Notification(Base):
    __tablename__ = "notification"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    body = Column(Text, default="")
    data = Column(JSONB, default={})
    read = Column(Boolean, default=False)
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


class ProductEvent(Base):
    """Product-analytics event stream backing the beta metrics dashboard.

    Distinct from ``AuditLog``: audit records *who changed what* for compliance,
    this records *how the product is used* for the beta success criteria in
    ``docs/beta-testing-plan.md`` §7. ``org_id``/``user_id`` are nullable so
    errors on unauthenticated requests are still captured.
    """

    __tablename__ = "product_event"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    session_id = Column(String(64), default="")
    name = Column(String(100), nullable=False)
    category = Column(String(30), nullable=False, default="feature")
    path = Column(String(500), default="")
    campaign_id = Column(UUID(as_uuid=True), nullable=True)
    duration_ms = Column(Integer)
    properties = Column(JSONB, default={})
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Webhook(Base):
    """A tenant-registered outbound HTTP endpoint.

    ``secret`` is the per-webhook HMAC-SHA256 signing key. It is returned to the
    caller exactly once, at registration, and never echoed by list responses —
    the receiver needs the same value to verify ``X-Webhook-Signature``, so it is
    stored in plaintext rather than hashed.
    """

    __tablename__ = "webhook"

    id = Column(PortableUUID, primary_key=True, default=uuid.uuid4)
    org_id = Column(PortableUUID, ForeignKey("organization.id"), nullable=False)
    url = Column(Text, nullable=False)
    events = Column(PortableTextArray, default=[])
    secret = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class WebhookDelivery(Base):
    """One row per delivery *attempt* — the audit trail behind a webhook."""

    __tablename__ = "webhook_delivery"

    id = Column(PortableUUID, primary_key=True, default=uuid.uuid4)
    webhook_id = Column(
        PortableUUID, ForeignKey("webhook.id", ondelete="CASCADE"), nullable=False
    )
    org_id = Column(PortableUUID, ForeignKey("organization.id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    attempt = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="failed")
    response_code = Column(Integer)
    error = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class KnowledgeEmbedding(Base):
    """One embedded chunk of the marketing skill library — the RAG index.

    Not org-scoped: the skill library ships with the product and is identical
    for every tenant, so there is no tenant data here and nothing to filter on.
    If per-tenant documents are ever indexed, add ``org_id`` and scope the
    query in :mod:`agency.services.knowledge_base` — there is no RLS.

    ``embedding_provider``/``embedding_model``/``embedding_dim`` are stored per
    row because vectors from different models are not comparable. Retrieval
    filters on the model currently configured, so switching providers makes the
    old rows invisible rather than silently returning nonsense; re-run
    ``backend/scripts/index_knowledge_base.py`` after a switch.
    """

    __tablename__ = "knowledge_embedding"

    id = Column(PortableUUID, primary_key=True, default=uuid.uuid4)
    # Stable per source file (md5 of the relative path), so a re-index replaces
    # rather than duplicates.
    document_id = Column(String(64), nullable=False)
    source_path = Column(Text, nullable=False)
    title = Column(String(500), nullable=False, default="")
    category = Column(String(100), nullable=False, default="general")
    chunk_index = Column(Integer, nullable=False, default=0)
    chunk_text = Column(Text, nullable=False)
    embedding_provider = Column(String(50), nullable=False)
    embedding_model = Column(String(100), nullable=False)
    embedding_dim = Column(Integer, nullable=False)
    embedding = Column(PortableVector, nullable=False)
    metadata_ = Column("metadata", PortableJSONB, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "embedding_model", "document_id", "chunk_index", name="uq_knowledge_embedding_chunk"
        ),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100))
    resource_id = Column(String(255))
    details = Column(JSONB, default={})
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
