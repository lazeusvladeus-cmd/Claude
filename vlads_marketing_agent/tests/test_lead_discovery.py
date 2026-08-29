"""Тести Модуля 1 (lead_discovery.py) з мокованими відповідями Google Places API."""

from __future__ import annotations

import pytest
import responses

import lead_discovery
from src.clients.google_places import GooglePlacesClient, PlacesAPIError, _split_website_and_social
from src.db import get_leads_by_status
from tests.conftest import load_fixture

_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def _mock_places(text_search_fixture: str, details_fixture: str) -> None:
    responses.add(
        responses.GET, _TEXT_SEARCH_URL, json=load_fixture(text_search_fixture), status=200
    )
    responses.add(responses.GET, _DETAILS_URL, json=load_fixture(details_fixture), status=200)


class TestSplitWebsiteAndSocial:
    def test_real_website_stays_website(self) -> None:
        website, social = _split_website_and_social("https://komaha-cafe.example.ua")
        assert website == "https://komaha-cafe.example.ua"
        assert social == []

    def test_instagram_link_becomes_social(self) -> None:
        website, social = _split_website_and_social("https://www.instagram.com/terrahome.lviv/")
        assert website is None
        assert social == ["https://www.instagram.com/terrahome.lviv/"]

    def test_none_website(self) -> None:
        website, social = _split_website_and_social(None)
        assert website is None
        assert social == []


class TestGooglePlacesClient:
    @responses.activate
    def test_search_businesses_cafe_full_data(self) -> None:
        _mock_places("places_text_search_cafe.json", "places_details_cafe.json")
        client = GooglePlacesClient("fake-key")

        leads = client.search_businesses("кав'ярні Львів")

        assert len(leads) == 1
        lead = leads[0]
        assert lead["place_id"] == "ChIJ_test_cafe_komaha_001"
        assert lead["name"] == "Кав'ярня Комаха"
        assert lead["website"] == "https://komaha-cafe.example.ua"
        assert lead["social_links"] == []
        assert lead["phone"] == "(032) 123 4567"
        assert lead["rating"] == 4.7
        assert lead["reviews_count"] == 312

    @responses.activate
    def test_search_businesses_no_website_extracts_social(self) -> None:
        _mock_places("places_text_search_furniture.json", "places_details_furniture.json")
        client = GooglePlacesClient("fake-key")

        leads = client.search_businesses("меблеві магазини Львів")

        assert len(leads) == 1
        lead = leads[0]
        assert lead["website"] is None
        assert lead["social_links"] == ["https://www.instagram.com/terrahome.lviv/"]
        assert lead["name"] == "TERRAHOME OUTDOOR, FURNITURE SHOWROOM"

    @responses.activate
    def test_search_businesses_no_site_no_social(self) -> None:
        _mock_places("places_text_search_nosite.json", "places_details_nosite.json")
        client = GooglePlacesClient("fake-key")

        leads = client.search_businesses("салони краси Львів")

        assert leads[0]["website"] is None
        assert leads[0]["social_links"] == []

    @responses.activate
    def test_text_search_retries_on_over_query_limit_then_succeeds(self) -> None:
        # Примітка: тут навмисно НЕ мокається time.sleep — retry_with_backoff
        # прив'язує посилання на time.sleep ще при імпорті модуля, тому тест
        # реально чекає ~2 секунди перед успішною другою спробою.
        fixture = load_fixture("places_text_search_cafe.json")
        responses.add(
            responses.GET,
            _TEXT_SEARCH_URL,
            json={"status": "OVER_QUERY_LIMIT", "results": []},
            status=200,
        )
        responses.add(responses.GET, _TEXT_SEARCH_URL, json=fixture, status=200)

        client = GooglePlacesClient("fake-key")
        results = client.text_search("кав'ярні Львів")

        assert len(results) == 1
        assert results[0]["place_id"] == "ChIJ_test_cafe_komaha_001"

    @responses.activate
    def test_text_search_raises_on_request_denied(self) -> None:
        responses.add(
            responses.GET,
            _TEXT_SEARCH_URL,
            json={"status": "REQUEST_DENIED", "error_message": "Invalid API key", "results": []},
            status=200,
        )
        client = GooglePlacesClient("fake-key")

        with pytest.raises(PlacesAPIError, match="REQUEST_DENIED"):
            client.text_search("кав'ярні Львів")

    def test_dry_run_makes_no_http_calls(self) -> None:
        client = GooglePlacesClient("fake-key", dry_run=True)
        # Без responses.activate() будь-який реальний HTTP-запит впаде з ConnectionError.
        leads = client.search_businesses("кав'ярні Львів")
        assert leads == []


class TestRunDiscovery:
    @responses.activate
    def test_creates_new_lead_in_db(self, settings) -> None:
        _mock_places("places_text_search_cafe.json", "places_details_cafe.json")

        stats = lead_discovery.run_discovery(settings, dry_run=False)

        assert stats.leads_created == 1
        assert stats.duplicates_skipped == 0
        new_leads = get_leads_by_status(settings.leads_db_path, "new")
        assert len(new_leads) == 1
        assert new_leads[0].name == "Кав'ярня Комаха"
        assert new_leads[0].status == "new"

    @responses.activate
    def test_dedup_skips_duplicate_on_second_run(self, settings) -> None:
        _mock_places("places_text_search_cafe.json", "places_details_cafe.json")
        lead_discovery.run_discovery(settings, dry_run=False)

        _mock_places("places_text_search_cafe.json", "places_details_cafe.json")
        stats_second = lead_discovery.run_discovery(settings, dry_run=False)

        assert stats_second.leads_created == 0
        assert stats_second.duplicates_skipped == 1
        assert len(get_leads_by_status(settings.leads_db_path, "new")) == 1

    @responses.activate
    def test_respects_max_new_leads_per_run(self, settings) -> None:
        settings.leads_config.searches[0]
        object.__setattr__(settings.leads_config, "max_new_leads_per_run", 0)
        _mock_places("places_text_search_cafe.json", "places_details_cafe.json")

        stats = lead_discovery.run_discovery(settings, dry_run=False)

        assert stats.leads_created == 0
        assert stats.searches_run == 0

    @responses.activate
    def test_search_failure_does_not_stop_pipeline(self, settings, mocker) -> None:
        mocker.patch.object(
            lead_discovery.GooglePlacesClient,
            "search_businesses",
            side_effect=PlacesAPIError("simulated outage"),
        )

        stats = lead_discovery.run_discovery(settings, dry_run=False)

        assert stats.searches_failed == 1
        assert stats.leads_created == 0

    @responses.activate
    def test_min_reviews_filter_skips_low_review_businesses(self, settings) -> None:
        object.__setattr__(settings.leads_config, "min_reviews_count", 1000)
        _mock_places("places_text_search_cafe.json", "places_details_cafe.json")

        stats = lead_discovery.run_discovery(settings, dry_run=False)

        assert stats.leads_created == 0
        assert stats.skipped_low_reviews == 1

    def test_dry_run_does_not_create_leads(self, settings) -> None:
        stats = lead_discovery.run_discovery(settings, dry_run=True)
        assert stats.leads_created == 0
        assert get_leads_by_status(settings.leads_db_path, "new") == []
