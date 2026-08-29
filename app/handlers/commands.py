"""Slash commands, plus their equivalent persistent-quick-action-button entry points.

Every quick-action button (the bottom keyboard from /start) is just a plain text
message with a fixed label — the handlers below match those labels and delegate
to the exact same logic as the matching slash command, so the two are always
in sync by construction rather than by two versions of the same code.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.enums import ChatAction
from aiogram.types import BufferedInputFile, Message

from app.keyboards import (
    QUICK_ADVICE,
    QUICK_HELP,
    QUICK_SHEET,
    QUICK_STATS,
    QUICK_TODAY,
    dashboard_kb,
    main_menu_kb,
    undo_kb,
)
from app.config import settings
from app.security import rate_limiter
from app.services import budget, calendar
from app.services.advice import build_savings_digest
from app.services.calendar import CalendarNotConfigured
from app.services.sheets import get_all_transactions, get_last_transaction, sheet_url
from app.services.stats import (
    compute_period_stats,
    format_stats_message,
    format_trend,
    render_category_pie_chart,
    since_days_ago,
    start_of_this_month,
)

logger = logging.getLogger(__name__)
router = Router(name="commands")

_HELP_TEXT = """👋 <b>Here's what I can do:</b>

🎙️ Send a <b>voice message</b> or just <b>type</b> a purchase (e.g. "15 dollars for lunch") and I'll log it. Use the buttons below any time — no need to remember commands.

<b>Commands:</b>
/stats — spending in the last 7 days
/month — spending in the last 30 days, vs the month before
/advice — personalized savings suggestions
/today — remaining calendar events today
/budget — check your monthly budget usage
/setbudget &lt;amount&gt; — set or change your monthly budget
/undo — remove the most recent transaction
/sheet — link to your Google Sheet ledger
/dashboard — open the visual dashboard (if set up)
/help — this message

I'll also message you before calendar events, the moment you cross a budget threshold, and with a weekly savings digest.
"""


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(f"Welcome! 💸\n\n{_HELP_TEXT}", reply_markup=main_menu_kb())
    kb = dashboard_kb()
    if kb:
        await message.answer("A visual dashboard is also available:", reply_markup=kb)


@router.message(Command("dashboard"))
async def cmd_dashboard(message: Message) -> None:
    kb = dashboard_kb()
    if not kb:
        await message.answer(
            "The dashboard isn't set up yet — it needs MINIAPP_URL configured "
            "(see README) once this bot is deployed somewhere with a public HTTPS URL."
        )
        return
    await message.answer("📈 Your finance dashboard:", reply_markup=kb)


@router.message(Command("help"))
@router.message(F.text == QUICK_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(_HELP_TEXT, reply_markup=main_menu_kb())


@router.message(Command("sheet"))
@router.message(F.text == QUICK_SHEET)
async def cmd_sheet(message: Message) -> None:
    await message.answer(f"📄 Your ledger: {sheet_url()}")


async def _send_stats(message: Message, days: int, label: str, compare_to_previous: bool) -> None:
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        transactions = await get_all_transactions()
    except Exception:
        logger.exception("Failed to load transactions for stats")
        await message.answer("⚠️ Couldn't load your data from Google Sheets right now. Please try again shortly.")
        return

    stats = await compute_period_stats(transactions, since=since_days_ago(days))

    trend = None
    if compare_to_previous:
        previous = await compute_period_stats(
            transactions, since=since_days_ago(days * 2), until=since_days_ago(days)
        )
        trend = format_trend(stats.total_spent, previous.total_spent)

    text = format_stats_message(stats, label, trend=trend)
    chart = render_category_pie_chart(stats, title=f"Spending — {label}")
    if chart:
        await message.answer_photo(BufferedInputFile(chart, filename="stats.png"), caption=text)
    else:
        await message.answer(text)


@router.message(Command("stats"))
@router.message(F.text == QUICK_STATS)
async def cmd_stats(message: Message) -> None:
    await _send_stats(message, days=7, label="last 7 days", compare_to_previous=False)


@router.message(Command("month"))
async def cmd_month(message: Message) -> None:
    await _send_stats(message, days=30, label="last 30 days", compare_to_previous=True)


@router.message(Command("advice"))
@router.message(F.text == QUICK_ADVICE)
async def cmd_advice(message: Message) -> None:
    if not rate_limiter.allow(message.from_user.id):
        await message.answer("⏳ Please wait a minute before requesting advice again.")
        return
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
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
@router.message(F.text == QUICK_TODAY)
async def cmd_today(message: Message) -> None:
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
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


@router.message(Command("budget"))
async def cmd_budget(message: Message) -> None:
    target = await budget.get_effective_budget()
    if not target:
        await message.answer(
            "No monthly budget set yet.\nUse <code>/setbudget 1000</code> to set one "
            f"(in {settings.base_currency})."
        )
        return

    try:
        transactions = await get_all_transactions()
    except Exception:
        logger.exception("Failed to load transactions for /budget")
        await message.answer("⚠️ Couldn't reach Google Sheets right now. Please try again shortly.")
        return

    stats = await compute_period_stats(transactions, since=start_of_this_month())
    used_pct = (stats.total_spent / target) * 100
    remaining = target - stats.total_spent
    bar = _progress_bar(used_pct)
    warn = " 🚨" if used_pct >= 100 else (" ⚠️" if used_pct >= 80 else "")

    cur = settings.base_currency
    lines = [
        "🎯 <b>Monthly budget</b>",
        "",
        f"{bar} {used_pct:.0f}%{warn}",
        f"Spent so far: <b>{cur} {stats.total_spent:,.2f}</b> of <b>{cur} {target:,.2f}</b>",
    ]
    if remaining >= 0:
        lines.append(f"Remaining: <b>{cur} {remaining:,.2f}</b>")
    else:
        lines.append(f"Over by: <b>{cur} {abs(remaining):,.2f}</b>")
    await message.answer("\n".join(lines))


def _progress_bar(pct: float, width: int = 10) -> str:
    filled = min(width, max(0, round(width * pct / 100)))
    return "🟩" * filled + "⬜️" * (width - filled) if pct < 100 else "🟥" * width


@router.message(Command("setbudget"))
async def cmd_setbudget(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer("Usage: <code>/setbudget 1000</code> (in your base currency)")
        return

    raw = command.args.strip().replace(",", "")
    try:
        amount = float(raw)
    except ValueError:
        await message.answer(f"'{command.args}' doesn't look like a number. Try: <code>/setbudget 1000</code>")
        return

    if amount <= 0:
        await message.answer("Budget has to be a positive number.")
        return

    try:
        await budget.set_budget(amount)
    except Exception:
        logger.exception("Failed to save budget setting")
        await message.answer("⚠️ Couldn't save that to Google Sheets right now. Please try again shortly.")
        return

    await message.answer(
        f"🎯 Monthly budget set to <b>{settings.base_currency} {amount:,.2f}</b>. "
        "Check progress any time with /budget."
    )


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
