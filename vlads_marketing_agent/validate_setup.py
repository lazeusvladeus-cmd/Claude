#!/usr/bin/env python3
"""Скрипт фінальної валідації налаштування агента.

Запускається користувачем одразу після заповнення .env, ДО першого
реального запуску пайплайну. Перевіряє:
    1. Чи всі обов'язкові змінні середовища присутні.
    2. Чи валідний формат Anthropic API ключа (без реального виклику API).
    3. Чи існує та коректний за структурою credentials.json для Gmail.
    4. Чи можна імпортувати всі залежності з requirements.txt.
    5. Чи валідний leads_config.yaml.

Виводить чіткий чек-лист ✅/❌ по кожному пункту та повертає код виходу
0 (усе гаразд) або 1 (є проблеми).
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REQUIRED_ENV_VARS = (
    "GOOGLE_PLACES_API_KEY",
    "ANTHROPIC_API_KEY",
    "GMAIL_CREDENTIALS_FILE",
    "GMAIL_SENDER_EMAIL",
)

# (ім'я_модуля_для_import, назва_пакету_у_requirements.txt)
REQUIRED_PACKAGES = (
    ("requests", "requests"),
    ("bs4", "beautifulsoup4"),
    ("yaml", "PyYAML"),
    ("dotenv", "python-dotenv"),
    ("anthropic", "anthropic"),
    ("googleapiclient", "google-api-python-client"),
    ("google_auth_oauthlib", "google-auth-oauthlib"),
    ("pptx", "python-pptx"),
)


def _check(label: str, ok: bool, detail: str = "") -> bool:
    """Друкує один рядок чек-листа з іконкою ✅/❌ і повертає ok без змін."""
    icon = "✅" if ok else "❌"
    suffix = f" — {detail}" if detail and not ok else ""
    print(f"{icon} {label}{suffix}")
    return ok


def check_env_vars() -> bool:
    """Перевіряє наявність усіх обов'язкових змінних середовища."""
    print("\n--- Змінні середовища (.env) ---")
    all_ok = True
    for var in REQUIRED_ENV_VARS:
        ok = bool(os.getenv(var))
        all_ok = _check(f"{var} задано", ok, "відсутнє або порожнє у .env") and all_ok
    return all_ok


def check_anthropic_key_format() -> bool:
    """Перевіряє формат Anthropic API ключа без жодного реального виклику API."""
    print("\n--- Формат Anthropic API ключа ---")
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return _check("ANTHROPIC_API_KEY має правильний формат", False, "ключ не задано")
    ok = key.startswith("sk-ant-") and len(key) > 15
    return _check(
        "ANTHROPIC_API_KEY має правильний формат (починається з 'sk-ant-')",
        ok,
        "очікується ключ, що починається з 'sk-ant-' (див. console.anthropic.com)",
    )


def check_gmail_credentials() -> bool:
    """Перевіряє наявність та структуру credentials.json для Gmail OAuth."""
    print("\n--- Gmail credentials.json ---")
    path = Path(os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json"))

    if not path.exists():
        return _check(
            f"Файл '{path}' знайдено",
            False,
            "завантажте credentials.json з Google Cloud Console (SETUP.md, розділ 3)",
        )
    _check(f"Файл '{path}' знайдено", True)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return _check("credentials.json є валідним JSON", False, str(exc))
    _check("credentials.json є валідним JSON", True)

    section = data.get("installed") or data.get("web")
    ok = bool(section and section.get("client_id") and section.get("client_secret"))
    return _check(
        "credentials.json має коректну структуру OAuth Client ID",
        ok,
        "очікуються поля 'installed' (або 'web') з 'client_id' та 'client_secret'",
    )


def check_imports() -> bool:
    """Перевіряє, чи можна імпортувати всі залежності з requirements.txt."""
    print("\n--- Python-залежності (requirements.txt) ---")
    all_ok = True
    for module_name, package_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(module_name)
            ok = True
        except ImportError:
            ok = False
        all_ok = (
            _check(
                f"Пакет '{package_name}' імпортується",
                ok,
                "встановіть: pip install -r requirements.txt",
            )
            and all_ok
        )
    return all_ok


def check_leads_config() -> bool:
    """Перевіряє валідність leads_config.yaml."""
    print("\n--- leads_config.yaml ---")
    from src.config import _load_yaml_config  # локальний імпорт, щоб не падати раніше часу
    from src.exceptions import AgentConfigError

    path = os.getenv("LEADS_CONFIG_PATH", "leads_config.yaml")
    try:
        cfg = _load_yaml_config(path)
    except AgentConfigError as exc:
        return _check(f"'{path}' валідний", False, str(exc).splitlines()[0])
    return _check(f"'{path}' валідний ({len(cfg.searches)} пошукових запитів)", True)


def main() -> int:
    """Запускає всі перевірки та виводить підсумок."""
    load_dotenv()

    print("=" * 64)
    print("Перевірка налаштування агента Vlad's Marketing")
    print("=" * 64)

    results = [
        check_env_vars(),
        check_anthropic_key_format(),
        check_gmail_credentials(),
        check_imports(),
        check_leads_config(),
    ]

    print("\n" + "=" * 64)
    if all(results):
        print("✅ Усі перевірки пройдено. Можна запускати: python main.py pipeline")
        return 0

    print("❌ Деякі перевірки не пройдено. Виправте помилки вище перед запуском.")
    print("   Порада: спочатку спробуйте кожну команду з прапорцем --dry-run.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
