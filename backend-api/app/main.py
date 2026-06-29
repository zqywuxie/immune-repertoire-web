"""FastAPI application entry point for the Immune Repertoire Platform API.

This is a Phase 5 skeleton — Flask still serves production traffic.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router as api_router
from .core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Immune Repertoire Platform API",
        version="0.1.0",
        description="Unified API for the Immune Repertoire analysis platform.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    from .core.error_handlers import register_error_handlers
    register_error_handlers(app)

    return app


app = create_app()
