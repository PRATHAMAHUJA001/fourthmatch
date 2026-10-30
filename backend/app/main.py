"""FourthMatch FastAPI app factory. create_all on startup (SQLite now)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.routers import deliveries, health, purchase_orders
from app.core.config import Settings, get_settings
from app.core.errors import AppError
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
    app.include_router(deliveries.router, prefix="/api")
    return app


app = create_app()
