"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request

from flowkit.api.schemas.errors import ErrorResponse
from flowkit.errors import FlowkitError
from flowkit.persistence.database import dispose_engine, get_engine

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[str, int] = {
    "NOT_FOUND": 404,
    "VALIDATION_ERROR": 422,
    "EXECUTION_ERROR": 500,
    "TIMEOUT": 504,
    "WEBHOOK_ERROR": 400,
    "INVALID_TRANSITION": 409,
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown."""
    # Startup: initialize engine (lazy, but we trigger it here)
    get_engine()
    yield
    # Shutdown: dispose engine
    await dispose_engine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Flowkit",
        description="Headless workflow backend service",
        version="0.1.0",
        lifespan=lifespan,
        responses={401: {"model": ErrorResponse, "description": "Unauthorized"}},
    )

    # Authentication middleware
    from flowkit.api.middleware import ApiKeyMiddleware

    app.add_middleware(ApiKeyMiddleware)

    # Import and include routers
    from flowkit.api.routes.runs import router as runs_router
    from flowkit.api.routes.triggers import router as triggers_router
    from flowkit.api.routes.workflows import router as workflows_router

    app.include_router(workflows_router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    app.include_router(triggers_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(FlowkitError)
    async def flowkit_error_handler(request: Request, exc: FlowkitError) -> JSONResponse:
        status_code = _STATUS_MAP.get(exc.code, 500)
        logger.warning(
            "FlowkitError code=%s status=%d: %s", exc.code, status_code, exc
        )
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                }
            },
        )

    return app
