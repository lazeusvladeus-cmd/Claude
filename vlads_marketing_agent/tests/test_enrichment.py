"""Тести Модуля 2 (enrichment.py) з мокованими HTTP-запитами до сайтів."""

from __future__ import annotations

import json

import requests
import responses

import enrichment
from src.db import get_lead

_WORKING_SITE_HTML = """
<html>
<head><meta name="description" content="Затишна кав'ярня в центрі Львова"></head>
<body>
  <nav><a href="/blog">Блог</a></nav>
  <p>Ласкаво просимо! Замовити каву можна онлайн, оформити замовлення тут.</p>
  <p>Пишіть нам: hello@komaha-cafe.example.ua</p>
  <footer>&copy; 2021 Кав'ярня Комаха. Тел: +380 32 123 45 67</footer>
</body>
</html>
"""

_MINIMAL_SITE_HTML = "<html><body><p>Просто текст без корисних даних.</p></body></html>"


class TestFetchAndParseWebsite:
    @responses.activate
    def test_working_site_extracts_all_fields(self) -> None:
        responses.add(
            responses.GET, "https://komaha-cafe.example.ua", body=_WORKING_SITE_HTML, status=200
        )

        data = enrichment.fetch_and_parse_website("https://komaha-cafe.example.ua")

        assert data["fetch_error"] is None
        assert data["description"] == "Затишна кав'ярня в центрі Львова"
        assert data["has_online_ordering"] is True
        assert data["has_blog"] is True
        assert data["contact_email"] == "hello@komaha-cafe.example.ua"
        assert data["contact_phone_found"] is True
        assert data["last_updated_guess"] == "2021"

    @responses.activate
    def test_site_timeout(self) -> None:
        responses.add(
            responses.GET,
            "https://slow-site.example.ua",
            body=requests.exceptions.Timeout("simulated timeout"),
        )

        data = enrichment.fetch_and_parse_website("https://slow-site.example.ua")

        assert data["fetch_error"] is not None
        assert (
            "timeout" in data["fetch_error"].lower() or "очікування" in data["fetch_error"].lower()
        )

    @responses.activate
    def test_site_404(self) -> None:
        responses.add(responses.GET, "https://missing-site.example.ua", status=404)

        data = enrichment.fetch_and_parse_website("https://missing-site.example.ua")

        assert data["fetch_error"] is not None
        assert "404" in data["fetch_error"]

    @responses.activate
    def test_site_without_useful_data(self) -> None:
        responses.add(
            responses.GET, "https://empty-site.example.ua", body=_MINIMAL_SITE_HTML, status=200
        )

        data = enrichment.fetch_and_parse_website("https://empty-site.example.ua")

        assert data["fetch_error"] is None
        assert data["has_online_ordering"] is False
        assert data["has_blog"] is False
        assert data["contact_email"] is None

    @responses.activate
    def test_connection_error(self) -> None:
        responses.add(
            responses.GET,
            "https://unreachable.example.ua",
            body=requests.exceptions.ConnectionError("simulated connection error"),
        )

        data = enrichment.fetch_and_parse_website("https://unreachable.example.ua")

        assert data["fetch_error"] is not None


class TestRunEnrichment:
    @responses.activate
    def test_website_lead_becomes_enriched(self, settings, sample_lead_factory) -> None:
        responses.add(
            responses.GET, "https://komaha-cafe.example.ua", body=_WORKING_SITE_HTML, status=200
        )
        lead_id = sample_lead_factory(
            place_id="p1",
            name="Комаха",
            website="https://komaha-cafe.example.ua",
            social_links="[]",
        )

        stats = enrichment.run_enrichment(settings, dry_run=False)

        assert stats.enriched_from_website == 1
        lead = get_lead(settings.leads_db_path, lead_id)
        assert lead.status == "enriched"
        assert lead.enrichment["has_online_ordering"] is True

    def test_social_link_lead_needs_manual_screenshot(self, settings, sample_lead_factory) -> None:
        lead_id = sample_lead_factory(
            place_id="p2",
            name="Terrahome",
            website=None,
            social_links=json.dumps(["https://www.instagram.com/terrahome.lviv/"]),
        )

        stats = enrichment.run_enrichment(settings, dry_run=False)

        assert stats.needs_manual_screenshot == 1
        lead = get_lead(settings.leads_db_path, lead_id)
        assert lead.status == "needs_manual_screenshot"

    def test_lead_without_site_or_social_still_enriched(
        self, settings, sample_lead_factory
    ) -> None:
        lead_id = sample_lead_factory(
            place_id="p3", name="БезСайту", website=None, social_links="[]"
        )

        stats = enrichment.run_enrichment(settings, dry_run=False)

        assert stats.enriched_without_data == 1
        lead = get_lead(settings.leads_db_path, lead_id)
        assert lead.status == "enriched"
        assert lead.enrichment["source"] == "none"

    def test_empty_db_is_graceful(self, settings) -> None:
        stats = enrichment.run_enrichment(settings, dry_run=False)
        assert stats.processed == 0
        assert stats.as_dict() == {
            "processed": 0,
            "enriched_from_website": 0,
            "needs_manual_screenshot": 0,
            "enriched_without_data": 0,
            "website_errors": 0,
        }

    @responses.activate
    def test_website_error_does_not_stop_other_leads(self, settings, sample_lead_factory) -> None:
        responses.add(responses.GET, "https://broken-site.example.ua", status=404)
        responses.add(
            responses.GET, "https://komaha-cafe.example.ua", body=_WORKING_SITE_HTML, status=200
        )
        broken_id = sample_lead_factory(
            place_id="p4",
            name="Broken",
            website="https://broken-site.example.ua",
            social_links="[]",
        )
        ok_id = sample_lead_factory(
            place_id="p5", name="OK", website="https://komaha-cafe.example.ua", social_links="[]"
        )

        stats = enrichment.run_enrichment(settings, dry_run=False)

        assert stats.website_errors == 1
        assert stats.enriched_from_website == 1
        broken_lead = get_lead(settings.leads_db_path, broken_id)
        ok_lead = get_lead(settings.leads_db_path, ok_id)
        # Обидва все одно переходять у 'enriched', щоб не зупиняти пайплайн;
        # помилка сайту зберігається як факт для подальшого аналізу.
        assert broken_lead.status == "enriched"
        assert broken_lead.enrichment["fetch_error"] is not None
        assert ok_lead.status == "enriched"

    def test_dry_run_makes_no_changes(self, settings, sample_lead_factory) -> None:
        lead_id = sample_lead_factory(
            place_id="p6",
            name="Комаха",
            website="https://komaha-cafe.example.ua",
            social_links="[]",
        )

        stats = enrichment.run_enrichment(settings, dry_run=True)

        assert stats.enriched_from_website == 0
        lead = get_lead(settings.leads_db_path, lead_id)
        assert lead.status == "new"


class TestAddManualData:
    def test_add_manual_data_transitions_to_enriched(self, settings, sample_lead_factory) -> None:
        lead_id = sample_lead_factory(
            place_id="p7", name="Terrahome", website=None, social_links="[]"
        )

        enrichment.add_manual_data(
            settings, lead_id, "Instagram-пост: акція -20% на весь асортимент."
        )

        lead = get_lead(settings.leads_db_path, lead_id)
        assert lead.status == "enriched"
        assert "акція" in lead.manual_screenshot_text
        assert lead.enrichment["source"] == "manual_screenshot"
