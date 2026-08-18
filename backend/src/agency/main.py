import json

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agency.config import get_settings
from agency.middleware.api_key_auth import ApiKeyAuthMiddleware
from agency.middleware.request_metrics import RequestMetricsMiddleware
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
    product_analytics,
    public_api,
    publishing,
    reports,
    slack,
    stats,
    team,
    webhooks_config,
)

logger = structlog.get_logger()


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
    # Logged because a missing origin is otherwise silent and looks like an app
    # bug: Starlette answers a disallowed preflight with a bare 400 and writes
    # nothing, so the browser reports a CORS failure while the server looks
    # healthy. On 260818 the production domain was absent here and every
    # browser request failed preflight while curl (which does not preflight)
    # kept working. The FIRST entry is also the app's own base URL for building
    # OAuth redirect URIs -- see routers/oauth.py::_first_cors_origin -- so
    # order is load-bearing, not cosmetic.
    logger.info(
        "cors_allowed_origins",
        origins=origins,
        oauth_base_url=origins[0] if origins else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )
    # Added first => innermost, so TenantMiddleware has already resolved
    # request.state.org_id by the time request outcomes are recorded.
    app.add_middleware(RequestMetricsMiddleware)
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
        product_analytics,
    ]:
        app.include_router(router.router, prefix="/api/v1")

    @app.on_event("startup")
    async def startup():
        from agency.agents.graph_runtime import init_campaign_graph_runtime
        from agency.services.scheduler import scheduler

        await init_campaign_graph_runtime()
        await scheduler.start()

    @app.on_event("shutdown")
    async def shutdown():
        from agency.agents.graph_runtime import shutdown_campaign_graph_runtime
        from agency.services.scheduler import scheduler

        await scheduler.stop()
        await shutdown_campaign_graph_runtime()

    return app


app = create_app()
