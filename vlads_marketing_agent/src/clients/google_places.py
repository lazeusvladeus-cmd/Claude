"""Клієнт для Google Places API (Text Search + Place Details).

Використовується Модулем 1 (lead_discovery.py) для пошуку малого та
середнього бізнесу за категорією й локацією. НЕ звертається до
Instagram/Facebook напряму — якщо Google Places замість власного сайту
повертає посилання на сторінку в соцмережі (типово для малого бізнесу
без сайту), воно зберігається окремим текстовим полем `social_links`
для подальшого напівручного збагачення користувачем (Модуль 2).
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse

import requests

from src.utils import retry_with_backoff

logger = logging.getLogger(__name__)

_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

_SOCIAL_DOMAINS = ("instagram.com", "facebook.com", "fb.com")

# Статуси Google Places API, при яких варто повторити запит (тимчасові збої).
_RETRYABLE_STATUSES = {"OVER_QUERY_LIMIT", "UNKNOWN_ERROR"}


class PlacesAPIError(Exception):
    """Помилка звернення до Google Places API (після вичерпання спроб)."""


def _is_social_link(url: str) -> bool:
    """Перевіряє, чи є URL посиланням на Instagram/Facebook, а не власним сайтом."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return any(domain in host for domain in _SOCIAL_DOMAINS)


def _split_website_and_social(raw_website: str | None) -> tuple[str | None, list[str]]:
    """Розділяє поле 'website' з Places API на (справжній_сайт, соцмережі).

    Малий бізнес часто вказує в Google Business Profile посилання на
    Instagram/Facebook замість власного сайту. Ми ніколи не скрейпимо
    ці посилання напряму (ToS + robots.txt), тому переносимо їх у
    окреме поле для ручного/напівручного опрацювання.
    """
    if not raw_website:
        return None, []
    if _is_social_link(raw_website):
        return None, [raw_website]
    return raw_website, []


class GooglePlacesClient:
    """Тонка обгортка над Google Places Text Search / Place Details API."""

    def __init__(self, api_key: str, *, dry_run: bool = False, request_delay_seconds: float = 0.2):
        """Ініціалізує клієнт.

        Args:
            api_key: ключ Google Places API (з .env, GOOGLE_PLACES_API_KEY).
            dry_run: якщо True — жодних реальних HTTP-запитів не виконується,
                натомість повертаються фейкові дані та в консоль друкується,
                який запит було б зроблено.
            request_delay_seconds: пауза між послідовними запитами, щоб не
                впертися в rate limit Google Places API.
        """
        self._api_key = api_key
        self._dry_run = dry_run
        self._request_delay_seconds = request_delay_seconds

    @retry_with_backoff(
        max_attempts=3,
        base_delay_seconds=2.0,
        retryable_exceptions=(requests.exceptions.RequestException, PlacesAPIError),
    )
    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        status = payload.get("status")
        if status in _RETRYABLE_STATUSES:
            raise PlacesAPIError(f"Google Places API повернув статус {status}")
        if status not in ("OK", "ZERO_RESULTS"):
            # REQUEST_DENIED, INVALID_REQUEST тощо — це не тимчасові помилки,
            # повторювати їх немає сенсу, одразу піднімаємо як фатальну помилку.
            raise PlacesAPIError(
                f"Google Places API повернув статус {status}: "
                f"{payload.get('error_message', 'без деталей')}"
            )
        return payload

    def text_search(self, query: str, *, max_results: int = 20) -> list[dict[str, Any]]:
        """Виконує Text Search запит і повертає список сирих результатів Places.

        Args:
            query: пошуковий текст, наприклад "кав'ярні Львів".
            max_results: максимальна кількість результатів (з урахуванням
                пагінації по 20 на сторінку, до 60 сумарно).

        Returns:
            Список словників-результатів Google Places (сирий формат API).
        """
        if self._dry_run:
            logger.info(
                "[DRY-RUN] Places.text_search(query=%r, max_results=%d)", query, max_results
            )
            print(f"[DRY-RUN] Було б виконано Google Places Text Search: query='{query}'")
            return []

        results: list[dict[str, Any]] = []
        params: dict[str, Any] = {"query": query, "key": self._api_key}
        page = 0
        while True:
            payload = self._get(_TEXT_SEARCH_URL, params)
            results.extend(payload.get("results", []))
            page += 1
            next_token = payload.get("next_page_token")
            if not next_token or len(results) >= max_results or page >= 3:
                break
            # Google вимагає невелику паузу перед тим, як next_page_token стане дійсним.
            time.sleep(2.0)
            params = {"pagetoken": next_token, "key": self._api_key}
            time.sleep(self._request_delay_seconds)

        return results[:max_results]

    def get_place_details(self, place_id: str) -> dict[str, Any]:
        """Отримує деталі місця (телефон, сайт, рейтинг) за Place ID."""
        if self._dry_run:
            logger.info("[DRY-RUN] Places.get_place_details(place_id=%r)", place_id)
            print(f"[DRY-RUN] Було б виконано Google Places Details: place_id='{place_id}'")
            return {}

        fields = "name,formatted_address,formatted_phone_number,website,rating,user_ratings_total"
        payload = self._get(
            _DETAILS_URL, {"place_id": place_id, "fields": fields, "key": self._api_key}
        )
        time.sleep(self._request_delay_seconds)
        return payload.get("result", {})

    def search_businesses(self, query: str, *, max_results: int = 20) -> list[dict[str, Any]]:
        """Повний пошук: Text Search + деталі кожного місця, у зручному форматі.

        Це основний метод, який використовує lead_discovery.py. Об'єднує
        Text Search та Place Details, і одразу розділяє website/соцмережі.

        Returns:
            Список словників з полями: place_id, name, address, phone,
            website, social_links (list[str]), rating, reviews_count.
        """
        if self._dry_run:
            print(f"[DRY-RUN] search_businesses(query='{query}') -> 0 результатів (dry-run)")
            return []

        leads: list[dict[str, Any]] = []
        for item in self.text_search(query, max_results=max_results):
            place_id = item.get("place_id")
            if not place_id:
                continue
            try:
                details = self.get_place_details(place_id)
            except PlacesAPIError as exc:
                logger.warning(
                    "Не вдалося отримати деталі місця place_id=%s: %s. "
                    "Використовуємо дані лише з Text Search.",
                    place_id,
                    exc,
                )
                details = {}

            merged = {**item, **details}
            website, social_links = _split_website_and_social(merged.get("website"))

            leads.append(
                {
                    "place_id": place_id,
                    "name": merged.get("name", "Без назви"),
                    "address": merged.get("formatted_address"),
                    "phone": merged.get("formatted_phone_number"),
                    "website": website,
                    "social_links": social_links,
                    "rating": merged.get("rating"),
                    "reviews_count": merged.get("user_ratings_total"),
                }
            )
        return leads
