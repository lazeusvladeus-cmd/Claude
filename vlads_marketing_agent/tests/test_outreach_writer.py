"""Тести Модуля 4 (outreach_writer.py) з мокованим Gmail API та Claude API.

КРИТИЧНО ВАЖЛИВО: у кожному тесті, де використовується моковий Gmail
service, явно перевіряється, що метод відправки (users().messages().send)
НІКОЛИ не викликається — лише users().drafts().create().
"""

from __future__ import annotations

import json

import pytest

import outreach_writer
from src.db import get_lead, save_analysis, save_enrichment
from src.exceptions import AgentAuthError
from tests.conftest import load_fixture


def _make_mock_gmail_service(mocker, *, draft_id: str, thread_id: str):
    """Створює моковий Gmail service, де drafts().create().execute() повертає фейкову чернетку."""
    mock_service = mocker.MagicMock()
    drafts_create = mock_service.users.return_value.drafts.return_value.create
    drafts_create.return_value.execute.return_value = {
        "id": draft_id,
        "message": {"threadId": thread_id},
    }
    return mock_service


def _lead_with_email(
    sample_lead_factory, settings, *, place_id: str, name: str, email: str, weaknesses: list[str]
):
    lead_id = sample_lead_factory(
        place_id=place_id, name=name, website="https://example.ua", social_links="[]"
    )
    save_enrichment(settings.leads_db_path, lead_id, {"source": "website", "contact_email": email})
    save_analysis(settings.leads_db_path, lead_id, weaknesses)
    return lead_id


class TestParseEmailResponse:
    def test_parses_clean_json(self) -> None:
        fixture = load_fixture("claude_email_response.json")
        subject, body = outreach_writer.parse_email_response(
            json.dumps(fixture, ensure_ascii=False), "TERRAHOME"
        )
        assert subject == fixture["subject"]
        assert body == fixture["body"]

    def test_fallback_on_non_json_text(self) -> None:
        subject, body = outreach_writer.parse_email_response(
            "Пропозиція для кав'ярні\nТекст листа тут.", "Кав'ярня"
        )
        assert subject == "Пропозиція для кав'ярні"
        assert "Текст листа" in body


class TestRunDraft:
    def test_creates_gmail_draft_with_correct_fields(
        self, settings, sample_lead_factory, mocker
    ) -> None:
        lead_id = _lead_with_email(
            sample_lead_factory,
            settings,
            place_id="p1",
            name="TERRAHOME",
            email="info@terrahome.example",
            weaknesses=["Немає власного сайту."],
        )
        fixture = load_fixture("claude_email_response.json")
        mocker.patch(
            "outreach_writer.ClaudeClient.complete",
            return_value=json.dumps(fixture, ensure_ascii=False),
        )

        mock_service = _make_mock_gmail_service(
            mocker, draft_id="draft-123", thread_id="thread-abc"
        )
        mocker.patch("outreach_writer.GmailClient._get_service", return_value=mock_service)

        stats = outreach_writer.run_draft(settings, dry_run=False)

        assert stats.drafted == 1
        lead = get_lead(settings.leads_db_path, lead_id)
        assert lead.status == "drafted"
        assert lead.draft_id == "draft-123"
        assert lead.thread_id == "thread-abc"
        assert lead.email_subject == fixture["subject"]

        # Перевіряємо аргументи виклику drafts().create(...)
        create_call = mock_service.users.return_value.drafts.return_value.create
        _, kwargs = create_call.call_args
        assert kwargs["userId"] == "me"
        assert "message" in kwargs["body"]

        # КРИТИЧНО: метод відправки НІКОЛИ не має викликатись.
        mock_service.users.return_value.messages.return_value.send.assert_not_called()

    def test_send_is_never_called_even_indirectly(
        self, settings, sample_lead_factory, mocker
    ) -> None:
        """Явна перевірка на рівні всього GmailClient: send() не існує і не може бути викликаний."""
        _lead_with_email(
            sample_lead_factory,
            settings,
            place_id="p2",
            name="Комаха",
            email="hello@komaha.example",
            weaknesses=["Немає блогу."],
        )
        fixture = load_fixture("claude_email_response.json")
        mocker.patch(
            "outreach_writer.ClaudeClient.complete",
            return_value=json.dumps(fixture, ensure_ascii=False),
        )
        mock_service = _make_mock_gmail_service(
            mocker, draft_id="draft-999", thread_id="thread-999"
        )
        mocker.patch("outreach_writer.GmailClient._get_service", return_value=mock_service)

        outreach_writer.run_draft(settings, dry_run=False)

        assert not hasattr(
            outreach_writer.GmailClient, "send"
        ), "GmailClient не повинен мати методу send()"
        mock_service.users.return_value.messages.return_value.send.assert_not_called()

    def test_skips_lead_without_email(self, settings, sample_lead_factory) -> None:
        lead_id = sample_lead_factory(
            place_id="p3", name="БезEmail", website=None, social_links="[]"
        )
        save_enrichment(settings.leads_db_path, lead_id, {"source": "none"})
        save_analysis(settings.leads_db_path, lead_id, ["Щось"])

        stats = outreach_writer.run_draft(settings, dry_run=False)

        assert stats.skipped_no_email == 1
        assert stats.drafted == 0
        assert get_lead(settings.leads_db_path, lead_id).status == "analyzed"

    def test_empty_db_is_graceful(self, settings) -> None:
        stats = outreach_writer.run_draft(settings, dry_run=False)
        assert stats.processed == 0
        assert stats.drafted == 0

    def test_auth_error_propagates_clearly(self, settings, sample_lead_factory, mocker) -> None:
        _lead_with_email(
            sample_lead_factory,
            settings,
            place_id="p4",
            name="X",
            email="x@example.ua",
            weaknesses=["Щось"],
        )
        fixture = load_fixture("claude_email_response.json")
        mocker.patch(
            "outreach_writer.ClaudeClient.complete",
            return_value=json.dumps(fixture, ensure_ascii=False),
        )
        mocker.patch(
            "outreach_writer.GmailClient.create_draft",
            side_effect=AgentAuthError("Токен протерміновано, потрібна повторна авторизація."),
        )

        with pytest.raises(AgentAuthError, match="(?i)авторизац"):
            outreach_writer.run_draft(settings, dry_run=False)

    def test_dry_run_creates_no_drafts(self, settings, sample_lead_factory, mocker) -> None:
        lead_id = _lead_with_email(
            sample_lead_factory,
            settings,
            place_id="p5",
            name="Y",
            email="y@example.ua",
            weaknesses=["Щось"],
        )
        claude_spy = mocker.patch("outreach_writer.ClaudeClient.complete")
        gmail_spy = mocker.patch("outreach_writer.GmailClient.create_draft")

        stats = outreach_writer.run_draft(settings, dry_run=True)

        claude_spy.assert_not_called()
        gmail_spy.assert_not_called()
        assert stats.drafted == 0
        assert get_lead(settings.leads_db_path, lead_id).status == "analyzed"

    def test_writes_human_readable_report(
        self, settings, sample_lead_factory, mocker, tmp_path
    ) -> None:
        _lead_with_email(
            sample_lead_factory,
            settings,
            place_id="p6",
            name="Z",
            email="z@example.ua",
            weaknesses=["Щось"],
        )
        fixture = load_fixture("claude_email_response.json")
        mocker.patch(
            "outreach_writer.ClaudeClient.complete",
            return_value=json.dumps(fixture, ensure_ascii=False),
        )
        mock_service = _make_mock_gmail_service(mocker, draft_id="draft-1", thread_id="thread-1")
        mocker.patch("outreach_writer.GmailClient._get_service", return_value=mock_service)

        outreach_writer.run_draft(settings, dry_run=False)

        report_files = list((tmp_path / "logs").glob("drafts_report_*.txt"))
        assert len(report_files) == 1
        content = report_files[0].read_text(encoding="utf-8")
        assert "Z" in content
        assert "z@example.ua" in content
