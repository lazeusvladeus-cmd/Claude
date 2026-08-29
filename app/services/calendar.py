"""Google Calendar reads, used to send a Telegram reminder before each event.

Uses the shared user-OAuth credentials (see services/google_oauth.py) — the
same one-time login that also authorizes Sheets access.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import settings
from app.services.google_oauth import GoogleAuthNotConfigured, load_credentials

logger = logging.getLogger(__name__)


class CalendarNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    summary: str
    start: datetime
    location: str | None
    is_all_day: bool


def _load_credentials() -> Credentials:
    try:
        return load_credentials()
    except GoogleAuthNotConfigured as exc:
        raise CalendarNotConfigured(str(exc)) from exc


def _list_upcoming_events_sync(window_minutes: int) -> list[CalendarEvent]:
    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now = datetime.now(timezone.utc)
    time_max = now + timedelta(minutes=window_minutes)

    try:
        result = (
            service.events()
            .list(
                calendarId=settings.google_calendar_id,
                timeMin=now.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=25,
            )
            .execute()
        )
    except HttpError:
        logger.exception("Google Calendar API call failed")
        raise

    events: list[CalendarEvent] = []
    for item in result.get("items", []):
        start_info = item.get("start", {})
        is_all_day = "date" in start_info and "dateTime" not in start_info
        if is_all_day:
            start_dt = datetime.fromisoformat(start_info["date"]).replace(tzinfo=timezone.utc)
        else:
            start_dt = datetime.fromisoformat(start_info["dateTime"])
        events.append(
            CalendarEvent(
                id=item.get("id", ""),
                summary=item.get("summary", "(no title)"),
                start=start_dt,
                location=item.get("location"),
                is_all_day=is_all_day,
            )
        )
    return events


async def list_upcoming_events(window_minutes: int) -> list[CalendarEvent]:
    return await asyncio.to_thread(_list_upcoming_events_sync, window_minutes)


async def list_today_events() -> list[CalendarEvent]:
    """Used by /today — everything remaining in the *local* calendar day."""
    local_tz = ZoneInfo(settings.timezone)
    now_local = datetime.now(local_tz)
    midnight_local = (now_local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    minutes_remaining = int((midnight_local - now_local).total_seconds() // 60)
    return await list_upcoming_events(max(minutes_remaining, 1))
