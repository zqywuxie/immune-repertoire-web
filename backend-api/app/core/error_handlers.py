"""Global exception handlers and middleware for the FastAPI application."""

import traceback
from typing import Union

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTP exceptions with consistent JSON format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": "HTTP_ERROR",
            "message": str(exc.detail),
            "status_code": exc.status_code,
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic validation errors."""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error.get("loc", [])),
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        })
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": errors,
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions."""
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "detail": str(exc) if _is_debug() else None,
        },
    )


def _is_debug() -> bool:
    import os
    return os.environ.get("API_DEBUG", "").lower() in ("1", "true", "yes")


class RequestLogMiddleware:
    """Lightweight request logging middleware."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        import time
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        path = scope.get("path", "")
        method = scope.get("method", "")

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                elapsed_ms = (time.monotonic() - start) * 1000
                status = message.get("status", 0)
                if status >= 400:
                    print(f"  [{method}] {path} → {status} ({elapsed_ms:.0f}ms)")
            await send(message)

        await self.app(scope, receive, send_wrapper)


def register_error_handlers(app):
    """Register all exception handlers on the FastAPI app."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    app.add_middleware(RequestLogMiddleware)
