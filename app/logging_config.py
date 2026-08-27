"""Logging setup that never accidentally writes secrets or full financial detail to disk."""
import logging
import re

from app.config import settings

_SECRET_PATTERNS = [
    re.compile(r"(bot\d+:[A-Za-z0-9_-]{20,})"),  # telegram bot tokens
    re.compile(r"(sk-[A-Za-z0-9]{20,})"),  # openai keys
]


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = msg
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactSecretsFilter())
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[handler],
    )
    # Quiet down noisy third-party loggers.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
