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

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # LLM Providers
    google_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Storage
    s3_bucket_name: str = "campaignforge-media"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # AgentMail
    agentmail_api_key: str = ""
    agentmail_default_domain: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
