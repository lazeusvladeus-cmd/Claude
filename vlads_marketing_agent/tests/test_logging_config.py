"""Тести налаштування логування (src/logging_config.py)."""

from __future__ import annotations

import logging

from src.logging_config import SecretMaskingFilter, setup_logging


class TestSetupLogging:
    def test_creates_log_directory_and_file(self, tmp_path) -> None:
        log_dir = tmp_path / "logs"
        setup_logging(str(log_dir), "INFO")

        logger = logging.getLogger("test_logger")
        logger.info("Тестове повідомлення")
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert (log_dir / "agent.log").exists()
        content = (log_dir / "agent.log").read_text(encoding="utf-8")
        assert "Тестове повідомлення" in content

    def test_respects_log_level(self, tmp_path) -> None:
        setup_logging(str(tmp_path / "logs"), "WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_repeated_setup_does_not_duplicate_handlers(self, tmp_path) -> None:
        setup_logging(str(tmp_path / "logs"), "INFO")
        setup_logging(str(tmp_path / "logs"), "INFO")
        assert len(logging.getLogger().handlers) == 2  # консоль + файл


class TestSecretMaskingFilter:
    def test_masks_anthropic_key_in_message(self) -> None:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Ключ: sk-ant-abcdef1234567890abcdef",
            args=(),
            exc_info=None,
        )
        SecretMaskingFilter().filter(record)
        assert "sk-ant-" not in record.getMessage()
        assert "MASKED" in record.getMessage()

    def test_masks_google_key_in_message(self) -> None:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Ключ: AIzaSyD1234567890ABCDEFGHIJKLMNOPQRSTU",
            args=(),
            exc_info=None,
        )
        SecretMaskingFilter().filter(record)
        assert "MASKED" in record.getMessage()

    def test_leaves_normal_messages_untouched(self) -> None:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Звичайне повідомлення без секретів",
            args=(),
            exc_info=None,
        )
        SecretMaskingFilter().filter(record)
        assert record.getMessage() == "Звичайне повідомлення без секретів"
