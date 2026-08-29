"""МОДУЛЬ 4: Персоналізація і створення чернеток у Gmail (Outreach Writer).

Для кожного ліда зі статусом "analyzed" генерує персоналізований email
через Claude API (використовуючи стиль/тон референсного прикладу нижче)
і створює ЧЕРНЕТКУ (users.drafts.create) у Gmail акаунті користувача.

Лист НІКОЛИ не відправляється автоматично — лише зберігається як
чернетка, яку користувач переглядає і надсилає вручну.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.clients.anthropic_client import ClaudeClient
from src.clients.gmail_client import GmailClient
from src.config import Settings
from src.db import Lead, get_leads_by_status, init_db, save_draft
from src.exceptions import AgentAuthError

logger = logging.getLogger(__name__)

# Референсний приклад тону/стилю Vlad's Marketing (наданий власником
# агенції). Використовується як few-shot приклад у промпті — Claude має
# писати в такому ж стилі, але з ПЕРСОНАЛІЗАЦІЄЮ під конкретного ліда,
# а не копіювати приклад дослівно.
_STYLE_REFERENCE_EXAMPLE = """\
Вітаю! Звернув увагу на TERRAHOME OUTDOOR, FURNITURE SHOWROOM та ваш \
напрямок — роздрібний та e-commerce напрямок. Для вас я б насамперед \
протестував кампанію під одну пріоритетну товарну категорію з окремим \
ретаргетингом на відвідувачів. У Vlad's Marketing ми будуємо Meta Ads \
навколо конкретної дії, окремо тестуємо холодну аудиторію й ретаргетинг \
та відсіюємо слабкі сегменти. Можу безкоштовно накидати короткий план із \
2–3 рекламними ідеями саме для TERRAHOME OUTDOOR, FURNITURE SHOWROOM. \
Надіслати?

З повагою,
Владислав, Vlad's Marketing\
"""

_SYSTEM_PROMPT = f"""\
Ти пишеш листи холодного аутричу від імені Владислава, засновника \
performance-маркетингової агенції Vlad's Marketing (Meta Ads, контент, \
брендинг для малого й середнього бізнесу, спочатку у Львові).

Ось приклад тону й стилю, яким мають бути написані листи (структура: \
привітання -> конкретне спостереження про бізнес -> одна конкретна ідея \
під нього -> коротке пояснення підходу агенції -> пропозиція безкоштовного \
плану -> питання "Надіслати?" -> підпис):

---ПРИКЛАД---
{_STYLE_REFERENCE_EXAMPLE}
---КІНЕЦЬ ПРИКЛАДА---

ВАЖЛИВО:
1. НЕ копіюй приклад дослівно — напиши НОВИЙ лист, персоналізований під \
конкретний бізнес і його реальні слабкі місця, які тобі нададуть.
2. Використовуй лише факти зі слабких місць, які тобі передали. Не \
вигадуй додаткових деталей про бізнес.
3. Тон — дружній, впевнений, без зайвого маркетингового жаргону, без \
емодзі, без перебільшень.
4. Лист має бути коротким (100-150 слів).
5. Завжди завершуй підписом "З повагою,\\nВладислав, Vlad's Marketing".
6. Відповідай ВИКЛЮЧНО у форматі JSON-об'єкта з ключами "subject" (тема \
листа, коротка й конкретна) та "body" (повний текст листа). Без жодного \
тексту до або після JSON.
"""


@dataclass
class DraftStats:
    """Підсумок одного запуску створення чернеток."""

    processed: int = 0
    drafted: int = 0
    skipped_no_email: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "processed": self.processed,
            "drafted": self.drafted,
            "skipped_no_email": self.skipped_no_email,
            "errors": self.errors,
        }


def _get_recipient_email(lead: Lead) -> str | None:
    """Визначає email отримувача з даних збагачення ліда (якщо знайдено)."""
    enrichment = lead.enrichment
    email = enrichment.get("contact_email")
    return email.strip() if email else None


def build_email_prompt(lead: Lead) -> str:
    """Формує промпт для генерації персоналізованого листа."""
    weaknesses = lead.weaknesses
    weaknesses_text = (
        "\n".join(f"- {w}" for w in weaknesses) if weaknesses else "(слабких місць не визначено)"
    )
    return (
        f"Назва бізнесу: {lead.name}\n"
        f"Категорія: {lead.category or 'невідомо'}\n"
        f"Локація: {lead.location or 'невідомо'}\n\n"
        f"Слабкі місця, визначені аналізом:\n{weaknesses_text}\n\n"
        "Напиши персоналізований лист холодного аутричу для цього бізнесу."
    )


def parse_email_response(response_text: str, fallback_business_name: str) -> tuple[str, str]:
    """Розпарсює відповідь Claude у (subject, body).

    Якщо модель не повернула валідний JSON, використовує запасний варіант:
    перший рядок тексту як тему, решту — як тіло листа.
    """
    import json
    import re

    text = response_text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("subject") and data.get("body"):
            return str(data["subject"]).strip(), str(data["body"]).strip()
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and data.get("subject") and data.get("body"):
                return str(data["subject"]).strip(), str(data["body"]).strip()
        except json.JSONDecodeError:
            pass

    logger.warning(
        "Відповідь Claude не в JSON-форматі, застосовуємо запасний розбір теми/тіла листа."
    )
    lines = text.splitlines() or [""]
    subject = lines[0].strip() or f"Пропозиція співпраці для {fallback_business_name}"
    body = "\n".join(lines[1:]).strip() or text
    return subject, body


def _write_draft_report(entries: list[tuple[str, str, str, datetime]], log_dir: str) -> Path:
    """Записує людяний текстовий звіт про створені чернетки.

    Args:
        entries: список кортежів (назва_бізнесу, email, тема, час_створення).
        log_dir: директорія для звітів.

    Returns:
        Шлях до створеного файлу звіту.
    """
    report_dir = Path(log_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"drafts_report_{timestamp}.txt"

    lines = [
        f"Звіт про створені чернетки — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
    ]
    if not entries:
        lines.append("Жодної чернетки не було створено під час цього запуску.")
    for business_name, email, subject, created_at in entries:
        timestamp = created_at.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f'[{timestamp}] {business_name} <{email}> — тема: "{subject}"')
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run_draft(settings: Settings, *, dry_run: bool = False) -> DraftStats:
    """Створює персоналізовані чернетки листів для всіх лідів у статусі "analyzed".

    Args:
        settings: налаштування агента (Claude + Gmail облікові дані).
        dry_run: якщо True — не викликає ні Claude, ні Gmail API реально,
            лише показує, що було б зроблено.

    Returns:
        DraftStats зі статистикою запуску.

    Raises:
        AgentAuthError: якщо Gmail OAuth токен недійсний/протермінований
            і повторна авторизація неможлива без дії користувача. Ця
            помилка навмисно НЕ ковтається всередині циклу, оскільки
            стосується всіх лідів одразу, а не одного конкретного.
    """
    init_db(settings.leads_db_path)
    stats = DraftStats()

    leads = get_leads_by_status(settings.leads_db_path, "analyzed")
    if not leads:
        logger.warning(
            "Немає лідів у статусі 'analyzed' для створення чернеток. "
            "Спочатку запустіть 'python main.py analyze'."
        )
        return stats

    claude = ClaudeClient(settings.anthropic_api_key, settings.anthropic_model, dry_run=dry_run)
    gmail = GmailClient(settings.gmail_credentials_file, settings.gmail_token_file, dry_run=dry_run)
    report_entries: list[tuple[str, str, str, datetime]] = []

    logger.info("Старт Модуля 4 (Outreach Writer): %d лідів для створення чернеток.", len(leads))

    for lead in leads:
        stats.processed += 1
        recipient = _get_recipient_email(lead)
        if not recipient:
            stats.skipped_no_email += 1
            logger.warning(
                "Лід #%d ('%s') не має email-адреси в зібраних даних — "
                "чернетку неможливо створити автоматично. Додайте email "
                "вручну в базі даних leads.db (колонка не передбачена CLI "
                "навмисно, щоб уникнути помилкових розсилок).",
                lead.id,
                lead.name,
            )
            continue

        prompt = build_email_prompt(lead)

        if dry_run:
            logger.info(
                "[DRY-RUN] Було б згенеровано лист для ліда #%d ('%s').", lead.id, lead.name
            )
            print(
                f"[DRY-RUN] Outreach Writer -> лист для '{lead.name}' <{recipient}> "
                "не генерується і не надсилається."
            )
            continue

        try:
            response_text = claude.complete(
                system=_SYSTEM_PROMPT,
                user_prompt=prompt,
                max_tokens=700,
                dry_run_label=f"Генерація листа для '{lead.name}'",
            )
            subject, body = parse_email_response(response_text, lead.name)
        except Exception as exc:  # noqa: BLE001 - помилка генерації не має зупиняти інших лідів
            stats.errors += 1
            logger.error(
                "Не вдалося згенерувати лист для ліда #%d ('%s'): %s", lead.id, lead.name, exc
            )
            continue

        try:
            draft = gmail.create_draft(to=recipient, subject=subject, body_text=body)
        except AgentAuthError:
            # Проблема з авторизацією стосується ВСІХ лідів, а не лише
            # цього одного — піднімаємо далі, щоб main.py показав чітку
            # інструкцію користувачу замість тихого пропуску всього циклу.
            raise
        except Exception as exc:  # noqa: BLE001
            stats.errors += 1
            logger.error(
                "Не вдалося створити чернетку Gmail для ліда #%d ('%s'): %s",
                lead.id,
                lead.name,
                exc,
            )
            continue

        save_draft(
            settings.leads_db_path,
            lead.id,
            draft_id=draft["id"],
            thread_id=draft["threadId"],
            subject=subject,
            body=body,
        )
        stats.drafted += 1
        report_entries.append((lead.name, recipient, subject, datetime.now()))
        logger.info(
            "Чернетку для ліда #%d ('%s') створено (draft_id=%s).", lead.id, lead.name, draft["id"]
        )

    if report_entries:
        report_path = _write_draft_report(report_entries, settings.log_dir)
        logger.info("Звіт про створені чернетки збережено: %s", report_path)

    logger.info(
        "Модуль 4 завершено: %d чернеток створено, %d пропущено (немає email), %d помилок.",
        stats.drafted,
        stats.skipped_no_email,
        stats.errors,
    )
    return stats
