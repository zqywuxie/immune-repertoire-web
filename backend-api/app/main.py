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
        description="""
## Immune Repertoire Platform API

Unified REST API for the Immune Repertoire analysis platform.

### Migration Status (Phase 5 — 2026-06-29)

| Domain    | Status |
|-----------|--------|
| Projects  | ✅ Real SQL |
| Assets    | ✅ Real SQL (list/preview/download/upload) |
| Jobs      | ✅ Real SQL (CRUD + SSE events + submission) |
| System    | ✅ Health + Info |
| Auth      | 🔄 Placeholder (Flask bridge) |

### Backends

- **Flask** — current production backend at `:5000`
- **FastAPI** — this API, migrating routes from Flask

### Storage

- Default: local filesystem (`local://` URIs)
- Optional: S3/MinIO (`STORAGE_BACKEND=s3`)
        """.strip(),
        version="0.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
        contact={"name": "Immune Repertoire Team"},
        license_info={"name": "Proprietary"},
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
