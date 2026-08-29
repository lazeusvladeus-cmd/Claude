"""МОДУЛЬ 1: Пошук бізнесів (Lead Discovery).

Шукає малий та середній бізнес через Google Places API за категоріями
та локаціями, заданими у leads_config.yaml. Для кожного знайденого
місця зберігає назву, адресу, телефон, сайт, рейтинг, кількість
відгуків та Place ID у локальну SQLite базу (leads.db), дедублікуючи
за Place ID.

НЕ скрейпить Instagram/Facebook напряму — якщо Google Places видає
посилання на соцмережу замість сайту, воно зберігається як окреме
текстове поле для подальшого напівручного збагачення (Модуль 2).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from src.clients.google_places import GooglePlacesClient, PlacesAPIError
from src.config import Settings
from src.db import init_db, upsert_lead

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryStats:
    """Підсумок одного запуску пошуку лідів."""

    searches_run: int = 0
    searches_failed: int = 0
    businesses_found: int = 0
    leads_created: int = 0
    duplicates_skipped: int = 0
    skipped_low_reviews: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "searches_run": self.searches_run,
            "searches_failed": self.searches_failed,
            "businesses_found": self.businesses_found,
            "leads_created": self.leads_created,
            "duplicates_skipped": self.duplicates_skipped,
            "skipped_low_reviews": self.skipped_low_reviews,
        }


def run_discovery(settings: Settings, *, dry_run: bool = False) -> DiscoveryStats:
    """Запускає повний цикл пошуку лідів за конфігурацією leads_config.yaml.

    Проходить по всіх запитах (категорія + локація), шукає бізнеси через
    Google Places API, і зберігає нові (ще не бачені) ліди в leads.db.
    Зупиняється, коли досягнуто ліміт `max_new_leads_per_run` — це
    захищає від випадкового перевищення квоти/бюджету Google Places API.

    Помилка одного пошукового запиту (наприклад, тимчасова недоступність
    API) НЕ зупиняє обробку інших запитів зі списку.

    Args:
        settings: налаштування агента (ключі API, ліміти, шлях до БД).
        dry_run: якщо True — не робить реальних запитів до Google Places,
            лише показує, що було б зроблено.

    Returns:
        DiscoveryStats зі статистикою запуску.
    """
    init_db(settings.leads_db_path)
    client = GooglePlacesClient(settings.google_places_api_key, dry_run=dry_run)
    config = settings.leads_config
    stats = DiscoveryStats()

    logger.info(
        "Старт Модуля 1 (Lead Discovery): %d пошукових запитів, ліміт %d нових лідів",
        len(config.searches),
        config.max_new_leads_per_run,
    )

    for search in config.searches:
        if stats.leads_created >= config.max_new_leads_per_run:
            logger.info(
                "Досягнуто ліміт нових лідів за запуск (%d). Зупиняємо пошук.",
                config.max_new_leads_per_run,
            )
            break

        stats.searches_run += 1
        try:
            businesses = client.search_businesses(
                search.query_text, max_results=config.max_results_per_search
            )
        except PlacesAPIError as exc:
            stats.searches_failed += 1
            logger.error(
                "Пошук за запитом '%s' не вдався: %s. Переходимо до наступного запиту.",
                search.query_text,
                exc,
            )
            continue

        stats.businesses_found += len(businesses)
        logger.info("Запит '%s': знайдено %d бізнесів.", search.query_text, len(businesses))

        for biz in businesses:
            if stats.leads_created >= config.max_new_leads_per_run:
                break

            reviews_count = biz.get("reviews_count") or 0
            if reviews_count < config.min_reviews_count:
                stats.skipped_low_reviews += 1
                logger.warning(
                    "Лід '%s' пропущено: лише %d відгуків (мінімум %d).",
                    biz.get("name"),
                    reviews_count,
                    config.min_reviews_count,
                )
                continue

            lead_data = {
                "place_id": biz["place_id"],
                "name": biz.get("name", "Без назви"),
                "address": biz.get("address"),
                "phone": biz.get("phone"),
                "website": biz.get("website"),
                "social_links": json.dumps(biz.get("social_links") or [], ensure_ascii=False),
                "rating": biz.get("rating"),
                "reviews_count": biz.get("reviews_count"),
                "category": search.category,
                "location": search.location,
            }
            lead_id, created = upsert_lead(settings.leads_db_path, lead_data)
            if created:
                stats.leads_created += 1
                logger.info("Новий лід #%d створено: %s", lead_id, lead_data["name"])
            else:
                stats.duplicates_skipped += 1
                logger.debug(
                    "Дублікат пропущено: %s (place_id=%s)", lead_data["name"], biz["place_id"]
                )

    logger.info(
        "Модуль 1 завершено: %d нових лідів, %d дублікатів, %d невдалих запитів.",
        stats.leads_created,
        stats.duplicates_skipped,
        stats.searches_failed,
    )
    return stats
