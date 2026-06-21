"""API authentication middleware."""

import logging
import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from flowkit.config import get_settings

logger = logging.getLogger(__name__)

# Paths that skip auth
_PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Middleware that validates X-API-Key header against configured key."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Check API key on non-public paths when auth is enabled."""
        settings = get_settings()
        # If no API key configured, auth is disabled (dev mode)
        if not settings.api_key:
            return await call_next(request)

        # Skip auth for public paths
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        # Check X-API-Key header
        provided_key = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(provided_key, settings.api_key):
            logger.warning(
                "Auth failed from %s",
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Invalid or missing API key",
                    }
                },
            )

        return await call_next(request)
