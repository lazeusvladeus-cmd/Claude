"""Background jobs: calendar reminders (near-real-time, polled every minute) and the
weekly savings digest. Runs inside the bot process via APScheduler — no separate worker
needed for a single-user bot.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services import calendar
from app.services.advice import build_savings_digest
from app.services.calendar import CalendarNotConfigured
from app.services.sheets import get_all_transactions

logger = logging.getLogger(__name__)

_CALENDAR_POLL_SECONDS = 60
# Remember which events we've already reminded about (in-memory; fine to lose on restart —
# worst case is one duplicate reminder if the process restarts right at the wrong moment).
_reminded_event_ids: set[str] = set()


async def _broadcast(bot: Bot, text: str, **kwargs) -> None:
    for user_id in settings.allowed_user_ids:
        try:
            await bot.send_message(user_id, text, **kwargs)
        except Exception:
            logger.exception("Failed to send scheduled message to user_id=%s", user_id)


async def _check_calendar_reminders(bot: Bot) -> None:
    try:
        events = await calendar.list_upcoming_events(settings.calendar_reminder_minutes_before)
    except CalendarNotConfigured:
        return  # calendar integration not set up yet; silently skip
    except Exception:
        logger.exception("Calendar poll failed")
        return

    for ev in events:
        if ev.id in _reminded_event_ids or ev.is_all_day:
            continue
        _reminded_event_ids.add(ev.id)
        when = ev.start.strftime("%H:%M")
        text = f"⏰ <b>{ev.summary}</b> starts at {when}" + (f"\n📍 {ev.location}" if ev.location else "")
        await _broadcast(bot, text)

    # Bound memory: an event that's now in the past can never be reminded about again anyway.
    if len(_reminded_event_ids) > 5000:
        _reminded_event_ids.clear()


async def _send_weekly_digest(bot: Bot) -> None:
    try:
        transactions = await get_all_transactions()
        digest = await build_savings_digest(transactions)
    except Exception:
        logger.exception("Failed to build weekly digest")
        return
    await _broadcast(bot, digest)


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    scheduler.add_job(
        _check_calendar_reminders,
        "interval",
        seconds=_CALENDAR_POLL_SECONDS,
        args=[bot],
        id="calendar_reminders",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        _send_weekly_digest,
        CronTrigger(day_of_week=settings.weekly_digest_dow, hour=settings.weekly_digest_hour, minute=0),
        args=[bot],
        id="weekly_digest",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info("Scheduler started: calendar reminders every %ss, weekly digest at dow=%s hour=%s",
                _CALENDAR_POLL_SECONDS, settings.weekly_digest_dow, settings.weekly_digest_hour)
    return scheduler
