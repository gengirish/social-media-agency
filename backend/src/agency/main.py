from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agency.config import get_settings
from agency.middleware.tenant import TenantMiddleware
from agency.routers import auth, campaigns, clients, content, health, stats


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="CampaignForge AI",
        description="Multi-Agent Digital Marketing Agency API",
        version="0.1.0",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(TenantMiddleware)

    for router in [health, auth, clients, campaigns, content, stats]:
        app.include_router(router.router, prefix="/api/v1")

    return app


app = create_app()
