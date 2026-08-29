"""МОДУЛЬ 2: Збагачення даних про бізнес (Enrichment).

Для кожного ліда зі статусом "new":
  - якщо є сайт — завантажує головну сторінку та парсить її (BeautifulSoup)
    на предмет опису послуг, наявності онлайн-замовлення, блогу/новин,
    орієнтовної дати останнього оновлення та контактів;
  - якщо сайту немає, але Google Places видав посилання на Instagram/
    Facebook — лід переводиться у статус "needs_manual_screenshot" і НЕ
    скрейпиться напряму (порушувало б ToS та технічно блокується
    robots.txt). Користувач може донести дані вручну через
    `add_manual_data()`;
  - якщо немає ні сайту, ні соцмереж — лід все одно позначається
    "enriched" з порожніми даними, щоб не зупиняти пайплайн.

Помилка одного сайту (timeout, 404, недоступність) НЕ зупиняє обробку
інших лідів.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.config import Settings
from src.db import (
    add_manual_data as _db_add_manual_data,
)
from src.db import (
    get_leads_by_status,
    init_db,
    mark_needs_manual_screenshot,
    save_enrichment,
)

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 10
_USER_AGENT = "Mozilla/5.0 (compatible; VladsMarketingLeadBot/1.0; +https://vladsmarketing.example)"

_ORDER_KEYWORDS = (
    "замовити",
    "кошик",
    "оформити замовлення",
    "додати в кошик",
    "checkout",
    "add to cart",
    "buy now",
    "order online",
    "shop now",
)
_BLOG_KEYWORDS = ("блог", "новини", "статті", "blog", "news", "articles")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-()]{8,}\d)")
_YEAR_RE = re.compile(r"(20[0-2]\d)")


@dataclass
class EnrichmentStats:
    """Підсумок одного запуску збагачення лідів."""

    processed: int = 0
    enriched_from_website: int = 0
    needs_manual_screenshot: int = 0
    enriched_without_data: int = 0
    website_errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "processed": self.processed,
            "enriched_from_website": self.enriched_from_website,
            "needs_manual_screenshot": self.needs_manual_screenshot,
            "enriched_without_data": self.enriched_without_data,
            "website_errors": self.website_errors,
        }


def fetch_and_parse_website(url: str) -> dict[str, Any]:
    """Завантажує та аналізує головну сторінку сайту бізнесу.

    Args:
        url: URL сайту бізнесу.

    Returns:
        Словник з ключами:
          - fetch_error: None, якщо все ок, або текст помилки.
          - description: опис зі сторінки (meta description або перший
            значущий заголовок/параграф), якщо знайдено.
          - has_online_ordering: bool — чи знайдено ознаки онлайн-замовлення.
          - has_blog: bool — чи знайдено розділ блогу/новин.
          - last_updated_guess: рядок з роком, знайденим у футері/копірайті,
            або None, якщо визначити не вдалося.
          - contact_email: перша знайдена email-адреса або None.
          - contact_phone_found: bool — чи знайдено номер телефону в тексті.
          - text_snippet: перші ~500 символів видимого тексту (для
            подальшого аналізу Claude без вигадування фактів).
    """
    result: dict[str, Any] = {
        "source": "website",
        "url": url,
        "fetch_error": None,
        "description": None,
        "has_online_ordering": False,
        "has_blog": False,
        "last_updated_guess": None,
        "contact_email": None,
        "contact_phone_found": False,
        "text_snippet": "",
    }

    try:
        response = requests.get(
            url,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        result["fetch_error"] = "Час очікування відповіді сайту вичерпано (timeout)."
        return result
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        result["fetch_error"] = f"Сайт повернув помилку HTTP {status}."
        return result
    except requests.exceptions.RequestException as exc:
        result["fetch_error"] = f"Сайт недоступний: {exc}"
        return result

    try:
        soup = BeautifulSoup(response.text, "lxml")
    except Exception:  # noqa: BLE001 - lxml інколи відсутній/б'ється на дивних HTML
        soup = BeautifulSoup(response.text, "html.parser")

    page_text = soup.get_text(separator=" ", strip=True)
    lower_text = page_text.lower()

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        result["description"] = meta_desc["content"].strip()
    else:
        first_heading = soup.find(["h1", "h2"])
        if first_heading and first_heading.get_text(strip=True):
            result["description"] = first_heading.get_text(strip=True)

    result["has_online_ordering"] = any(kw in lower_text for kw in _ORDER_KEYWORDS)
    result["has_blog"] = any(kw in lower_text for kw in _BLOG_KEYWORDS)

    email_match = _EMAIL_RE.search(page_text)
    if email_match:
        result["contact_email"] = email_match.group(0)

    result["contact_phone_found"] = bool(_PHONE_RE.search(page_text))

    footer = soup.find("footer")
    footer_text = footer.get_text(separator=" ", strip=True) if footer else page_text[-1000:]
    year_matches = _YEAR_RE.findall(footer_text)
    if year_matches:
        result["last_updated_guess"] = max(year_matches)

    result["text_snippet"] = page_text[:500]
    return result


def add_manual_data(settings: Settings, lead_id: int, screenshot_text: str) -> None:
    """Додає вручну розшифрований текст зі скріншоту соцмережі для ліда.

    Викликається користувачем для лідів у статусі "needs_manual_screenshot"
    (коли у бізнесу немає власного сайту). Після виклику лід переходить у
    статус "enriched" і потрапляє в наступний запуск `analyze`.

    Args:
        settings: налаштування агента (для шляху до БД).
        lead_id: ID ліда в leads.db.
        screenshot_text: текст, який користувач вручну переписав/скопіював
            зі скріншоту профілю в Instagram/Facebook.
    """
    _db_add_manual_data(settings.leads_db_path, lead_id, screenshot_text)
    logger.info(
        "Лід #%d збагачено вручну (текст зі скріншоту, %d символів).", lead_id, len(screenshot_text)
    )


def run_enrichment(settings: Settings, *, dry_run: bool = False) -> EnrichmentStats:
    """Запускає збагачення для всіх лідів у статусі "new".

    Args:
        settings: налаштування агента.
        dry_run: якщо True — не робить реальних HTTP-запитів до сайтів,
            лише показує, що було б зроблено.

    Returns:
        EnrichmentStats зі статистикою запуску.
    """
    init_db(settings.leads_db_path)
    stats = EnrichmentStats()

    leads = get_leads_by_status(settings.leads_db_path, "new")
    if not leads:
        logger.warning(
            "Немає лідів у статусі 'new' для збагачення. "
            "Спочатку запустіть 'python main.py discover'."
        )
        return stats

    logger.info("Старт Модуля 2 (Enrichment): %d лідів для обробки.", len(leads))

    for lead in leads:
        stats.processed += 1
        social_links: list[str] = json.loads(lead.social_links) if lead.social_links else []

        if lead.website:
            if dry_run:
                logger.info("[DRY-RUN] Було б завантажено та проаналізовано сайт: %s", lead.website)
                print(
                    f"[DRY-RUN] Enrichment: сайт '{lead.website}' для '{lead.name}' "
                    "не завантажується."
                )
                continue

            data = fetch_and_parse_website(lead.website)
            if data["fetch_error"]:
                stats.website_errors += 1
                logger.warning(
                    "Не вдалося завантажити сайт ліда #%d (%s): %s",
                    lead.id,
                    lead.name,
                    data["fetch_error"],
                )
                # Зберігаємо факт помилки, але не блокуємо пайплайн:
                # лід все одно переходить у 'enriched' з мінімальними даними.
                data["analyzed_at"] = datetime.now().isoformat()
                save_enrichment(settings.leads_db_path, lead.id, data)
                continue

            data["analyzed_at"] = datetime.now().isoformat()
            save_enrichment(settings.leads_db_path, lead.id, data)
            stats.enriched_from_website += 1
            logger.info("Лід #%d ('%s') збагачено даними з сайту.", lead.id, lead.name)

        elif social_links:
            if dry_run:
                logger.info(
                    "[DRY-RUN] Лід #%d потребував би позначки 'needs_manual_screenshot'.", lead.id
                )
                print(
                    f"[DRY-RUN] Enrichment: '{lead.name}' немає сайту, є соцмережа "
                    f"{social_links[0]} — потребує ручного скріншоту."
                )
                continue
            mark_needs_manual_screenshot(settings.leads_db_path, lead.id)
            stats.needs_manual_screenshot += 1
            logger.info(
                "Лід #%d ('%s') позначено 'needs_manual_screenshot' (соцмережа: %s).",
                lead.id,
                lead.name,
                social_links[0],
            )
        else:
            if dry_run:
                print(
                    f"[DRY-RUN] Enrichment: '{lead.name}' без сайту й соцмереж — "
                    "буде позначено 'enriched'."
                )
                continue
            save_enrichment(
                settings.leads_db_path,
                lead.id,
                {"source": "none", "note": "Немає сайту та посилань на соцмережі."},
            )
            stats.enriched_without_data += 1
            logger.warning(
                "Лід #%d ('%s') не має ні сайту, ні соцмереж — збагачено без даних.",
                lead.id,
                lead.name,
            )

    logger.info(
        "Модуль 2 завершено: %d з сайту, %d потребують скріншоту, %d без даних, %d помилок сайтів.",
        stats.enriched_from_website,
        stats.needs_manual_screenshot,
        stats.enriched_without_data,
        stats.website_errors,
    )
    return stats
