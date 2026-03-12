"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from flowkit.persistence.database import dispose_engine, get_engine

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


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
    )

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

    return app
