"""Pure demo-gate logic: constant-time passcode check and a sliding-window limiter.

No fastapi / sqlalchemy imports. The clock is injectable so tests never sleep.
"""
from __future__ import annotations

import hmac
import threading
import time
from collections import deque
from collections.abc import Callable


def passcode_matches(provided: str | None, expected: str) -> bool:
    """Constant-time compare. An empty expected passcode never matches (feature off)."""
    if not expected or provided is None:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


class SlidingWindowLimiter:
    """At most ``limit`` accepted events in any rolling ``window_seconds``."""

    def __init__(
        self, limit: int, window_seconds: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: deque[float] = deque()
        self._lock = threading.Lock()

    def _evict(self, now: float) -> None:
        while self._events and now - self._events[0] >= self.window_seconds:
            self._events.popleft()

    def try_acquire(self) -> bool:
        """Record and accept one event, or reject without recording."""
        with self._lock:
            now = self._clock()
            self._evict(now)
            if len(self._events) >= self.limit:
                return False
            self._events.append(now)
            return True

    def retry_after_seconds(self) -> int:
        """Seconds until a slot frees up (0 if one is free now)."""
        with self._lock:
            now = self._clock()
            self._evict(now)
            if len(self._events) < self.limit:
                return 0
            return max(1, int(self.window_seconds - (now - self._events[0])) + 1)
