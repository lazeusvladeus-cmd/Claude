"""Slash commands: stats, calendar digest, savings advice, sheet link, undo, help."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, Message

from app.keyboards import undo_kb
from app.security import rate_limiter
from app.services import calendar
from app.services.advice import build_savings_digest
from app.services.calendar import CalendarNotConfigured
from app.services.sheets import get_all_transactions, get_last_transaction, sheet_url
from app.services.stats import format_stats_message, render_category_pie_chart, compute_period_stats, since_days_ago

logger = logging.getLogger(__name__)
router = Router(name="commands")

_HELP_TEXT = """👋 <b>Here's what I can do:</b>

🎙️ Send a <b>voice message</b> or just <b>type</b> a purchase (e.g. "15 dollars for lunch") and I'll log it.

<b>Commands:</b>
/stats — spending in the last 7 days
/month — spending in the last 30 days
/advice — personalized savings suggestions
/today — remaining calendar events today
/undo — remove the most recent transaction
/sheet — link to your Google Sheet ledger
/help — this message

I'll also message you before calendar events and with a weekly savings digest.
"""


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(f"Welcome! 💸\n\n{_HELP_TEXT}")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(_HELP_TEXT)


@router.message(Command("sheet"))
async def cmd_sheet(message: Message) -> None:
    await message.answer(f"📄 Your ledger: {sheet_url()}")


async def _send_stats(message: Message, days: int, label: str) -> None:
    try:
        transactions = await get_all_transactions()
    except Exception:
        logger.exception("Failed to load transactions for stats")
        await message.answer("⚠️ Couldn't load your data from Google Sheets right now. Please try again shortly.")
        return

    stats = await compute_period_stats(transactions, since=since_days_ago(days))
    text = format_stats_message(stats, label)
    chart = render_category_pie_chart(stats, title=f"Spending — {label}")
    if chart:
        await message.answer_photo(BufferedInputFile(chart, filename="stats.png"), caption=text)
    else:
        await message.answer(text)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    await _send_stats(message, days=7, label="last 7 days")


@router.message(Command("month"))
async def cmd_month(message: Message) -> None:
    await _send_stats(message, days=30, label="last 30 days")


@router.message(Command("advice"))
async def cmd_advice(message: Message) -> None:
    if not rate_limiter.allow(message.from_user.id):
        await message.answer("⏳ Please wait a minute before requesting advice again.")
        return
    status = await message.answer("🧠 Analyzing your spending…")
    try:
        transactions = await get_all_transactions()
        digest = await build_savings_digest(transactions)
    except Exception:
        logger.exception("Failed to build savings advice")
        await status.edit_text("⚠️ Couldn't generate advice right now. Please try again shortly.")
        return
    await status.edit_text(digest)


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    try:
        events = await calendar.list_today_events()
    except CalendarNotConfigured as exc:
        await message.answer(f"📅 {exc}")
        return
    except Exception:
        logger.exception("Failed to fetch today's calendar events")
        await message.answer("⚠️ Couldn't reach Google Calendar right now. Please try again shortly.")
        return

    if not events:
        await message.answer("📅 Nothing left on your calendar for today. 🎉")
        return

    lines = ["📅 <b>Remaining today:</b>", ""]
    for ev in events:
        when = "All day" if ev.is_all_day else ev.start.strftime("%H:%M")
        lines.append(f"• <b>{when}</b> — {ev.summary}" + (f" ({ev.location})" if ev.location else ""))
    await message.answer("\n".join(lines))


@router.message(Command("undo"))
async def cmd_undo(message: Message) -> None:
    try:
        last = await get_last_transaction()
    except Exception:
        logger.exception("Failed to fetch last transaction for /undo")
        await message.answer("⚠️ Couldn't reach Google Sheets right now. Please try again shortly.")
        return

    if last is None:
        await message.answer("There's nothing to undo.")
        return

    await message.answer(
        f"Most recent entry:\n\n{last.amount:,.2f} {last.currency} — {last.description} ({last.category})\n\n"
        "Tap below to remove it.",
        reply_markup=undo_kb(last.id),
    )


@router.message(F.text.startswith("/"))
async def cmd_unknown(message: Message) -> None:
    """Catch-all for unrecognized slash commands — placed last so specific
    commands above always match first."""
    await message.answer("Not sure what that command is. Send /help to see what I can do.")
