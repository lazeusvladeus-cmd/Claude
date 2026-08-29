"""МОДУЛЬ 3: Аналіз і генерація інсайтів (Analyzer).

Для кожного ліда зі статусом "enriched" викликає Claude API з промптом,
що відтворює логіку Skill "outreach-analyzer": знаходить 3-5 конкретних,
дій-орієнтованих слабких місць у присутності бізнесу онлайн, спираючись
ВИКЛЮЧНО на реально зібрані дані (з Модуля 2), без вигадування цифр чи
фактів, яких немає у вхідних даних.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from src.clients.anthropic_client import ClaudeClient
from src.config import Settings
from src.db import Lead, get_leads_by_status, init_db, save_analysis

logger = logging.getLogger(__name__)

# Системний промпт відтворює логіку Skill "outreach-analyzer": аналізувати
# лише реальні факти, не вигадувати метрики, давати дій-орієнтовані висновки.
_SYSTEM_PROMPT = """\
Ти — аналітик performance-маркетингової агенції Vlad's Marketing, що \
спеціалізується на Meta Ads, контенті та брендингу для малого й \
середнього бізнесу.

Твоє завдання: на основі наданих РЕАЛЬНИХ зібраних даних про бізнес \
(з Google Places та/або з парсингу сайту чи скріншоту соцмережі) \
визначити від 3 до 5 конкретних, дій-орієнтованих слабких місць у \
присутності бізнесу онлайн.

СУВОРІ ПРАВИЛА:
1. Використовуй ЛИШЕ факти, які прямо надані у вхідних даних. НІКОЛИ не \
вигадуй цифри, статистику чи факти, яких немає у вхідних даних.
2. Якщо якогось поля даних немає (наприклад, невідомо, чи є в бізнесу \
блог) — просто не роби про це тверджень, а не вигадуй відповідь.
3. Кожне слабке місце має бути конкретним і дій-орієнтованим (тобто з \
нього має бути зрозуміло, що можна покращити), а не загальною фразою \
на кшталт "потрібно покращити маркетинг".
4. Відповідай ВИКЛЮЧНО у форматі JSON-об'єкта з одним ключем "weaknesses" \
— списком рядків українською мовою. Без жодного тексту до або після JSON.

Приклад формату відповіді:
{"weaknesses": ["Сайт не оновлювався з 2021 року — застаріла інформація \
відлякує клієнтів.", "Немає онлайн-замовлення на сайті, хоча асортимент \
дозволяє e-commerce."]}
"""


@dataclass
class AnalysisStats:
    """Підсумок одного запуску аналізу лідів."""

    processed: int = 0
    analyzed: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"processed": self.processed, "analyzed": self.analyzed, "errors": self.errors}


def build_analysis_prompt(lead: Lead) -> str:
    """Формує текст промпту для Claude на основі реальних даних ліда.

    Включає лише ті поля, які фактично присутні (немає сайту — не
    згадується сайт; немає опису — не вигадується опис), щоб модель не
    мала підстав фантазувати.
    """
    enrichment = lead.enrichment
    lines = [
        f"Назва бізнесу: {lead.name}",
        f"Категорія: {lead.category or 'невідомо'}",
        f"Локація: {lead.location or 'невідомо'}",
    ]
    if lead.rating is not None:
        lines.append(f"Рейтинг Google: {lead.rating} ({lead.reviews_count or 0} відгуків)")
    if lead.phone:
        lines.append(f"Телефон вказано: так ({lead.phone})")
    else:
        lines.append("Телефон вказано: ні")

    source = enrichment.get("source")
    if source == "website":
        lines.append(f"Сайт: {enrichment.get('url')}")
        if enrichment.get("fetch_error"):
            lines.append(f"Помилка завантаження сайту: {enrichment['fetch_error']}")
        else:
            if enrichment.get("description"):
                lines.append(f"Опис на сайті: {enrichment['description']}")
            ordering_status = "знайдено" if enrichment.get("has_online_ordering") else "не знайдено"
            lines.append(f"Онлайн-замовлення на сайті: {ordering_status}")
            blog_status = "знайдено" if enrichment.get("has_blog") else "не знайдено"
            lines.append(f"Блог/новини на сайті: {blog_status}")
            if enrichment.get("last_updated_guess"):
                lines.append(
                    f"Рік у футері сайту (орієнтовно останнє оновлення): "
                    f"{enrichment['last_updated_guess']}"
                )
            email_status = "знайдено" if enrichment.get("contact_email") else "не знайдено"
            lines.append(f"Контактний email на сайті: {email_status}")
    elif source == "manual_screenshot":
        lines.append("Сайту немає, дані зібрано вручну зі скріншоту соцмережі:")
        lines.append(enrichment.get("manual_text", ""))
    else:
        lines.append(
            "Даних про сайт чи соцмережі немає (у бізнеса відсутній сайт і посилання на соцмережі)."
        )

    lines.append(
        "\nНа основі ЛИШЕ цих даних визнач 3-5 конкретних, дій-орієнтованих "
        "слабких місць у присутності бізнесу онлайн."
    )
    return "\n".join(lines)


def parse_weaknesses_response(response_text: str) -> list[str]:
    """Розпарсює відповідь Claude у список слабких місць.

    Очікує JSON-об'єкт `{"weaknesses": [...]}`, але має запасний варіант
    для випадку, коли модель додала зайвий текст навколо JSON, або
    повернула марковану списком відповідь замість JSON.

    Raises:
        ValueError: якщо не вдалося витягнути жодного слабкого місця.
    """
    text = response_text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("weaknesses"), list):
            return [str(w).strip() for w in data["weaknesses"] if str(w).strip()][:5]
        if isinstance(data, list):
            return [str(w).strip() for w in data if str(w).strip()][:5]
    except json.JSONDecodeError:
        pass

    # Запасний варіант: витягнути перший JSON-об'єкт/масив із тексту.
    match = re.search(r"\{.*\}", text, re.DOTALL) or re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and isinstance(data.get("weaknesses"), list):
                return [str(w).strip() for w in data["weaknesses"] if str(w).strip()][:5]
            if isinstance(data, list):
                return [str(w).strip() for w in data if str(w).strip()][:5]
        except json.JSONDecodeError:
            pass

    # Останній запасний варіант: маркований список ("- ..." або "1. ...").
    bullet_lines = [
        re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
        for line in text.splitlines()
        if re.match(r"^[\-\*\d]", line.strip())
    ]
    bullet_lines = [line for line in bullet_lines if line]
    if bullet_lines:
        return bullet_lines[:5]

    raise ValueError(
        f"Не вдалося розпарсити відповідь Claude як список слабких місць: {text[:200]!r}"
    )


def run_analysis(settings: Settings, *, dry_run: bool = False) -> AnalysisStats:
    """Запускає аналіз для всіх лідів у статусі "enriched".

    Args:
        settings: налаштування агента (Anthropic API ключ, модель, шлях до БД).
        dry_run: якщо True — не викликає реальний Claude API, лише показує
            промпт, який був би надісланий.

    Returns:
        AnalysisStats зі статистикою запуску.
    """
    init_db(settings.leads_db_path)
    stats = AnalysisStats()

    leads = get_leads_by_status(settings.leads_db_path, "enriched")
    if not leads:
        logger.warning(
            "Немає лідів у статусі 'enriched' для аналізу. "
            "Спочатку запустіть 'python main.py enrich'."
        )
        return stats

    client = ClaudeClient(settings.anthropic_api_key, settings.anthropic_model, dry_run=dry_run)
    logger.info("Старт Модуля 3 (Analyzer): %d лідів для аналізу.", len(leads))

    for lead in leads:
        stats.processed += 1
        prompt = build_analysis_prompt(lead)

        if dry_run:
            logger.info(
                "[DRY-RUN] Було б проаналізовано ліда #%d ('%s') через Claude API.",
                lead.id,
                lead.name,
            )
            print(f"[DRY-RUN] Analyzer -> проаналізовано б '{lead.name}', промпт:\n{prompt}\n")
            continue

        try:
            response_text = client.complete(
                system=_SYSTEM_PROMPT,
                user_prompt=prompt,
                max_tokens=800,
                dry_run_label=f"Аналіз ліда '{lead.name}'",
            )
            weaknesses = parse_weaknesses_response(response_text)
        except Exception as exc:  # noqa: BLE001 - будь-яка помилка не має зупиняти пайплайн
            stats.errors += 1
            logger.error("Не вдалося проаналізувати ліда #%d ('%s'): %s", lead.id, lead.name, exc)
            continue

        save_analysis(settings.leads_db_path, lead.id, weaknesses)
        stats.analyzed += 1
        logger.info(
            "Лід #%d ('%s') проаналізовано: знайдено %d слабких місць.",
            lead.id,
            lead.name,
            len(weaknesses),
        )

    logger.info("Модуль 3 завершено: %d проаналізовано, %d помилок.", stats.analyzed, stats.errors)
    return stats
