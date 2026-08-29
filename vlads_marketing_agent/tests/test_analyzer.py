"""Тести Модуля 3 (analyzer.py) з мокованим Anthropic (Claude) API."""

from __future__ import annotations

import json

import pytest

import analyzer
from src.db import get_lead
from tests.conftest import load_fixture


class FakeTextBlock:
    """Емуляція одного текстового блоку відповіді Anthropic SDK."""

    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class FakeAnthropicResponse:
    def __init__(self, text: str):
        self.content = [FakeTextBlock(text)]


def _mock_claude_complete(mocker, response_text: str):
    """Підміняє ClaudeClient.complete() на заданий текст без реального виклику API."""
    return mocker.patch("analyzer.ClaudeClient.complete", return_value=response_text)


class TestBuildAnalysisPrompt:
    def test_prompt_includes_only_real_data(self, sample_lead_factory, settings) -> None:
        lead_id = sample_lead_factory(
            place_id="p1",
            name="Кав'ярня Комаха",
            website="https://komaha-cafe.example.ua",
            social_links="[]",
        )
        from src.db import save_enrichment

        save_enrichment(
            settings.leads_db_path,
            lead_id,
            {
                "source": "website",
                "url": "https://komaha-cafe.example.ua",
                "has_online_ordering": False,
                "has_blog": False,
            },
        )
        lead = get_lead(settings.leads_db_path, lead_id)

        prompt = analyzer.build_analysis_prompt(lead)

        assert "Кав'ярня Комаха" in prompt
        assert "https://komaha-cafe.example.ua" in prompt
        # Немає вигаданих полів, яких не було у даних (наприклад, дати оновлення).
        assert "last_updated_guess" not in prompt

    def test_prompt_for_manual_screenshot_lead(self, sample_lead_factory, settings) -> None:
        from src.db import add_manual_data

        lead_id = sample_lead_factory(
            place_id="p2", name="Terrahome", website=None, social_links="[]"
        )
        add_manual_data(settings.leads_db_path, lead_id, "Instagram: акція -20%")
        lead = get_lead(settings.leads_db_path, lead_id)

        prompt = analyzer.build_analysis_prompt(lead)

        assert "Instagram: акція -20%" in prompt
        assert "скріншоту" in prompt


class TestParseWeaknessesResponse:
    def test_parses_clean_json(self) -> None:
        text = json.dumps({"weaknesses": ["А", "Б", "В"]}, ensure_ascii=False)
        assert analyzer.parse_weaknesses_response(text) == ["А", "Б", "В"]

    def test_parses_json_with_surrounding_text(self) -> None:
        text = 'Ось результат:\n{"weaknesses": ["Один", "Два"]}\nДякую.'
        assert analyzer.parse_weaknesses_response(text) == ["Один", "Два"]

    def test_parses_bullet_list_fallback(self) -> None:
        text = "- Перше слабке місце\n- Друге слабке місце\n- Третє"
        result = analyzer.parse_weaknesses_response(text)
        assert result == ["Перше слабке місце", "Друге слабке місце", "Третє"]

    def test_limits_to_five_items(self) -> None:
        text = json.dumps({"weaknesses": [f"Пункт {i}" for i in range(10)]})
        assert len(analyzer.parse_weaknesses_response(text)) == 5

    def test_raises_on_unparseable_text(self) -> None:
        with pytest.raises(ValueError):
            analyzer.parse_weaknesses_response("Повністю нерелевантна відповідь без структури.")


class TestRunAnalysis:
    def test_cafe_lead_analyzed(self, settings, sample_lead_factory, mocker) -> None:
        from src.db import save_enrichment

        lead_id = sample_lead_factory(
            place_id="p3", name="Кав'ярня Комаха", website="https://x.ua", social_links="[]"
        )
        save_enrichment(
            settings.leads_db_path, lead_id, {"source": "website", "url": "https://x.ua"}
        )
        fixture = load_fixture("claude_analysis_cafe.json")
        _mock_claude_complete(mocker, json.dumps(fixture, ensure_ascii=False))

        stats = analyzer.run_analysis(settings, dry_run=False)

        assert stats.analyzed == 1
        lead = get_lead(settings.leads_db_path, lead_id)
        assert lead.status == "analyzed"
        assert lead.weaknesses == fixture["weaknesses"]

    def test_furniture_lead_analyzed(self, settings, sample_lead_factory, mocker) -> None:
        from src.db import add_manual_data

        lead_id = sample_lead_factory(
            place_id="p4", name="Terrahome", website=None, social_links="[]"
        )
        add_manual_data(settings.leads_db_path, lead_id, "Instagram-профіль без сайту")
        fixture = load_fixture("claude_analysis_furniture.json")
        _mock_claude_complete(mocker, json.dumps(fixture, ensure_ascii=False))

        stats = analyzer.run_analysis(settings, dry_run=False)

        assert stats.analyzed == 1
        lead = get_lead(settings.leads_db_path, lead_id)
        assert lead.weaknesses == fixture["weaknesses"]

    def test_ecommerce_lead_analyzed(self, settings, sample_lead_factory, mocker) -> None:
        from src.db import save_enrichment

        lead_id = sample_lead_factory(
            place_id="p5", name="ShopUA", website="https://shopua.example", social_links="[]"
        )
        save_enrichment(
            settings.leads_db_path, lead_id, {"source": "website", "url": "https://shopua.example"}
        )
        fixture = load_fixture("claude_analysis_ecommerce.json")
        _mock_claude_complete(mocker, json.dumps(fixture, ensure_ascii=False))

        stats = analyzer.run_analysis(settings, dry_run=False)

        assert stats.analyzed == 1
        lead = get_lead(settings.leads_db_path, lead_id)
        assert lead.weaknesses == fixture["weaknesses"]

    def test_empty_db_is_graceful(self, settings) -> None:
        stats = analyzer.run_analysis(settings, dry_run=False)
        assert stats.processed == 0
        assert stats.analyzed == 0

    def test_claude_error_does_not_stop_other_leads(
        self, settings, sample_lead_factory, mocker
    ) -> None:
        from src.db import save_enrichment

        bad_id = sample_lead_factory(
            place_id="p6", name="Bad", website="https://bad.example", social_links="[]"
        )
        save_enrichment(
            settings.leads_db_path, bad_id, {"source": "website", "url": "https://bad.example"}
        )
        good_id = sample_lead_factory(
            place_id="p7", name="Good", website="https://good.example", social_links="[]"
        )
        save_enrichment(
            settings.leads_db_path, good_id, {"source": "website", "url": "https://good.example"}
        )

        fixture = load_fixture("claude_analysis_cafe.json")
        mocker.patch(
            "analyzer.ClaudeClient.complete",
            side_effect=[
                RuntimeError("simulated API failure"),
                json.dumps(fixture, ensure_ascii=False),
            ],
        )

        stats = analyzer.run_analysis(settings, dry_run=False)

        assert stats.errors == 1
        assert stats.analyzed == 1
        assert get_lead(settings.leads_db_path, bad_id).status == "enriched"
        assert get_lead(settings.leads_db_path, good_id).status == "analyzed"

    def test_dry_run_makes_no_api_calls_or_changes(
        self, settings, sample_lead_factory, mocker
    ) -> None:
        from src.db import save_enrichment

        lead_id = sample_lead_factory(
            place_id="p8", name="Комаха", website="https://x.ua", social_links="[]"
        )
        save_enrichment(
            settings.leads_db_path, lead_id, {"source": "website", "url": "https://x.ua"}
        )
        spy = mocker.patch("analyzer.ClaudeClient.complete")

        stats = analyzer.run_analysis(settings, dry_run=True)

        spy.assert_not_called()
        assert stats.analyzed == 0
        assert get_lead(settings.leads_db_path, lead_id).status == "enriched"
