"""Request outcome tracking — feeds "error rate by endpoint" for the beta plan.

Every request updates in-memory counters (cheap, gives a true rate). Only
failures are persisted, so an error spike costs one row per failure rather than
one row per request.
"""

import re

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from agency.services import product_analytics as pa

logger = structlog.get_logger()

_UUID_RE = re.compile(
    r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)

# Auth probes and 404s on unmatched routes are noise, not product signal.
_UNPERSISTED_STATUSES = frozenset({401, 404})

# Persisting an error for the ingest route would let tracking feed itself.
_SKIP_PATHS = frozenset({"/api/v1/events"})


def _route_template(request: Request) -> str:
    """Prefer the matched route pattern; fall back to a UUID-masked path."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return str(path)
    return _UUID_RE.sub("/{id}", request.url.path)


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            # ServerErrorMiddleware sits outside this layer, so an unhandled
            # exception reaches us as a raise, not a 500 response.
            await self._record(request, 500)
            raise

        await self._record(request, response.status_code)
        return response

    async def _record(self, request: Request, status_code: int) -> None:
        try:
            endpoint = _route_template(request)
            method = request.method
            pa.record_request(method, endpoint, status_code)

            if status_code < 400 or status_code in _UNPERSISTED_STATUSES:
                return
            if request.url.path in _SKIP_PATHS:
                return

            org_id = getattr(request.state, "org_id", None)
            await pa.track_detached(
                name=pa.API_ERROR,
                org_id=org_id,
                path=request.url.path,
                properties={
                    "endpoint": endpoint,
                    "method": method,
                    "status": str(status_code),
                },
            )
        except Exception as exc:  # pragma: no cover - must never break a request
            logger.warning("request_metrics_failed", error=str(exc))
