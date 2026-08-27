import time

from app.security import RateLimiter
from app.config import settings


def test_allowed_user_ids_parsed_from_csv_env():
    assert settings.allowed_user_ids == {111, 222}


def test_rate_limiter_allows_up_to_the_limit_then_blocks():
    limiter = RateLimiter(max_per_minute=3)
    user_id = 42
    assert limiter.allow(user_id) is True
    assert limiter.allow(user_id) is True
    assert limiter.allow(user_id) is True
    assert limiter.allow(user_id) is False  # 4th request within the window is blocked


def test_rate_limiter_is_independent_per_user():
    limiter = RateLimiter(max_per_minute=1)
    assert limiter.allow(1) is True
    assert limiter.allow(1) is False
    assert limiter.allow(2) is True  # different user, untouched by user 1's usage


def test_rate_limiter_window_slides(monkeypatch):
    limiter = RateLimiter(max_per_minute=1)
    fake_now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])

    assert limiter.allow(9) is True
    assert limiter.allow(9) is False

    fake_now[0] += 61  # past the 60s window
    assert limiter.allow(9) is True
