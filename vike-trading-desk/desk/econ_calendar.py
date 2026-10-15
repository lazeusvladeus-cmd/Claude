"""Economic calendar: the free ForexFactory weekly feed plus your own manual events.

The feed (nfs.faireconomy.media) is free and widely used, but unofficial: no guarantee,
one week at a time, and it blocks you if you download it too often. So the app keeps a
saved copy and only re-downloads every few hours. Manual events (data/economic_events_manual.csv)
always show, so you can add anything the feed misses - or use only manual events.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

FEEDS = {
    "this week": "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "next week": "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
}
OFFICIAL_SOURCES = [
    ("Fed: FOMC meeting calendar (rate decision 14:00 NY, press conference 14:30 NY)",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    ("BLS: CPI, jobs report (NFP), PPI release dates", "https://www.bls.gov/schedule/news_release/"),
    ("BEA: GDP and PCE inflation release dates", "https://www.bea.gov/news/schedule"),
    ("ForexFactory calendar (website of the free feed)", "https://www.forexfactory.com/calendar"),
]
MANUAL_COLUMNS = ["date", "time_ny", "event", "impact", "notes"]
IMPACT_RANK = {"Holiday": 4, "High": 3, "Medium": 2, "Low": 1}
EVENT_COLUMNS = ["time", "all_day", "events", "impact", "details", "source"]
USER_AGENT = "Mozilla/5.0 (personal trading-prep app; one download every few hours)"


@dataclass
class EventsResult:
    table: pd.DataFrame  # columns EVENT_COLUMNS, one row per time slot
    notes: list[str] = field(default_factory=list)
    feed_ok: bool = False


def _http_get(url: str):
    import requests

    return requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)


def fetch_feed(
    name: str,
    cache_dir: Path,
    max_age_hours: float,
    now: pd.Timestamp,
    http_get: Callable = _http_get,
) -> tuple[list | None, str]:
    """Return (events, status message). Uses the saved copy unless it's older than max_age_hours."""
    path = Path(cache_dir) / f"ff_{name.replace(' ', '_')}.json"
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
    if cached:
        fetched_at = pd.Timestamp(cached["fetched_at"])
        if now - fetched_at < pd.Timedelta(hours=max_age_hours):
            return cached.get("events"), f"saved copy from {fetched_at.tz_convert(now.tz):%a %H:%M}"

    def fallback(reason: str) -> tuple[list | None, str]:
        if cached and cached.get("events"):
            when = pd.Timestamp(cached["fetched_at"]).tz_convert(now.tz)
            return cached["events"], f"{reason} Using the saved copy from {when:%a %d %b %H:%M}."
        return None, reason

    try:
        response = http_get(FEEDS[name])
    except Exception as exc:  # no internet, DNS, timeout
        return fallback(f"Couldn't reach the free calendar feed ({type(exc).__name__}).")
    status = getattr(response, "status_code", 0)
    events = None
    if status == 200:
        try:
            events = response.json()
        except ValueError:
            events = None
        if not isinstance(events, list):
            return fallback("The free feed refused the download (it allows only a few per hour).")
    elif status != 404:
        return fallback(f"The free feed answered with an error (HTTP {status}).")

    try:  # remember the answer - even "not published yet" (404) - so we don't ask again too soon
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetched_at": now.isoformat(), "url": FEEDS[name], "events": events}), encoding="utf-8")
    except OSError:
        pass
    if events is None:
        return fallback(f"The {name} file isn't published yet.")
    return events, f"downloaded {now:%a %H:%M}"


def parse_feed(items: list | None, market_tz) -> pd.DataFrame:
    rows = []
    for item in items or []:
        try:
            when = pd.Timestamp(item["date"]).tz_convert(market_tz)
        except (KeyError, ValueError, TypeError):
            continue
        rows.append(
            {
                "time": when,
                "title": str(item.get("title", "")).strip(),
                "country": str(item.get("country", "")).upper(),
                "impact": str(item.get("impact", "")).strip().capitalize(),
                "forecast": str(item.get("forecast", "") or "").strip(),
                "previous": str(item.get("previous", "") or "").strip(),
            }
        )
    return pd.DataFrame(rows, columns=["time", "title", "country", "impact", "forecast", "previous"])


def feed_covers(feed: pd.DataFrame, day: dt.date) -> bool:
    """ForexFactory weeks run Sunday-Saturday; does this feed's week include `day`?"""
    if feed.empty:
        return False

    def sunday(d: dt.date) -> dt.date:
        return d - dt.timedelta(days=(d.weekday() + 1) % 7)

    return sunday(day) in {sunday(t.date()) for t in feed["time"]}


def load_manual(csv_path: Path) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        return pd.DataFrame(columns=MANUAL_COLUMNS)
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    for col in MANUAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[MANUAL_COLUMNS]


def save_manual(df: pd.DataFrame, csv_path: Path) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = df.reindex(columns=MANUAL_COLUMNS).fillna("").astype(str)
    clean = clean[clean["event"].str.strip() != ""]
    clean.to_csv(path, index=False, encoding="utf-8")


def _manual_rows(manual: pd.DataFrame, day: dt.date, market_tz) -> tuple[list[dict], list[str]]:
    rows, problems = [], []
    for _, row in manual.iterrows():
        try:
            row_day = dt.date.fromisoformat(str(row["date"]).strip())
        except ValueError:
            if str(row["event"]).strip():
                problems.append(f'Manual event "{row["event"]}" has a date that isn\'t YYYY-MM-DD: "{row["date"]}".')
            continue
        if row_day != day:
            continue
        text = str(row["time_ny"]).strip()
        all_day = text == ""
        try:
            at = dt.time(0, 0) if all_day else dt.datetime.strptime(text, "%H:%M").time()
        except ValueError:
            problems.append(f'Manual event "{row["event"]}" has a time that isn\'t HH:MM (New York time): "{text}".')
            continue
        rows.append(
            {
                "time": pd.Timestamp(dt.datetime.combine(day, at)).tz_localize(market_tz),
                "all_day": all_day,
                "title": str(row["event"]).strip(),
                "impact": str(row["impact"]).strip().capitalize() or "High",
                "details": str(row["notes"]).strip(),
                "source": "manual",
            }
        )
    return rows, problems


def events_for_day(
    feed: pd.DataFrame,
    manual: pd.DataFrame,
    day: dt.date,
    market_tz,
    countries: tuple[str, ...] = ("USD",),
    impacts: tuple[str, ...] = ("High",),
) -> tuple[pd.DataFrame, list[str]]:
    """One row per time slot (e.g. all 08:30 releases together), sorted by time."""
    rows = []
    if not feed.empty:
        today = feed[[t.date() == day for t in feed["time"]]]
        today = today[today["country"].isin(countries)]
        today = today[today["impact"].isin(impacts) | (today["impact"] == "Holiday")]
        for _, ev in today.iterrows():
            detail = ", ".join(p for p in (
                f"forecast {ev['forecast']}" if ev["forecast"] else "",
                f"previous {ev['previous']}" if ev["previous"] else "",
            ) if p)
            rows.append(
                {
                    "time": ev["time"],
                    "all_day": ev["impact"] == "Holiday",
                    "title": f"{ev['title']} ({ev['country']})" if ev["impact"] == "Holiday" else ev["title"],
                    "impact": ev["impact"],
                    "details": f"{ev['title']}: {detail}" if detail else "",
                    "source": "ForexFactory",
                }
            )
    manual_rows, problems = _manual_rows(manual, day, market_tz)
    rows += manual_rows
    if not rows:
        return pd.DataFrame(columns=EVENT_COLUMNS), problems

    df = pd.DataFrame(rows)
    grouped = []
    for (when, all_day), group in df.groupby(["time", "all_day"], sort=True):
        impact = max(group["impact"], key=lambda i: IMPACT_RANK.get(i, 0))
        grouped.append(
            {
                "time": when,
                "all_day": bool(all_day),
                "events": " · ".join(dict.fromkeys(group["title"])),
                "impact": impact,
                "details": "; ".join(d for d in group["details"] if d),
                "source": " + ".join(sorted(set(group["source"]))),
            }
        )
    out = pd.DataFrame(grouped, columns=EVENT_COLUMNS)
    return out.sort_values(["all_day", "time"], ascending=[False, True]).reset_index(drop=True), problems


def get_events(
    day: dt.date,
    cache_dir: Path,
    manual_csv: Path,
    market_tz,
    now: pd.Timestamp,
    use_feed: bool = True,
    countries: tuple[str, ...] = ("USD",),
    impacts: tuple[str, ...] = ("High",),
    max_age_hours: float = 4,
    http_get: Callable = _http_get,
) -> EventsResult:
    notes: list[str] = []
    feed = pd.DataFrame()
    feed_ok = False
    if use_feed:
        for name in FEEDS:
            items, status = fetch_feed(name, cache_dir, max_age_hours, now, http_get)
            parsed = parse_feed(items, market_tz)
            if feed_covers(parsed, day):
                feed, feed_ok = parsed, True
                notes.append(f"Free ForexFactory feed ({name}): {status}.")
                break
            if name == "this week" and items is None:
                notes.append(status)
        if not feed_ok:
            notes.append(
                f"The free feed doesn't have {day:%a %d %b} (it publishes one week at a time). "
                "Add the day's events manually below, using the official calendars."
            )
    manual = load_manual(manual_csv)
    table, problems = events_for_day(feed, manual, day, market_tz, countries, impacts)
    return EventsResult(table=table, notes=notes + problems, feed_ok=feed_ok)
