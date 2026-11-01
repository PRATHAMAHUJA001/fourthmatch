"""One AppError hierarchy. API maps it to {error: {code, message, request_id}}."""
from __future__ import annotations


class AppError(Exception):
    code = "app_error"
    status_code = 500

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422


class ConflictError(AppError):
    code = "conflict"
    status_code = 409


class ForbiddenError(AppError):
    code = "forbidden"
    status_code = 403


class RateLimitError(AppError):
    code = "rate_limited"
    status_code = 429


class UpstreamModelError(AppError):
    code = "model_upstream"
    status_code = 502


class CacheError(AppError):
    code = "cache_error"
    status_code = 500
