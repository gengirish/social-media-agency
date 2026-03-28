from functools import lru_cache

from pydantic_settings import BaseSettings


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

    # LLM Providers
    google_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""

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

    # Image Generation
    fal_api_key: str = ""

    # Trends / Search
    exa_api_key: str = ""

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""

    # CORS — accepts JSON array string or comma-separated string
    cors_origins: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
