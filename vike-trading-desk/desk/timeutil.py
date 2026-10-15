"""Time helpers: your clock vs the exchange clock, CME trade dates, contract months."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd

DAY = dt.timedelta(days=1)


@lru_cache(maxsize=None)
def get_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name == "Europe/Kyiv":  # older time zone databases only know the old spelling
            return ZoneInfo("Europe/Kiev")
        raise


def parse_hhmm(text: str) -> dt.time:
    return dt.datetime.strptime(text.strip(), "%H:%M").time()


def next_weekday(d: dt.date) -> dt.date:
    while d.weekday() >= 5:
        d += DAY
    return d


def previous_weekday(d: dt.date) -> dt.date:
    d -= DAY
    while d.weekday() >= 5:
        d -= DAY
    return d


@dataclass(frozen=True)
class Clocks:
    """Converts and formats times for both clocks: yours (home) and the exchange's (market)."""

    home_tz: str
    market_tz: str
    home_label: str = "Kyiv"
    market_label: str = "NY"

    @property
    def home(self) -> ZoneInfo:
        return get_zone(self.home_tz)

    @property
    def market(self) -> ZoneInfo:
        return get_zone(self.market_tz)

    def now(self) -> pd.Timestamp:
        return pd.Timestamp.now(tz=self.market)

    def market_ts(self, day: dt.date, at: dt.time) -> pd.Timestamp:
        """A wall-clock time on the exchange clock, e.g. 09:30 New York on `day`."""
        return pd.Timestamp(dt.datetime.combine(day, at)).tz_localize(self.market)

    def home_ts(self, day: dt.date, at: dt.time) -> pd.Timestamp:
        return pd.Timestamp(dt.datetime.combine(day, at)).tz_localize(self.home)

    def dual(self, ts: pd.Timestamp, fmt: str = "%H:%M") -> str:
        """'15:30 Kyiv · 08:30 NY' - your time first, exchange time second."""
        ts = pd.Timestamp(ts)
        return (
            f"{ts.tz_convert(self.home).strftime(fmt)} {self.home_label} · "
            f"{ts.tz_convert(self.market).strftime(fmt)} {self.market_label}"
        )

    def offset_hours(self, ts: pd.Timestamp) -> float:
        ts = pd.Timestamp(ts)
        home = ts.tz_convert(self.home).utcoffset()
        market = ts.tz_convert(self.market).utcoffset()
        return (home - market).total_seconds() / 3600

    def offset_note(self, ts: pd.Timestamp) -> str:
        """Explains the hour difference, and flags the weeks when the clocks change on different dates."""
        hours = self.offset_hours(ts)
        year = pd.Timestamp(ts).year
        usual = {
            self.offset_hours(pd.Timestamp(dt.datetime(year, 1, 15, 12), tz="UTC")),
            self.offset_hours(pd.Timestamp(dt.datetime(year, 7, 15, 12), tz="UTC")),
        }
        text = f"{self.home_label} is {_fmt_hours(hours)} ahead of {self.market_label} right now"
        if hours not in usual:
            normal = " / ".join(_fmt_hours(h) for h in sorted(usual))
            text += (
                f" (usually {normal}: Europe and the US change their clocks on different dates. "
                "All times shown are already adjusted)"
            )
        return text + "."


def _fmt_hours(hours: float) -> str:
    return f"{hours:g} hours" if hours != 1 else "1 hour"


# ---------------------------------------------------------------- trade dates


def trade_dates(index: pd.DatetimeIndex, globex_start: dt.time) -> pd.DatetimeIndex:
    """CME trade date for each bar (index must be on the exchange clock).

    Futures trade nearly 24h: the session that opens at 18:00 New York belongs to the
    NEXT trading day (Sunday 18:00 opens Monday's trade date).
    """
    if len(index) == 0:
        return pd.DatetimeIndex([])
    local = index.tz_localize(None) if index.tz is not None else index
    shift = pd.Timedelta(days=1) - pd.Timedelta(hours=globex_start.hour, minutes=globex_start.minute)
    days = (local + shift).normalize()
    weekday = days.weekday
    roll = np.where(weekday == 5, 2, np.where(weekday == 6, 1, 0))
    return days + pd.to_timedelta(roll, unit="D")


def default_target_date(now_market: pd.Timestamp, rth_end: dt.time) -> dt.date:
    """The session to prepare for: today until the RTH close, then the next weekday."""
    day = now_market.date()
    if now_market.time() >= rth_end:
        day += DAY
    return next_weekday(day)


def globex_is_open(now_market: pd.Timestamp, globex_start: dt.time) -> bool:
    """Roughly: Sunday 18:00 to Friday 17:00 New York, with a daily 17:00-18:00 pause (holidays ignored)."""
    wd, t = now_market.weekday(), now_market.time()
    if wd == 5:
        return False
    if wd == 6:
        return t >= globex_start
    if wd == 4 and t >= dt.time(17, 0):
        return False
    return not (dt.time(17, 0) <= t < globex_start)


# ---------------------------------------------------------------- contract months

MONTH_CODES = {3: "H", 6: "M", 9: "U", 12: "Z"}
MONTH_NAMES = {3: "Mar", 6: "Jun", 9: "Sep", 12: "Dec"}


def third_friday(year: int, month: int) -> dt.date:
    d = dt.date(year, month, 15)  # the third Friday falls on the 15th-21st
    return d + dt.timedelta(days=(4 - d.weekday()) % 7)


@dataclass(frozen=True)
class Contract:
    root: str
    year: int
    month: int

    @property
    def code(self) -> str:
        return f"{self.root}{MONTH_CODES[self.month]}{self.year % 100:02d}"

    @property
    def label(self) -> str:
        return f"{self.code} ({MONTH_NAMES[self.month]} {self.year})"

    @property
    def expiry(self) -> dt.date:
        return third_friday(self.year, self.month)

    @property
    def roll_date(self) -> dt.date:
        """CME convention for equity index futures: roll 8 days before expiry (a Thursday)."""
        return self.expiry - dt.timedelta(days=8)

    def next(self) -> "Contract":
        if self.month == 12:
            return Contract(self.root, self.year + 1, 3)
        return Contract(self.root, self.year, self.month + 3)


def front_contract(root: str, today: dt.date) -> Contract:
    """The contract most traders use on `today` (switches on the roll date, not on expiry)."""
    first_month = ((today.month - 1) // 3) * 3 + 3
    contract = Contract(root, today.year, first_month)
    while today >= contract.roll_date:
        contract = contract.next()
    return contract


def rollover_warning(root: str, today: dt.date, warn_days_before: int = 3) -> str | None:
    """Plain-language warning during roll week, when Yahoo's continuous price can be on another contract."""
    contract = Contract(root, today.year, ((today.month - 1) // 3) * 3 + 3)
    while contract.expiry < today:
        contract = contract.next()
    start = contract.roll_date - dt.timedelta(days=warn_days_before)
    if not start <= today <= contract.expiry:
        return None
    nxt = contract.next()
    return (
        f"Rollover period for {root}: traders move from {contract.code} to {nxt.code} on "
        f"{contract.roll_date:%a %d %b} (CME roll date); {contract.code} expires {contract.expiry:%a %d %b}. "
        f"Yahoo's continuous price may switch contracts on a different day than your ATAS chart, "
        f"so levels here can be off by the price difference between the two contracts. "
        f"This week, take your levels from the contract you actually trade in ATAS."
    )
