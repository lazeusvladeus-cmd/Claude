"""Typed domain models shared across services and handlers."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator

CATEGORIES: list[str] = [
    "Groceries",
    "Food & Drink",
    "Transport",
    "Housing & Rent",
    "Utilities",
    "Health",
    "Shopping",
    "Entertainment",
    "Subscriptions",
    "Travel",
    "Education",
    "Savings & Investments",
    "Gifts & Donations",
    "Other",
]

CATEGORY_EMOJI: dict[str, str] = {
    "Groceries": "🛒",
    "Food & Drink": "🍔",
    "Transport": "🚕",
    "Housing & Rent": "🏠",
    "Utilities": "💡",
    "Health": "💊",
    "Shopping": "🛍️",
    "Entertainment": "🎬",
    "Subscriptions": "🔁",
    "Travel": "✈️",
    "Education": "📚",
    "Savings & Investments": "💹",
    "Gifts & Donations": "🎁",
    "Other": "📦",
}


def category_label(category: str) -> str:
    return f"{CATEGORY_EMOJI.get(category, '📦')} {category}"


_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _sheet_safe(text: str) -> str:
    """Neutralize spreadsheet formula injection: a transcript like "=HYPERLINK(evil)"
    or "@SUM(...)" would otherwise be evaluated as a formula by Google Sheets (we write
    with USER_ENTERED so values are parsed). A leading apostrophe forces plain text,
    per the standard CSV/spreadsheet-injection mitigation (OWASP)."""
    if text and text[0] in _FORMULA_TRIGGER_CHARS:
        return "'" + text
    return text


class Direction(str, Enum):
    EXPENSE = "expense"
    INCOME = "income"


class ParsedTransaction(BaseModel):
    """What the NLP service extracts from a voice/text message, before the user confirms it."""

    amount: float
    currency: str
    category: str
    description: str
    direction: Direction = Direction.EXPENSE
    merchant: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)

    @field_validator("amount")
    @classmethod
    def _amount_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be positive; direction encodes expense vs income")
        return round(v, 2)

    @field_validator("currency")
    @classmethod
    def _currency_upper(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError(f"currency must be a 3-letter ISO code, got {v!r}")
        return v

    @field_validator("category")
    @classmethod
    def _category_known(cls, v: str) -> str:
        return v if v in CATEGORIES else "Other"


class Transaction(BaseModel):
    """A confirmed, persisted transaction as stored in Google Sheets."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    amount: float
    currency: str
    direction: Direction = Direction.EXPENSE
    category: str
    description: str
    merchant: str | None = None
    source: str = "voice"  # voice | text | manual
    raw_text: str = ""

    def to_row(self) -> list[str]:
        return [
            self.id,
            self.timestamp.isoformat(timespec="seconds"),
            self.direction.value,
            f"{self.amount:.2f}",
            self.currency,
            self.category,
            _sheet_safe(self.description),
            _sheet_safe(self.merchant or ""),
            self.source,
            _sheet_safe(self.raw_text.replace("\n", " ").strip()),
        ]

    @staticmethod
    def header_row() -> list[str]:
        return [
            "id",
            "timestamp_utc",
            "direction",
            "amount",
            "currency",
            "category",
            "description",
            "merchant",
            "source",
            "raw_text",
        ]
