import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agency.config import get_settings
from agency.middleware.api_key_auth import ApiKeyAuthMiddleware
from agency.middleware.tenant import TenantMiddleware
from agency.routers import (
    acquisition,
    audit,
    auth,
    billing,
    brand_analytics,
    campaigns,
    clients,
    comments,
    competitive,
    content,
    health,
    integrations,
    magic_brief,
    notifications,
    oauth,
    portal,
    public_api,
    publishing,
    reports,
    slack,
    stats,
    team,
    webhooks_config,
)


def _parse_cors_origins(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("["):
        return json.loads(raw)
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="CampaignForge AI",
        description="Multi-Agent Digital Marketing Agency API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    origins = _parse_cors_origins(settings.cors_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )
    app.add_middleware(ApiKeyAuthMiddleware)
    app.add_middleware(TenantMiddleware)

    for router in [
        health,
        auth,
        clients,
        campaigns,
        acquisition,
        audit,
        content,
        comments,
        notifications,
        stats,
        billing,
        publishing,
        reports,
        team,
        magic_brief,
        integrations,
        webhooks_config,
        slack,
        portal,
        public_api,
        oauth,
        brand_analytics,
        competitive,
    ]:
        app.include_router(router.router, prefix="/api/v1")

    @app.on_event("startup")
    async def startup():
        from agency.services.scheduler import scheduler

        await scheduler.start()

    return app


app = create_app()
