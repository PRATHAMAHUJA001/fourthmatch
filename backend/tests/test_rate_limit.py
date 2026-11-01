"""Pure demo-gate logic: passcode compare + sliding-window limiter. No I/O, no sleeping."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.domain.rate_limit import SlidingWindowLimiter, passcode_matches  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_passcode_matches_exact_only() -> None:
    assert passcode_matches("s3cret", "s3cret")
    assert not passcode_matches("s3cre", "s3cret")
    assert not passcode_matches("S3CRET", "s3cret")
    assert not passcode_matches(None, "s3cret")


def test_empty_expected_passcode_never_matches() -> None:
    assert not passcode_matches("", "")
    assert not passcode_matches(None, "")


def test_limiter_allows_up_to_limit_then_rejects() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(3, 3600, clock)
    assert [limiter.try_acquire() for _ in range(5)] == [True, True, True, False, False]


def test_rejected_attempts_are_not_recorded() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(1, 100, clock)
    assert limiter.try_acquire()
    clock.now += 50
    assert not limiter.try_acquire()  # must not push the window forward
    clock.now += 51  # 101s after the single accepted event
    assert limiter.try_acquire()


def test_window_slides_one_event_at_a_time() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(2, 100, clock)
    assert limiter.try_acquire()      # t=0
    clock.now += 60
    assert limiter.try_acquire()      # t=60
    assert not limiter.try_acquire()
    clock.now += 41                   # t=101: first expired, second not
    assert limiter.try_acquire()
    assert not limiter.try_acquire()


def test_retry_after_seconds() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(1, 100, clock)
    assert limiter.retry_after_seconds() == 0
    limiter.try_acquire()
    clock.now += 40
    assert 60 <= limiter.retry_after_seconds() <= 61


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        SlidingWindowLimiter(0)
    with pytest.raises(ValueError):
        SlidingWindowLimiter(1, 0)
