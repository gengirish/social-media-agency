"""API key authentication middleware for public REST API access."""

from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from agency.models.database import get_session_factory
from agency.services.api_keys import validate_api_key


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Authenticate requests using X-API-Key header for /api/v1/public/* routes."""

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/v1/public/"):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if not api_key:
            return JSONResponse(
                {"detail": "X-API-Key header required"},
                status_code=401,
            )

        session_factory = get_session_factory()
        async with session_factory() as db:
            result = await validate_api_key(db, api_key)
            if not result:
                return JSONResponse(
                    {"detail": "Invalid API key"},
                    status_code=401,
                )
            request.state.api_key_org_id = UUID(result["org_id"])

        return await call_next(request)
