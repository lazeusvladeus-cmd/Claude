"""Клієнт для Gmail API (OAuth2).

КРИТИЧНО ВАЖЛИВО: цей клієнт НІКОЛИ не відправляє листи автоматично.
Він реалізує лише створення чернеток (`users.drafts.create`) та читання
тредів/повідомлень (`users.threads.get`) для перевірки відповідей.
Метод відправки (`users.messages.send`) у цьому класі свідомо
ВІДСУТНІЙ — фактичне надсилання завжди залишається ручною дією
користувача в інтерфейсі Gmail.
"""

from __future__ import annotations

import base64
import logging
from email.encoders import encode_base64
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.exceptions import AgentAuthError
from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)

# gmail.compose — створення чернеток; gmail.readonly — читання тредів для
# Модуля 5 (перевірка відповідей). Обидва скоупи НЕ дозволяють відправку.
SCOPES = (
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
)


class GmailClient:
    """Обгортка над Gmail API: лише чернетки та читання, ніколи відправка."""

    def __init__(self, credentials_file: str, token_file: str, *, dry_run: bool = False):
        """Ініціалізує клієнт.

        Args:
            credentials_file: шлях до credentials.json (OAuth Client ID
                типу "Desktop app"), завантаженого з Google Cloud Console.
            token_file: шлях, куди зберігати/звідки читати токен користувача
                після першої авторизації (створюється автоматично).
            dry_run: якщо True — жодної реальної авторизації чи звернень до
                Gmail API не відбувається, дії лише друкуються в консоль.
        """
        self._credentials_file = credentials_file
        self._token_file = token_file
        self._dry_run = dry_run
        self._service: Any = None

    def _get_service(self) -> Any:
        """Лениво створює авторизований Gmail API service (з кешуванням)."""
        if self._service is not None:
            return self._service

        creds: Credentials | None = None
        token_path = Path(self._token_file)
        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            except (ValueError, OSError) as exc:
                raise AgentAuthError(
                    f"Файл токена '{self._token_file}' пошкоджено або має "
                    f"неправильний формат ({exc}).\n"
                    f"Видаліть файл '{self._token_file}' та запустіть команду ще раз, "
                    "щоб пройти авторизацію в браузері заново."
                ) from exc

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as exc:
                    raise AgentAuthError(
                        "Токен доступу до Gmail протерміновано, і його не вдалося "
                        "оновити автоматично (можливо, доступ було відкликано).\n"
                        f"Виправлення: видаліть файл '{self._token_file}' і запустіть "
                        "будь-яку команду ще раз — відкриється браузер для повторної "
                        "авторизації. Див. SETUP.md, розділ 7."
                    ) from exc
            else:
                creds_path = Path(self._credentials_file)
                if not creds_path.exists():
                    raise AgentAuthError(
                        f"Файл '{self._credentials_file}' не знайдено.\n"
                        "Це файл credentials.json, який завантажується з Google Cloud "
                        "Console (OAuth 2.0 Client ID, тип 'Desktop app'). "
                        "Детальні кроки — у SETUP.md, розділ 3."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json(), encoding="utf-8")

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    @staticmethod
    def _build_message(
        *,
        to: str,
        subject: str,
        body_text: str,
        attachment_path: str | None = None,
        in_reply_to_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Формує тіло повідомлення Gmail API (base64url-encoded MIME)."""
        if attachment_path:
            mime_msg: MIMEMultipart | MIMEText = MIMEMultipart()
            mime_msg.attach(MIMEText(body_text, "plain", "utf-8"))
            attach_file = Path(attachment_path)
            part = MIMEBase(
                "application",
                "vnd.openxmlformats-officedocument.presentationml.presentation",
            )
            part.set_payload(attach_file.read_bytes())
            encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{attach_file.name}"')
            mime_msg.attach(part)
        else:
            mime_msg = MIMEText(body_text, "plain", "utf-8")

        mime_msg["to"] = to
        mime_msg["subject"] = subject
        if in_reply_to_message_id:
            mime_msg["In-Reply-To"] = in_reply_to_message_id
            mime_msg["References"] = in_reply_to_message_id

        raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")
        return {"raw": raw}

    @retry_with_backoff(max_attempts=3, base_delay_seconds=2.0, retryable_exceptions=(HttpError,))
    def create_draft(
        self,
        *,
        to: str,
        subject: str,
        body_text: str,
        thread_id: str | None = None,
        attachment_path: str | None = None,
        in_reply_to_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Створює чернетку листа в Gmail (users.drafts.create). НІКОЛИ не відправляє.

        Args:
            to: email отримувача.
            subject: тема листа.
            body_text: текст листа (plain text).
            thread_id: якщо задано — чернетка додається в існуючий тред
                (використовується для відповіді на лист клієнта).
            attachment_path: шлях до файлу-вкладення (наприклад, .pptx).
            in_reply_to_message_id: Message-ID листа, на який відповідаємо
                (для коректних заголовків In-Reply-To/References).

        Returns:
            Словник з ключами "id" (ID чернетки) та "threadId".
        """
        message_body = self._build_message(
            to=to,
            subject=subject,
            body_text=body_text,
            attachment_path=attachment_path,
            in_reply_to_message_id=in_reply_to_message_id,
        )
        if thread_id:
            message_body["threadId"] = thread_id

        if self._dry_run:
            logger.info("[DRY-RUN] Gmail.drafts.create(to=%r, subject=%r)", to, subject)
            print(
                f"[DRY-RUN] Було б створено чернетку листа для '{to}' "
                f"з темою '{subject}'"
                + (f" (з вкладенням {attachment_path})" if attachment_path else "")
                + ". Реального звернення до Gmail API НЕ виконано."
            )
            return {"id": "dry-run-draft-id", "threadId": thread_id or "dry-run-thread-id"}

        service = self._get_service()
        draft = (
            service.users().drafts().create(userId="me", body={"message": message_body}).execute()
        )
        return {
            "id": draft.get("id"),
            "threadId": draft.get("message", {}).get("threadId"),
        }

    @retry_with_backoff(max_attempts=3, base_delay_seconds=2.0, retryable_exceptions=(HttpError,))
    def get_thread(self, thread_id: str) -> dict[str, Any]:
        """Повертає повний тред (усі повідомлення) за ID (users.threads.get)."""
        if self._dry_run:
            logger.info("[DRY-RUN] Gmail.threads.get(thread_id=%r)", thread_id)
            print(f"[DRY-RUN] Було б перевірено тред '{thread_id}' на нові відповіді.")
            return {"id": thread_id, "messages": []}

        service = self._get_service()
        return service.users().threads().get(userId="me", id=thread_id, format="full").execute()
