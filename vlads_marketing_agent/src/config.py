"""Завантаження та валідація конфігурації агента.

Усі секрети (API-ключі, шляхи до credentials) читаються ВИКЛЮЧНО зі
змінних середовища (.env файл) — ніколи не хардкодяться в коді.
Налаштування пошуку лідів (категорії, локації, ліміти) читаються з
окремого YAML-файлу `leads_config.yaml`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.exceptions import AgentConfigError

# Список змінних середовища, без яких агент не може працювати взагалі
# (навіть у dry-run режимі порожній ключ вважається помилкою конфігурації,
# якщо команда явно потребує цього API).
REQUIRED_ENV_VARS: tuple[str, ...] = (
    "GOOGLE_PLACES_API_KEY",
    "ANTHROPIC_API_KEY",
)


@dataclass(frozen=True)
class SearchQuery:
    """Один пошуковий запит: категорія бізнесу + локація."""

    category: str
    location: str

    @property
    def query_text(self) -> str:
        """Текст запиту для Google Places Text Search."""
        return f"{self.category} {self.location}".strip()


@dataclass(frozen=True)
class LeadsSearchConfig:
    """Розпарсена та провалідована конфігурація пошуку лідів (leads_config.yaml)."""

    searches: tuple[SearchQuery, ...]
    max_new_leads_per_run: int
    max_results_per_search: int
    min_reviews_count: int


@dataclass(frozen=True)
class Settings:
    """Усі налаштування агента, зібрані з .env та leads_config.yaml."""

    google_places_api_key: str
    anthropic_api_key: str
    anthropic_model: str
    gmail_credentials_file: str
    gmail_token_file: str
    gmail_sender_email: str
    leads_db_path: str
    leads_config_path: str
    check_replies_interval_minutes: int
    presentations_dir: str
    log_level: str
    log_dir: str
    leads_config: LeadsSearchConfig = field(repr=False)


def _load_yaml_config(path: str | Path) -> LeadsSearchConfig:
    """Завантажує та валідує leads_config.yaml.

    Піднімає `AgentConfigError` із людяним поясненням, якщо файл
    відсутній, є битим YAML, або в ньому не вистачає обов'язкових полів.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise AgentConfigError(
            f"Файл конфігурації лідів не знайдено: '{config_path}'.\n"
            "Створіть файл leads_config.yaml у корені проєкту "
            "(приклад є в репозиторії) або вкажіть правильний шлях "
            "у змінній середовища LEADS_CONFIG_PATH."
        )

    try:
        with config_path.open("r", encoding="utf-8") as fh:
            raw: Any = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise AgentConfigError(
            f"Файл '{config_path}' містить некоректний YAML: {exc}\n"
            "Перевірте відступи та лапки у файлі leads_config.yaml."
        ) from exc

    if not isinstance(raw, dict):
        raise AgentConfigError(
            f"Файл '{config_path}' має бути YAML-словником (map), "
            f"а не {type(raw).__name__}. Перевірте структуру файлу."
        )

    searches_raw = raw.get("searches")
    if not searches_raw or not isinstance(searches_raw, list):
        raise AgentConfigError(
            "У leads_config.yaml відсутній або порожній список 'searches'.\n"
            "Додайте хоча б один запис виду:\n"
            "  searches:\n"
            '    - category: "кав\'ярні"\n'
            '      location: "Львів"'
        )

    searches: list[SearchQuery] = []
    for idx, item in enumerate(searches_raw):
        if not isinstance(item, dict) or "category" not in item or "location" not in item:
            raise AgentConfigError(
                f"Запис #{idx + 1} у 'searches' некоректний: {item!r}.\n"
                "Кожен запис має містити поля 'category' та 'location'."
            )
        category = str(item["category"]).strip()
        location = str(item["location"]).strip()
        if not category or not location:
            raise AgentConfigError(
                f"Запис #{idx + 1} у 'searches' має порожню категорію або локацію."
            )
        searches.append(SearchQuery(category=category, location=location))

    def _positive_int(key: str, default: int) -> int:
        value = raw.get(key, default)
        try:
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise AgentConfigError(
                f"Поле '{key}' у leads_config.yaml має бути цілим числом, "
                f"отримано: {raw.get(key)!r}"
            ) from exc
        if value <= 0:
            raise AgentConfigError(f"Поле '{key}' у leads_config.yaml має бути > 0.")
        return value

    def _non_negative_int(key: str, default: int) -> int:
        value = raw.get(key, default)
        try:
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise AgentConfigError(
                f"Поле '{key}' у leads_config.yaml має бути цілим числом, "
                f"отримано: {raw.get(key)!r}"
            ) from exc
        if value < 0:
            raise AgentConfigError(f"Поле '{key}' у leads_config.yaml не може бути від'ємним.")
        return value

    return LeadsSearchConfig(
        searches=tuple(searches),
        max_new_leads_per_run=_positive_int("max_new_leads_per_run", 20),
        max_results_per_search=_positive_int("max_results_per_search", 20),
        min_reviews_count=_non_negative_int("min_reviews_count", 0),
    )


def load_settings(env_file: str | Path = ".env", *, require_secrets: bool = True) -> Settings:
    """Завантажує всі налаштування агента з .env та leads_config.yaml.

    Args:
        env_file: шлях до .env файлу (типово ".env" у поточній директорії).
        require_secrets: якщо True — піднімає AgentConfigError за відсутності
            обов'язкових ключів (GOOGLE_PLACES_API_KEY, ANTHROPIC_API_KEY).
            Вимикається у validate_setup.py, щоб показати ✅/❌ по кожному
            пункту окремо, замість падіння на першому ж.

    Returns:
        Заповнений об'єкт Settings.

    Raises:
        AgentConfigError: якщо конфігурація неповна або некоректна.
    """
    load_dotenv(dotenv_path=env_file, override=False)

    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if require_secrets and missing:
        joined = ", ".join(missing)
        raise AgentConfigError(
            f"Відсутні обов'язкові змінні середовища: {joined}.\n"
            "Перевірте файл .env (скопіюйте .env.example -> .env та "
            "заповніть значення). Детальні інструкції — у SETUP.md."
        )

    leads_config_path = os.getenv("LEADS_CONFIG_PATH", "leads_config.yaml")
    leads_config = _load_yaml_config(leads_config_path)

    return Settings(
        google_places_api_key=os.getenv("GOOGLE_PLACES_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        gmail_credentials_file=os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json"),
        gmail_token_file=os.getenv("GMAIL_TOKEN_FILE", "token.json"),
        gmail_sender_email=os.getenv("GMAIL_SENDER_EMAIL", ""),
        leads_db_path=os.getenv("LEADS_DB_PATH", "leads.db"),
        leads_config_path=leads_config_path,
        check_replies_interval_minutes=int(os.getenv("CHECK_REPLIES_INTERVAL_MINUTES", "60")),
        presentations_dir=os.getenv("PRESENTATIONS_DIR", "presentations"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_dir=os.getenv("LOG_DIR", "logs"),
        leads_config=leads_config,
    )
