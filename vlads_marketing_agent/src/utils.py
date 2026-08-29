"""Дрібні спільні утиліти: retry з експоненційною затримкою тощо."""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
    retryable_exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Декоратор повторних спроб з експоненційною затримкою.

    Використовується для викликів зовнішніх API (Google Places, Anthropic,
    Gmail), які можуть тимчасово повертати помилки rate limit / мережі.
    Робить максимум `max_attempts` спроб із затримками
    base_delay, base_delay*2, base_delay*4, ... секунд між ними.

    Args:
        max_attempts: максимальна кількість спроб (типово 3).
        base_delay_seconds: базова затримка перед повтором у секундах.
        retryable_exceptions: кортеж класів винятків, при яких варто
            повторити спробу. Інші винятки одразу прокидаються далі.
        sleep_fn: функція "сну" (ін'єктується у тестах, щоб не чекати реально).

    Returns:
        Обгорнуту функцію, яка автоматично повторює виклик при збоях.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:  # noqa: BLE001 - навмисно широко
                    last_exc = exc
                    if attempt == max_attempts:
                        logger.error(
                            "Функція '%s' зазнала невдачі після %d спроб: %s",
                            func.__name__,
                            max_attempts,
                            exc,
                        )
                        raise
                    delay = base_delay_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "Спроба %d/%d функції '%s' невдала (%s). " "Повтор через %.1f с.",
                        attempt,
                        max_attempts,
                        func.__name__,
                        exc,
                        delay,
                    )
                    sleep_fn(delay)
            # Логічно недосяжно: цикл або повертає результат, або re-raise-ить.
            raise last_exc  # pragma: no cover

        return wrapper

    return decorator
