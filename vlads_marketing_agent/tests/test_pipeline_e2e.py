"""End-to-end тест повного пайплайну: від "новий лід знайдено" до "чернетка
з презентацією створена". Усі зовнішні API (Google Places, Claude, Gmail)
замоковано — жодного реального мережевого виклику не виконується.
"""

from __future__ import annotations

import json

import responses

import analyzer
import enrichment
import lead_discovery
import outreach_writer
import reply_monitor
from src.db import get_lead
from tests.conftest import load_fixture
from tests.test_reply_monitor import _make_message

_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

_WEBSITE_HTML = """
<html>
<head><meta name="description" content="Затишна кав'ярня в центрі Львова"></head>
<body>
  <p>Замовити каву можна онлайн.</p>
  <p>Пишіть нам: hello@komaha-cafe.example.ua</p>
  <footer>&copy; 2021 Кав'ярня Комаха.</footer>
</body>
</html>
"""


@responses.activate
def test_full_pipeline_new_lead_to_presented(settings, mocker) -> None:
    # --- Модуль 1: Discover ---------------------------------------------
    responses.add(
        responses.GET,
        _TEXT_SEARCH_URL,
        json=load_fixture("places_text_search_cafe.json"),
        status=200,
    )
    responses.add(
        responses.GET, _DETAILS_URL, json=load_fixture("places_details_cafe.json"), status=200
    )

    discover_stats = lead_discovery.run_discovery(settings, dry_run=False)
    assert discover_stats.leads_created == 1

    # --- Модуль 2: Enrich --------------------------------------------------
    responses.add(responses.GET, "https://komaha-cafe.example.ua", body=_WEBSITE_HTML, status=200)
    enrich_stats = enrichment.run_enrichment(settings, dry_run=False)
    assert enrich_stats.enriched_from_website == 1

    # --- Модуль 3: Analyze (Claude мокований) -------------------------------
    analysis_fixture = load_fixture("claude_analysis_cafe.json")
    mocker.patch(
        "analyzer.ClaudeClient.complete",
        return_value=json.dumps(analysis_fixture, ensure_ascii=False),
    )
    analyze_stats = analyzer.run_analysis(settings, dry_run=False)
    assert analyze_stats.analyzed == 1

    # --- Модуль 4: Draft (Claude + Gmail мокований) -------------------------
    email_fixture = load_fixture("claude_email_response.json")
    mocker.patch(
        "outreach_writer.ClaudeClient.complete",
        return_value=json.dumps(email_fixture, ensure_ascii=False),
    )
    mock_gmail_service = mocker.MagicMock()
    drafts_create = mock_gmail_service.users.return_value.drafts.return_value.create
    drafts_create.return_value.execute.return_value = {
        "id": "draft-e2e-1",
        "message": {"threadId": "thread-e2e-1"},
    }
    mocker.patch("outreach_writer.GmailClient._get_service", return_value=mock_gmail_service)

    draft_stats = outreach_writer.run_draft(settings, dry_run=False)
    assert draft_stats.drafted == 1

    from src.db import get_leads_by_status

    drafted_leads = get_leads_by_status(settings.leads_db_path, "drafted")
    assert len(drafted_leads) == 1
    lead_id = drafted_leads[0].id
    assert get_lead(settings.leads_db_path, lead_id).status == "drafted"

    # send() ніколи не викликається на жодному етапі пайплайну.
    mock_gmail_service.users.return_value.messages.return_value.send.assert_not_called()

    # --- Модуль 5: Reply Monitor (виявлення відповіді + презентація) -------
    thread_with_reply = {
        "messages": [
            _make_message(
                from_addr=settings.gmail_sender_email,
                text="Наш лист",
                label_sent=True,
                internal_date_ms=1000,
                message_id="m1",
            ),
            _make_message(
                from_addr="hello@komaha-cafe.example.ua",
                text="Дякую, дуже цікаво! Надішліть, будь ласка, план.",
                label_sent=False,
                internal_date_ms=2000,
                message_id="m2",
            ),
        ]
    }
    mocker.patch("reply_monitor.GmailClient.get_thread", return_value=thread_with_reply)
    ideas_fixture = load_fixture("claude_ideas_response.json")
    mocker.patch(
        "reply_monitor.ClaudeClient.complete",
        return_value=json.dumps(ideas_fixture, ensure_ascii=False),
    )
    drafts_create.return_value.execute.return_value = {
        "id": "reply-draft-e2e-1",
        "message": {"threadId": "thread-e2e-1"},
    }
    mocker.patch("reply_monitor.GmailClient._get_service", return_value=mock_gmail_service)

    reply_stats = reply_monitor.check_replies(settings, dry_run=False)

    assert reply_stats.marked_sent == 1
    assert reply_stats.presented == 1

    final_lead = get_lead(settings.leads_db_path, lead_id)
    assert final_lead.status == "presented"
    assert final_lead.presentation_path is not None

    from pathlib import Path

    assert Path(final_lead.presentation_path).exists()

    # Ще раз перевіряємо на завершальному етапі: send() не викликано жодного разу.
    mock_gmail_service.users.return_value.messages.return_value.send.assert_not_called()
