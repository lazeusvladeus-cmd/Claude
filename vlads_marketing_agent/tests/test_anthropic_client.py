"""Тести ClaudeClient (src/clients/anthropic_client.py): retry, dry-run."""

from __future__ import annotations

from unittest.mock import MagicMock

import anthropic
import pytest

from src.clients.anthropic_client import ClaudeClient


class FakeTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class FakeResponse:
    def __init__(self, text: str):
        self.content = [FakeTextBlock(text)]


def _connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(message="simulated network error", request=MagicMock())


class TestClaudeClientDryRun:
    def test_dry_run_returns_empty_without_real_call(self, mocker) -> None:
        client = ClaudeClient("sk-ant-fake", "claude-sonnet-4-6", dry_run=True)
        create_spy = mocker.patch.object(client._client.messages, "create")

        result = client.complete(system="sys", user_prompt="prompt")

        assert result == ""
        create_spy.assert_not_called()


class TestClaudeClientRealCalls:
    def test_returns_joined_text_blocks(self, mocker) -> None:
        client = ClaudeClient("sk-ant-fake", "claude-sonnet-4-6", dry_run=False)
        mocker.patch.object(client._client.messages, "create", return_value=FakeResponse("Привіт!"))

        result = client.complete(system="sys", user_prompt="prompt")

        assert result == "Привіт!"

    def test_retries_on_connection_error_then_succeeds(self, mocker) -> None:
        # Примітка: retry_with_backoff прив'язує time.sleep ще при імпорті
        # модуля, тому цей тест реально чекає ~2 секунди перед другою спробою.
        client = ClaudeClient("sk-ant-fake", "claude-sonnet-4-6", dry_run=False)
        mocker.patch.object(
            client._client.messages,
            "create",
            side_effect=[_connection_error(), FakeResponse("Відновлено")],
        )

        result = client.complete(system="sys", user_prompt="prompt")
        assert result == "Відновлено"

    def test_raises_after_exhausting_retries(self, mocker) -> None:
        client = ClaudeClient("sk-ant-fake", "claude-sonnet-4-6", dry_run=False)
        mocker.patch.object(client._client.messages, "create", side_effect=_connection_error())

        with pytest.raises(anthropic.APIConnectionError):
            client.complete(system="sys", user_prompt="prompt")
