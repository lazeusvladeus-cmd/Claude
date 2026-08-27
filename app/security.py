"""Everything that keeps this bot from being anyone's business but yours.

Two independent guards:
1. AllowlistMiddleware — hard-rejects any Telegram user not in ALLOWED_TELEGRAM_USER_IDS,
   before any handler (and therefore before any OpenAI/Google API call) runs.
2. RateLimiter — caps how many "expensive" (OpenAI-backed) actions a user can trigger
   per minute, so a bug, a retry storm, or a stranger who somehow slips through can't
   run up your OpenAI bill.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.config import settings

logger = logging.getLogger(__name__)


class AllowlistMiddleware(BaseMiddleware):
    """Silently drops (with a log line) any update from a non-owner user.

    We intentionally do NOT reply to unknown users beyond one polite message per
    session-ish, to avoid turning the bot into an oracle that confirms it exists
    and is worth attacking.
    """

    def __init__(self) -> None:
        self._warned_users: set[int] = set()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")

        if user is None:
            return await handler(event, data)

        if user.id not in settings.allowed_user_ids:
            logger.warning("Blocked message from non-owner Telegram user_id=%s (@%s)", user.id, user.username)
            if user.id not in self._warned_users:
                self._warned_users.add(user.id)
                message = getattr(event, "message", None)
                if message is not None:
                    try:
                        await message.answer("This bot is private and not available to you.")
                    except Exception:
                        pass
            return None  # swallow the update; handler never runs

        return await handler(event, data)


class RateLimiter:
    """Simple in-memory sliding-window limiter, per user, for OpenAI-backed actions."""

    def __init__(self, max_per_minute: int | None = None) -> None:
        self.max_per_minute = max_per_minute or settings.rate_limit_per_minute
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        window = self._hits[user_id]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.max_per_minute:
            return False
        window.append(now)
        return True


rate_limiter = RateLimiter()
