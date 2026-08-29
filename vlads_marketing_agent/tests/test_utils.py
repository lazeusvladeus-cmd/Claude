"""Тести retry-декоратора з експоненційною затримкою (src/utils.py)."""

from __future__ import annotations

import pytest

from src.utils import retry_with_backoff


class FlakyError(Exception):
    pass


class TestRetryWithBackoff:
    def test_succeeds_immediately_without_retry(self) -> None:
        calls = []

        @retry_with_backoff(
            max_attempts=3, base_delay_seconds=0.01, sleep_fn=lambda s: calls.append(s)
        )
        def always_ok():
            return "ok"

        assert always_ok() == "ok"
        assert calls == []

    def test_retries_and_eventually_succeeds(self) -> None:
        attempts = {"count": 0}
        sleeps = []

        @retry_with_backoff(
            max_attempts=3,
            base_delay_seconds=0.01,
            retryable_exceptions=(FlakyError,),
            sleep_fn=lambda s: sleeps.append(s),
        )
        def flaky():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise FlakyError("temporary")
            return "recovered"

        assert flaky() == "recovered"
        assert attempts["count"] == 3
        assert sleeps == [0.01, 0.02]  # експоненційне зростання

    def test_raises_after_exhausting_all_attempts(self) -> None:
        sleeps = []

        @retry_with_backoff(
            max_attempts=3,
            base_delay_seconds=0.01,
            retryable_exceptions=(FlakyError,),
            sleep_fn=lambda s: sleeps.append(s),
        )
        def always_fails():
            raise FlakyError("permanent")

        with pytest.raises(FlakyError):
            always_fails()
        assert len(sleeps) == 2  # 2 затримки між 3 спробами

    def test_non_retryable_exception_propagates_immediately(self) -> None:
        sleeps = []

        @retry_with_backoff(
            max_attempts=3,
            base_delay_seconds=0.01,
            retryable_exceptions=(FlakyError,),
            sleep_fn=lambda s: sleeps.append(s),
        )
        def raises_other():
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            raises_other()
        assert sleeps == []
