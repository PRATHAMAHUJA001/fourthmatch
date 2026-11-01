"""FourthMatch FastAPI app factory. create_all on startup (SQLite now)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.routers import cases, dashboard, deliveries, evidence, health, policies, purchase_orders
from app.core.config import Settings, get_settings
from app.core.errors import AppError, NotFoundError
from app.core.logging import configure_logging, get_request_id, set_request_id
from app.infra.db.session import create_all, make_engine


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        set_request_id(request.headers.get("x-request-id"))
        response = await call_next(request)
        response.headers["x-request-id"] = get_request_id()
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        create_all(make_engine())
        yield

    app = FastAPI(title="FourthMatch", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "request_id": get_request_id()}},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Internal error.", "request_id": get_request_id()}},
        )

    app.include_router(health.router, prefix="/api")
    app.include_router(purchase_orders.router, prefix="/api")
    app.include_router(cases.router, prefix="/api")
    app.include_router(deliveries.router, prefix="/api")
    app.include_router(policies.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(evidence.router, prefix="/api")
    _mount_spa(app, resolved.frontend_dist)
    return app


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA from this process. Registered last so /api routes win.

    Unknown /api paths raise the normal JSON error; any other GET falls back to
    index.html so client-side routes (/cases/3) survive a reload.
    """
    index = dist / "index.html"
    if not index.is_file():
        return
    root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise NotFoundError("No such API endpoint.", code="endpoint_not_found")
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        if full_path.startswith("assets/"):  # a missing hashed asset must 404, not return HTML
            raise NotFoundError("No such asset.", code="asset_not_found")
        return FileResponse(index)


app = create_app()
