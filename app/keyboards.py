"""Inline keyboards. Every write to the sheet is gated behind an explicit tap,
never auto-saved from an AI guess — see handlers/callbacks.py."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from app.config import settings
from app.models import CATEGORIES, category_label

# Button labels for the persistent quick-action menu (bottom reply keyboard). Defined
# once here and matched exactly by handlers/commands.py's quick-action handlers.
QUICK_STATS = "📊 Stats"
QUICK_ADVICE = "💡 Advice"
QUICK_TODAY = "📅 Today"
QUICK_SHEET = "📄 Sheet"
QUICK_HELP = "❓ Help"


def main_menu_kb() -> ReplyKeyboardMarkup:
    """The persistent bottom keyboard — one-tap access to the most common actions,
    always visible so you never have to remember or type a command."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=QUICK_STATS), KeyboardButton(text=QUICK_ADVICE)],
            [KeyboardButton(text=QUICK_TODAY), KeyboardButton(text=QUICK_SHEET)],
            [KeyboardButton(text=QUICK_HELP)],
        ],
        resize_keyboard=True,  # compact buttons instead of full-height default rows
        is_persistent=True,  # stays visible instead of collapsing behind the keyboard icon
    )


def confirm_transaction_kb(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Save", callback_data=f"tx:confirm:{pending_id}"),
                InlineKeyboardButton(text="✏️ Category", callback_data=f"tx:editcat:{pending_id}"),
            ],
            [
                InlineKeyboardButton(text="🔁 Flip type", callback_data=f"tx:flipdir:{pending_id}"),
                InlineKeyboardButton(text="❌ Discard", callback_data=f"tx:discard:{pending_id}"),
            ],
        ]
    )


def category_picker_kb(pending_id: str, current_category: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, cat in enumerate(CATEGORIES, start=1):
        label = category_label(cat)
        if cat == current_category:
            label = f"✓ {label}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"tx:setcat:{pending_id}:{cat}"))
        if i % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="« Back", callback_data=f"tx:back:{pending_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dashboard_kb() -> InlineKeyboardMarkup | None:
    """Button that opens the Mini App dashboard, or None if MINIAPP_URL isn't
    configured (the bot works fine without it — this is purely additive)."""
    if not settings.miniapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📈 Open Dashboard", web_app=WebAppInfo(url=settings.miniapp_url))]
        ]
    )


def undo_kb(tx_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ Undo this entry", callback_data=f"tx:undo:{tx_id}")]]
    )
