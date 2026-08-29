"""Налаштування логування агента.

Логи одночасно пишуться в консоль (для інтерактивного запуску) та у файл
`logs/agent.log` з ротацією (щоб файл не ріс безмежно). Використовується
стандартний модуль `logging`, а не `print`, щоб рівні (INFO/WARNING/ERROR)
можна було фільтрувати та щоб логи були придатні для продакшн-моніторингу.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Патерн для маскування можливих секретів у повідомленнях логів (про всяк
# випадок — навіть якщо хтось випадково передасть ключ у f-string).
_SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{10,}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
)


class SecretMaskingFilter(logging.Filter):
    """Фільтр логів, що замінює схожі на API-ключі підрядки на "***"."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = message
        for pattern in _SECRET_PATTERNS:
            masked = pattern.sub("***MASKED***", masked)
        if masked != message:
            record.msg = masked
            record.args = ()
        return True


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> None:
    """Ініціалізує кореневий логер агента (консоль + файл з ротацією).

    Args:
        log_dir: директорія для файлу логів (створюється, якщо відсутня).
        level: рівень логування ("DEBUG", "INFO", "WARNING", "ERROR").
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Уникаємо дублювання хендлерів при повторних викликах (наприклад, у тестах).
    root.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SecretMaskingFilter())
    root.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        log_path / "agent.log",
        maxBytes=5 * 1024 * 1024,  # 5 МБ на файл
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SecretMaskingFilter())
    root.addHandler(file_handler)
