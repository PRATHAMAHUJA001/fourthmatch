"""Demo-mode gate for live uploads: passcode header + rolling per-hour cap."""
from __future__ import annotations

from fastapi import Depends, Header, Request

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.core.errors import ForbiddenError, RateLimitError
from app.domain.rate_limit import SlidingWindowLimiter, passcode_matches

WINDOW_SECONDS = 3600.0


def _limiter_for(request: Request, limit: int) -> SlidingWindowLimiter:
    limiter: SlidingWindowLimiter | None = getattr(request.app.state, "upload_limiter", None)
    if limiter is None or limiter.limit != limit:
        limiter = SlidingWindowLimiter(limit, WINDOW_SECONDS)
        request.app.state.upload_limiter = limiter
    return limiter


def require_demo_passcode(
    x_demo_passcode: str | None = Header(default=None),
    settings: Settings = Depends(get_app_settings),
) -> None:
    """No-op unless DEMO_MODE. Then every write (and every model-calling route) needs the passcode."""
    if not settings.demo_mode:
        return
    if not settings.demo_passcode:
        raise ForbiddenError("Changes are disabled on this demo.", code="live_uploads_disabled")
    if not passcode_matches(x_demo_passcode, settings.demo_passcode):
        raise ForbiddenError("A valid demo passcode is required for this action.", code="demo_passcode_required")


def require_live_upload(
    request: Request,
    x_demo_passcode: str | None = Header(default=None),
    settings: Settings = Depends(get_app_settings),
) -> None:
    """No-op unless DEMO_MODE. Then: valid passcode (else 403), then quota (else 429)."""
    if not settings.demo_mode:
        return
    require_demo_passcode(x_demo_passcode, settings)
    limiter = _limiter_for(request, settings.live_upload_limit_per_hour)
    if not limiter.try_acquire():
        raise RateLimitError(
            f"Live upload limit reached ({settings.live_upload_limit_per_hour} per hour). "
            f"Try again in about {max(1, limiter.retry_after_seconds() // 60)} minute(s).",
            code="upload_rate_limited",
        )
