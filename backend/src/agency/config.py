from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


def generate_token_encryption_key() -> str:
    """Return a new url-safe Fernet key suitable for TOKEN_ENCRYPTION_KEY."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


class Settings(BaseSettings):
    app_env: str = "dev"
    debug: bool = False

    # Database (Neon PostgreSQL)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/campaignforge"
    neon_database_url: str = ""  # Pooled Neon connection for LangGraph checkpointer

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Auth (legacy JWT)
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Clerk
    clerk_secret_key: str = ""
    clerk_jwks_url: str = ""

    # Optional: first-time Clerk sign-ins for these emails attach to this org (see db/seed.sql).
    demo_org_id: str = ""
    demo_org_allowlist: str = ""

    # LLM Providers.
    # Each provider needs an api key; OpenAI-compatible ones also take a base_url.
    # A blank key disables that provider — see services/llm_provider.py.
    google_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    )
    gemini_model: str = "gemini-2.5-flash"

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"

    anthropic_api_key: str = ""

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-oss-120b"

    nvidia_nim_api_key: str = ""
    nvidia_nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_nim_model: str = "deepseek-ai/deepseek-v4-flash"

    bonsai_api_key: str = ""
    bonsai_base_url: str = "https://api.trybons.ai/v1"
    bonsai_model: str = "gpt-4o-mini"

    # Comma-separated preference order. Blank uses llm_provider.DEFAULT_PROVIDER_ORDER.
    llm_provider_order: str = ""

    # Pin one provider to a tier, overriding the order entirely.
    llm_brain_provider: str = ""
    llm_worker_provider: str = ""
    llm_ad_copy_provider: str = ""
    llm_lite_provider: str = ""

    # Override the model for a tier, whichever provider ends up serving it.
    llm_brain_model: str = ""
    llm_worker_model: str = ""
    llm_ad_copy_model: str = ""
    llm_lite_model: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_growth: str = ""
    stripe_price_agency: str = ""

    # Storage
    s3_bucket_name: str = "campaignforge-media"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # AgentMail
    agentmail_api_key: str = ""
    agentmail_default_domain: str = ""

    # OAuth
    twitter_client_id: str = ""
    twitter_client_secret: str = ""
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""

    # OAuth tokens at rest (Fernet). In dev, a built-in fallback is used if
    # unset (see utils.encryption).
    token_encryption_key: str = ""

    # Image Generation
    fal_api_key: str = ""

    # Trends / Search
    exa_api_key: str = ""

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""

    # CORS — accepts JSON array string or comma-separated string
    cors_origins: str = "http://localhost:3000"

    # Stripe Checkout return URLs when the client omits success_url / cancel_url
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
