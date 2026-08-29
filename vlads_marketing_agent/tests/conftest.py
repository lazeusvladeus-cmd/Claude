"""Спільні pytest-фікстури для всіх тестів агента."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from src.config import LeadsSearchConfig, SearchQuery, Settings
from src.db import init_db, upsert_lead

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Завантажує JSON-фікстуру за іменем файлу з tests/fixtures/."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Створює порожню тестову SQLite базу лідів у тимчасовій директорії."""
    path = str(tmp_path / "leads_test.db")
    init_db(path)
    return path


@pytest.fixture
def leads_search_config() -> LeadsSearchConfig:
    """Мінімальна валідна конфігурація пошуку для тестів."""
    return LeadsSearchConfig(
        searches=(SearchQuery(category="кав'ярні", location="Львів"),),
        max_new_leads_per_run=20,
        max_results_per_search=20,
        min_reviews_count=0,
    )


@pytest.fixture
def settings(tmp_path: Path, db_path: str, leads_search_config: LeadsSearchConfig) -> Settings:
    """Повний об'єкт Settings із безпечними тестовими значеннями (без реальних ключів)."""
    return Settings(
        google_places_api_key="test-places-key",
        anthropic_api_key="sk-ant-test-key-1234567890",
        anthropic_model="claude-sonnet-4-6",
        gmail_credentials_file=str(tmp_path / "credentials.json"),
        gmail_token_file=str(tmp_path / "token.json"),
        gmail_sender_email="vlad@vladsmarketing.example",
        leads_db_path=db_path,
        leads_config_path=str(tmp_path / "leads_config.yaml"),
        check_replies_interval_minutes=60,
        presentations_dir=str(tmp_path / "presentations"),
        log_level="INFO",
        log_dir=str(tmp_path / "logs"),
        leads_config=leads_search_config,
    )


@pytest.fixture
def sample_lead_factory(db_path: str) -> Callable[..., int]:
    """Фабрика для швидкого створення тестового ліда в БД із заданими полями."""

    def _create(**overrides: Any) -> int:
        data: dict[str, Any] = {
            "place_id": f"ChIJ_test_{overrides.get('name', 'default')}",
            "name": "Тестовий бізнес",
            "address": "вул. Тестова, 1, Львів",
            "phone": "+380 32 000 0000",
            "website": None,
            "social_links": "[]",
            "rating": 4.5,
            "reviews_count": 100,
            "category": "кав'ярні",
            "location": "Львів",
        }
        data.update(overrides)
        lead_id, _created = upsert_lead(db_path, data)
        return lead_id

    return _create
