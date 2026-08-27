"""Google Calendar reads, used to send a Telegram reminder before each event.

Uses a user-OAuth refresh token (minted once via scripts/google_oauth_setup.py),
since a service account has no access to a personal Google Calendar unless it's
explicitly shared — a refresh token is the simpler one-time setup for personal use.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import settings

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


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
    token_path = Path(settings.google_token_file)
    if not token_path.exists():
        raise CalendarNotConfigured(
            "Google Calendar isn't connected yet. Run scripts/google_oauth_setup.py once "
            "to authorize it (see README)."
        )
    creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return creds


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
