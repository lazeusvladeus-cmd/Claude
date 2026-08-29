#!/usr/bin/env python3
"""Головний CLI-скрипт агента пошуку клієнтів та холодного аутричу.

Команди:
    python main.py discover        # Модуль 1: пошук бізнесів
    python main.py enrich          # Модуль 2: збагачення даних
    python main.py analyze         # Модуль 3: аналіз слабких місць (Claude)
    python main.py draft           # Модуль 4: створення чернеток у Gmail
    python main.py check-replies   # Модуль 5: перевірка відповідей
    python main.py pipeline        # Модулі 1-4 послідовно
    python main.py status          # зведена таблиця статусів усіх лідів

Кожна команда (крім `status`) підтримує прапорець --dry-run, який виконує
всю логіку, але замість реальних викликів API лише друкує, що було б
зроблено.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import analyzer
import enrichment
import lead_discovery
import outreach_writer
import reply_monitor
from src.config import Settings, load_settings
from src.db import count_all_leads, get_status_counts, init_db
from src.exceptions import AgentAuthError, AgentConfigError
from src.logging_config import setup_logging

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    "new": "Нові (щойно знайдені)",
    "needs_manual_screenshot": "Потребують скріншоту вручну",
    "enriched": "Збагачені (готові до аналізу)",
    "analyzed": "Проаналізовані (готові до чернетки)",
    "drafted": "Чернетку створено (очікує ручної відправки)",
    "sent": "Надіслано (очікує відповіді)",
    "replied": "Отримано відповідь (готується презентація)",
    "presented": "Презентацію представлено",
}


def _load_settings_or_exit() -> Settings:
    """Завантажує налаштування або завершує програму зі зрозумілою помилкою."""
    try:
        settings = load_settings()
    except AgentConfigError as exc:
        print(f"\n❌ Помилка конфігурації:\n{exc}\n")
        sys.exit(1)
    setup_logging(settings.log_dir, settings.log_level)
    return settings


def _run_safely(fn, *args, **kwargs):
    """Виконує функцію модуля, перетворюючи AgentAuthError у чітке повідомлення."""
    try:
        return fn(*args, **kwargs)
    except AgentAuthError as exc:
        print(f"\n❌ Проблема з авторизацією Gmail:\n{exc}\n")
        sys.exit(2)


def cmd_discover(args: argparse.Namespace) -> None:
    settings = _load_settings_or_exit()
    stats = _run_safely(lead_discovery.run_discovery, settings, dry_run=args.dry_run)
    print(f"\nМодуль 1 (Discover) завершено: {stats.as_dict()}")


def cmd_enrich(args: argparse.Namespace) -> None:
    settings = _load_settings_or_exit()
    stats = _run_safely(enrichment.run_enrichment, settings, dry_run=args.dry_run)
    print(f"\nМодуль 2 (Enrich) завершено: {stats.as_dict()}")


def cmd_analyze(args: argparse.Namespace) -> None:
    settings = _load_settings_or_exit()
    stats = _run_safely(analyzer.run_analysis, settings, dry_run=args.dry_run)
    print(f"\nМодуль 3 (Analyze) завершено: {stats.as_dict()}")


def cmd_draft(args: argparse.Namespace) -> None:
    settings = _load_settings_or_exit()
    stats = _run_safely(outreach_writer.run_draft, settings, dry_run=args.dry_run)
    print(f"\nМодуль 4 (Draft) завершено: {stats.as_dict()}")


def cmd_check_replies(args: argparse.Namespace) -> None:
    settings = _load_settings_or_exit()
    if not args.watch:
        stats = _run_safely(reply_monitor.check_replies, settings, dry_run=args.dry_run)
        print(f"\nМодуль 5 (Check-Replies) завершено: {stats.as_dict()}")
        return

    interval_seconds = settings.check_replies_interval_minutes * 60
    print(
        f"Режим спостереження активовано: перевірка кожні "
        f"{settings.check_replies_interval_minutes} хв. Натисніть Ctrl+C для зупинки."
    )
    try:
        while True:
            stats = _run_safely(reply_monitor.check_replies, settings, dry_run=args.dry_run)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {stats.as_dict()}")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nЗупинено користувачем.")


def cmd_pipeline(args: argparse.Namespace) -> None:
    settings = _load_settings_or_exit()
    print("=== Запуск повного пайплайну: discover -> enrich -> analyze -> draft ===\n")

    discover_stats = _run_safely(lead_discovery.run_discovery, settings, dry_run=args.dry_run)
    print(f"[1/4] Discover: {discover_stats.as_dict()}")

    enrich_stats = _run_safely(enrichment.run_enrichment, settings, dry_run=args.dry_run)
    print(f"[2/4] Enrich:   {enrich_stats.as_dict()}")

    analyze_stats = _run_safely(analyzer.run_analysis, settings, dry_run=args.dry_run)
    print(f"[3/4] Analyze:  {analyze_stats.as_dict()}")

    draft_stats = _run_safely(outreach_writer.run_draft, settings, dry_run=args.dry_run)
    print(f"[4/4] Draft:    {draft_stats.as_dict()}")

    print("\n=== Пайплайн завершено. Перевірте чернетки в Gmail перед відправкою. ===")


def cmd_status(args: argparse.Namespace) -> None:
    settings = _load_settings_or_exit()
    init_db(settings.leads_db_path)
    total = count_all_leads(settings.leads_db_path)
    counts = get_status_counts(settings.leads_db_path)

    print(f"\nЗведення по базі лідів ({settings.leads_db_path})")
    print(f"Усього лідів: {total}\n")
    print(f"{'Статус':<45}{'Кількість'}")
    print("-" * 55)
    for status, label in _STATUS_LABELS.items():
        print(f"{label:<45}{counts.get(status, 0)}")
    print()


def build_parser() -> argparse.ArgumentParser:
    """Будує argparse-парсер з усіма CLI-командами."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Vlad's Marketing — агент пошуку клієнтів та холодного аутричу.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_dry_run(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--dry-run",
            action="store_true",
            help="Виконати логіку без реальних викликів зовнішніх API.",
        )

    p_discover = subparsers.add_parser("discover", help="Модуль 1: пошук бізнесів (Google Places).")
    add_dry_run(p_discover)
    p_discover.set_defaults(func=cmd_discover)

    p_enrich = subparsers.add_parser("enrich", help="Модуль 2: збагачення даних про бізнес.")
    add_dry_run(p_enrich)
    p_enrich.set_defaults(func=cmd_enrich)

    p_analyze = subparsers.add_parser(
        "analyze", help="Модуль 3: аналіз слабких місць (Claude API)."
    )
    add_dry_run(p_analyze)
    p_analyze.set_defaults(func=cmd_analyze)

    p_draft = subparsers.add_parser("draft", help="Модуль 4: створення чернеток у Gmail.")
    add_dry_run(p_draft)
    p_draft.set_defaults(func=cmd_draft)

    p_check_replies = subparsers.add_parser(
        "check-replies", help="Модуль 5: перевірка відповідей клієнтів."
    )
    add_dry_run(p_check_replies)
    p_check_replies.add_argument(
        "--watch",
        action="store_true",
        help="Перевіряти періодично (CHECK_REPLIES_INTERVAL_MINUTES) замість одноразового запуску.",
    )
    p_check_replies.set_defaults(func=cmd_check_replies)

    p_pipeline = subparsers.add_parser("pipeline", help="Послідовно запускає Модулі 1-4.")
    add_dry_run(p_pipeline)
    p_pipeline.set_defaults(func=cmd_pipeline)

    p_status = subparsers.add_parser("status", help="Показує зведену таблицю статусів усіх лідів.")
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Точка входу CLI. Повертає код завершення процесу."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
