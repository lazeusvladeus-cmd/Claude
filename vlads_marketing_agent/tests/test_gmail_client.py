"""Тести GmailClient: OAuth-помилки, побудова MIME-повідомлень, dry-run."""

from __future__ import annotations

import base64
import json
from email import message_from_bytes
from email.header import decode_header

import pytest
from google.auth.exceptions import RefreshError

from src.clients.gmail_client import SCOPES, GmailClient
from src.exceptions import AgentAuthError


class TestAuthErrors:
    def test_missing_credentials_file_raises_agent_auth_error(self, tmp_path) -> None:
        client = GmailClient(
            credentials_file=str(tmp_path / "does_not_exist.json"),
            token_file=str(tmp_path / "token.json"),
            dry_run=False,
        )
        with pytest.raises(AgentAuthError, match="не знайдено"):
            client.create_draft(to="x@example.ua", subject="S", body_text="B")

    def test_corrupted_token_file_raises_agent_auth_error(self, tmp_path) -> None:
        token_path = tmp_path / "token.json"
        token_path.write_text("{not valid json", encoding="utf-8")
        creds_path = tmp_path / "credentials.json"
        creds_path.write_text(
            json.dumps({"installed": {"client_id": "x", "client_secret": "y"}}), encoding="utf-8"
        )

        client = GmailClient(
            credentials_file=str(creds_path), token_file=str(token_path), dry_run=False
        )
        with pytest.raises(AgentAuthError, match="пошкоджено"):
            client.create_draft(to="x@example.ua", subject="S", body_text="B")

    def test_expired_token_refresh_failure_raises_clear_message(self, tmp_path, mocker) -> None:
        token_path = tmp_path / "token.json"
        token_path.write_text("{}", encoding="utf-8")

        fake_creds = mocker.MagicMock()
        fake_creds.valid = False
        fake_creds.expired = True
        fake_creds.refresh_token = "some-refresh-token"
        fake_creds.refresh.side_effect = RefreshError("token revoked")

        mocker.patch(
            "src.clients.gmail_client.Credentials.from_authorized_user_file",
            return_value=fake_creds,
        )

        client = GmailClient(
            credentials_file=str(tmp_path / "credentials.json"),
            token_file=str(token_path),
            dry_run=False,
        )
        with pytest.raises(AgentAuthError, match="протермінов"):
            client.create_draft(to="x@example.ua", subject="S", body_text="B")


def _decode_header_value(msg, name: str) -> str:
    """Декодує заголовок листа (враховуючи RFC 2047 encoded-word для кирилиці)."""
    parts = decode_header(msg[name])
    return "".join(
        chunk.decode(encoding or "ascii") if isinstance(chunk, bytes) else chunk
        for chunk, encoding in parts
    )


class TestBuildMessage:
    def test_plain_message_has_correct_headers(self) -> None:
        body = GmailClient._build_message(to="a@b.ua", subject="Тема", body_text="Текст листа")
        raw_bytes = base64.urlsafe_b64decode(body["raw"])
        msg = message_from_bytes(raw_bytes)
        assert msg["to"] == "a@b.ua"
        assert _decode_header_value(msg, "subject") == "Тема"
        assert "Текст листа" in msg.get_payload(decode=True).decode("utf-8")

    def test_message_with_attachment_is_multipart(self, tmp_path) -> None:
        attachment = tmp_path / "presentation.pptx"
        attachment.write_bytes(b"fake-pptx-bytes")

        body = GmailClient._build_message(
            to="a@b.ua", subject="Тема", body_text="Текст", attachment_path=str(attachment)
        )
        raw_bytes = base64.urlsafe_b64decode(body["raw"])
        msg = message_from_bytes(raw_bytes)
        assert msg.is_multipart()
        filenames = [part.get_filename() for part in msg.walk() if part.get_filename()]
        assert "presentation.pptx" in filenames

    def test_reply_headers_set_when_in_reply_to_given(self) -> None:
        body = GmailClient._build_message(
            to="a@b.ua",
            subject="Re: Тема",
            body_text="Текст",
            in_reply_to_message_id="<orig@example.ua>",
        )
        raw_bytes = base64.urlsafe_b64decode(body["raw"])
        msg = message_from_bytes(raw_bytes)
        assert msg["In-Reply-To"] == "<orig@example.ua>"
        assert msg["References"] == "<orig@example.ua>"


class TestDryRun:
    def test_create_draft_dry_run_returns_placeholder_without_service(self) -> None:
        client = GmailClient(credentials_file="nope.json", token_file="nope.json", dry_run=True)
        result = client.create_draft(to="a@b.ua", subject="S", body_text="B")
        assert result["id"] == "dry-run-draft-id"

    def test_get_thread_dry_run_returns_empty_thread(self) -> None:
        client = GmailClient(credentials_file="nope.json", token_file="nope.json", dry_run=True)
        result = client.get_thread("thread-123")
        assert result["messages"] == []


class TestScopesNeverIncludeSend:
    def test_send_scope_not_requested(self) -> None:
        assert not any("send" in scope.lower() for scope in SCOPES)

    def test_gmail_client_has_no_send_method(self) -> None:
        assert not hasattr(GmailClient, "send")
