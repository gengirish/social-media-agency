from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from agency.config import get_settings


class TenantMiddleware(BaseHTTPMiddleware):
    """Extract org_id from JWT and inject into request.state for tenant isolation."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        from jose import JWTError, jwt

        settings = get_settings()
        auth_header = request.headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(
                    token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
                )
                request.state.org_id = payload.get("org_id")
            except JWTError:
                request.state.org_id = None
        else:
            request.state.org_id = None

        return await call_next(request)
