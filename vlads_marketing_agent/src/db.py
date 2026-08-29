"""Шар роботи з локальною SQLite базою лідів (leads.db).

Таблиця `leads` — єдине джерело правди про стан кожного ліда протягом
усього пайплайну. Статус ліда рухається так:

    new -> needs_manual_screenshot -> enriched -> analyzed -> drafted
        -> sent -> replied -> presented

("needs_manual_screenshot" — бічна гілка для лідів без сайту, які
користувач збагачує вручну через `add_manual_data()`.)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Усі можливі статуси ліда, у порядку типового руху по пайплайну.
LEAD_STATUSES: tuple[str, ...] = (
    "new",
    "needs_manual_screenshot",
    "enriched",
    "analyzed",
    "drafted",
    "sent",
    "replied",
    "presented",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    address TEXT,
    phone TEXT,
    website TEXT,
    rating REAL,
    reviews_count INTEGER,
    social_links TEXT,
    category TEXT,
    location TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    enrichment_json TEXT,
    manual_screenshot_text TEXT,
    weaknesses_json TEXT,
    email_subject TEXT,
    email_body TEXT,
    draft_id TEXT,
    thread_id TEXT,
    sent_at TEXT,
    reply_text TEXT,
    reply_draft_id TEXT,
    presentation_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_place_id ON leads(place_id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Lead:
    """Зручне представлення рядка таблиці `leads` для решти коду."""

    id: int
    place_id: str
    name: str
    address: str | None
    phone: str | None
    website: str | None
    rating: float | None
    reviews_count: int | None
    social_links: str | None
    category: str | None
    location: str | None
    status: str
    enrichment_json: str | None
    manual_screenshot_text: str | None
    weaknesses_json: str | None
    email_subject: str | None
    email_body: str | None
    draft_id: str | None
    thread_id: str | None
    sent_at: str | None
    reply_text: str | None
    reply_draft_id: str | None
    presentation_path: str | None
    created_at: str
    updated_at: str
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def enrichment(self) -> dict[str, Any]:
        """Розпарсений enrichment_json (порожній dict, якщо ще нема даних)."""
        return json.loads(self.enrichment_json) if self.enrichment_json else {}

    @property
    def weaknesses(self) -> list[str]:
        """Розпарсений список слабких місць (порожній список, якщо ще нема)."""
        return json.loads(self.weaknesses_json) if self.weaknesses_json else []

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Lead:
        data = dict(row)
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        base = {k: v for k, v in data.items() if k in known}
        return cls(**base)


@contextmanager
def get_connection(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Контекстний менеджер з'єднання з БД: коміт при успіху, rollback при помилці."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | Path) -> None:
    """Створює файл БД та таблицю `leads`, якщо вони ще не існують.

    Ідемпотентна операція — безпечно викликати при кожному запуску.
    """
    with get_connection(db_path) as conn:
        conn.executescript(_SCHEMA)
    logger.info("База лідів готова: %s", db_path)


def upsert_lead(db_path: str | Path, lead_data: dict[str, Any]) -> tuple[int, bool]:
    """Додає нового ліда або повертає ID вже існуючого (дедублікація за place_id).

    Args:
        db_path: шлях до SQLite файлу.
        lead_data: словник із ключами name, place_id, address, phone,
            website, rating, reviews_count, social_links, category, location.

    Returns:
        Кортеж (lead_id, created) — created=True, якщо лід був щойно створений;
        created=False, якщо такий place_id вже існував (дублікат пропущено).
    """
    place_id = lead_data["place_id"]
    with get_connection(db_path) as conn:
        existing = conn.execute("SELECT id FROM leads WHERE place_id = ?", (place_id,)).fetchone()
        if existing:
            return existing["id"], False

        now = _now()
        cursor = conn.execute(
            """
            INSERT INTO leads (
                place_id, name, address, phone, website, rating,
                reviews_count, social_links, category, location,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)
            """,
            (
                place_id,
                lead_data.get("name", "Без назви"),
                lead_data.get("address"),
                lead_data.get("phone"),
                lead_data.get("website"),
                lead_data.get("rating"),
                lead_data.get("reviews_count"),
                lead_data.get("social_links"),
                lead_data.get("category"),
                lead_data.get("location"),
                now,
                now,
            ),
        )
        return cursor.lastrowid, True


def get_lead(db_path: str | Path, lead_id: int) -> Lead | None:
    """Повертає лід за ID або None, якщо не знайдено."""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return Lead.from_row(row) if row else None


def get_leads_by_status(db_path: str | Path, status: str) -> list[Lead]:
    """Повертає всі ліди з заданим статусом, відсортовані за датою створення."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM leads WHERE status = ? ORDER BY created_at ASC", (status,)
        ).fetchall()
        return [Lead.from_row(r) for r in rows]


def get_leads_by_statuses(db_path: str | Path, statuses: tuple[str, ...]) -> list[Lead]:
    """Повертає всі ліди, статус яких входить у переданий перелік."""
    placeholders = ",".join("?" for _ in statuses)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM leads WHERE status IN ({placeholders}) ORDER BY created_at ASC",
            statuses,
        ).fetchall()
        return [Lead.from_row(r) for r in rows]


def update_status(db_path: str | Path, lead_id: int, status: str) -> None:
    """Оновлює статус ліда. Кидає ValueError, якщо статус невідомий."""
    if status not in LEAD_STATUSES:
        raise ValueError(f"Невідомий статус ліда: {status!r}")
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), lead_id),
        )


def save_enrichment(db_path: str | Path, lead_id: int, enrichment: dict[str, Any]) -> None:
    """Зберігає результати збагачення (Модуль 2) та переводить лід у 'enriched'."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE leads SET enrichment_json = ?, status = 'enriched', updated_at = ? "
            "WHERE id = ?",
            (json.dumps(enrichment, ensure_ascii=False), _now(), lead_id),
        )


def mark_needs_manual_screenshot(db_path: str | Path, lead_id: int) -> None:
    """Позначає лід як такий, що потребує ручного скріншоту соцмережі."""
    update_status(db_path, lead_id, "needs_manual_screenshot")


def add_manual_data(db_path: str | Path, lead_id: int, screenshot_text: str) -> None:
    """Додає вручну розшифрований текст зі скріншоту Instagram/Facebook.

    Використовується користувачем для лідів без сайту, коли автоматичний
    скрейпінг соцмереж технічно та юридично неможливий. Після додавання
    тексту лід переводиться у статус 'enriched' і потрапляє в аналіз.

    Args:
        db_path: шлях до SQLite файлу.
        lead_id: ID ліда.
        screenshot_text: текст, вручну розшифрований користувачем зі
            скріншоту профілю в Instagram/Facebook (пости, опис, тощо).
    """
    lead = get_lead(db_path, lead_id)
    if lead is None:
        raise ValueError(f"Лід з ID={lead_id} не знайдено.")

    enrichment = lead.enrichment
    enrichment["source"] = "manual_screenshot"
    enrichment["manual_text"] = screenshot_text

    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE leads SET manual_screenshot_text = ?, enrichment_json = ?, "
            "status = 'enriched', updated_at = ? WHERE id = ?",
            (screenshot_text, json.dumps(enrichment, ensure_ascii=False), _now(), lead_id),
        )


def save_analysis(db_path: str | Path, lead_id: int, weaknesses: list[str]) -> None:
    """Зберігає список слабких місць (Модуль 3) та переводить лід у 'analyzed'."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE leads SET weaknesses_json = ?, status = 'analyzed', updated_at = ? "
            "WHERE id = ?",
            (json.dumps(weaknesses, ensure_ascii=False), _now(), lead_id),
        )


def save_draft(
    db_path: str | Path,
    lead_id: int,
    *,
    draft_id: str,
    thread_id: str,
    subject: str,
    body: str,
) -> None:
    """Зберігає інформацію про створену Gmail-чернетку (Модуль 4), статус -> 'drafted'."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE leads SET draft_id = ?, thread_id = ?, email_subject = ?, "
            "email_body = ?, status = 'drafted', updated_at = ? WHERE id = ?",
            (draft_id, thread_id, subject, body, _now(), lead_id),
        )


def mark_sent(db_path: str | Path, lead_id: int, sent_at: str | None = None) -> None:
    """Позначає лист як фактично надісланий користувачем (виявлено в Gmail)."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE leads SET status = 'sent', sent_at = ?, updated_at = ? WHERE id = ?",
            (sent_at or _now(), _now(), lead_id),
        )


def save_reply(db_path: str | Path, lead_id: int, reply_text: str) -> None:
    """Зберігає текст відповіді клієнта та переводить лід у статус 'replied'."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE leads SET reply_text = ?, status = 'replied', updated_at = ? WHERE id = ?",
            (reply_text, _now(), lead_id),
        )


def save_presentation(
    db_path: str | Path, lead_id: int, *, presentation_path: str, reply_draft_id: str
) -> None:
    """Зберігає шлях до згенерованої презентації, статус -> 'presented'."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE leads SET presentation_path = ?, reply_draft_id = ?, "
            "status = 'presented', updated_at = ? WHERE id = ?",
            (presentation_path, reply_draft_id, _now(), lead_id),
        )


def get_status_counts(db_path: str | Path) -> dict[str, int]:
    """Повертає кількість лідів по кожному статусу (для команди `status`)."""
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT status, COUNT(*) as cnt FROM leads GROUP BY status").fetchall()
        counts = {status: 0 for status in LEAD_STATUSES}
        for row in rows:
            counts[row["status"]] = row["cnt"]
        return counts


def count_all_leads(db_path: str | Path) -> int:
    """Повертає загальну кількість лідів у базі."""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM leads").fetchone()
        return row["cnt"]
