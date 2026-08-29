"""Тонка обгортка над Anthropic (Claude) API.

Ізолює решту коду від деталей SDK `anthropic`, щоб:
  - модулі analyzer.py / outreach_writer.py / reply_monitor.py не залежали
    напряму від бібліотеки Anthropic;
  - у тестах можна було легко підмінити цей клієнт на mock;
  - retry/backoff та dry-run режим були реалізовані в одному місці.
"""

from __future__ import annotations

import logging

import anthropic

from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)

# Помилки Anthropic API, при яких має сенс повторити спробу
# (тимчасове перевантаження / rate limit / мережеві збої).
_RETRYABLE_ANTHROPIC_ERRORS: tuple[type[BaseException], ...] = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
)


class ClaudeClient:
    """Клієнт для викликів Claude API з retry та dry-run режимом."""

    def __init__(self, api_key: str, model: str, *, dry_run: bool = False):
        """Ініціалізує клієнт.

        Args:
            api_key: ключ Anthropic API (з .env, ANTHROPIC_API_KEY).
            model: ідентифікатор моделі Claude (з .env, ANTHROPIC_MODEL).
            dry_run: якщо True — реальні виклики API не виконуються,
                натомість повертається заглушка та друкується опис дії.
        """
        self._model = model
        self._dry_run = dry_run
        # У dry-run режимі клієнт може взагалі не мати валідного ключа —
        # SDK ініціалізується лише лінивою заглушкою (ключ не перевіряється
        # до першого реального виклику).
        self._client = anthropic.Anthropic(api_key=api_key or "dry-run-placeholder")

    @retry_with_backoff(
        max_attempts=3, base_delay_seconds=2.0, retryable_exceptions=_RETRYABLE_ANTHROPIC_ERRORS
    )
    def _call(self, *, system: str, user_prompt: str, max_tokens: int) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text_parts = [
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ]
        return "\n".join(text_parts).strip()

    def complete(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int = 1024,
        dry_run_label: str = "Claude API виклик",
    ) -> str:
        """Виконує один виклик Claude API (system + user prompt) і повертає текст відповіді.

        Args:
            system: системний промпт (роль/інструкція для моделі).
            user_prompt: конкретне завдання/дані для цього виклику.
            max_tokens: максимальна довжина відповіді в токенах.
            dry_run_label: назва дії для виводу в консоль у dry-run режимі.

        Returns:
            Текст відповіді моделі (без обгортки JSON API).
        """
        if self._dry_run:
            logger.info("[DRY-RUN] %s (model=%s)", dry_run_label, self._model)
            print(f"[DRY-RUN] {dry_run_label}: реальний виклик Claude API НЕ виконується.")
            return ""
        return self._call(system=system, user_prompt=user_prompt, max_tokens=max_tokens)
