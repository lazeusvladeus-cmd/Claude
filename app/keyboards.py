"""Inline keyboards. Every write to the sheet is gated behind an explicit tap,
never auto-saved from an AI guess — see handlers/callbacks.py."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import CATEGORIES, category_label


def confirm_transaction_kb(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Save", callback_data=f"tx:confirm:{pending_id}"),
                InlineKeyboardButton(text="✏️ Category", callback_data=f"tx:editcat:{pending_id}"),
            ],
            [
                InlineKeyboardButton(text="🔁 Flip expense/income", callback_data=f"tx:flipdir:{pending_id}"),
                InlineKeyboardButton(text="❌ Discard", callback_data=f"tx:discard:{pending_id}"),
            ],
        ]
    )


def category_picker_kb(pending_id: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, cat in enumerate(CATEGORIES, start=1):
        row.append(InlineKeyboardButton(text=category_label(cat), callback_data=f"tx:setcat:{pending_id}:{cat}"))
        if i % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="« Back", callback_data=f"tx:back:{pending_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def undo_kb(tx_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ Undo this entry", callback_data=f"tx:undo:{tx_id}")]]
    )
