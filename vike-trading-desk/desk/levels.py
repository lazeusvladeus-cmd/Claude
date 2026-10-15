"""Prep-sheet levels: prior day, overnight, value area, weekly range, naked POCs, gap.

Everything is computed "as of" the 09:30 New York open of the session you prepare for
(or as of now, if the open hasn't happened yet). That makes old dates reproducible: the
journal review shows exactly what you would have seen before that open.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from desk.config import Instrument, LevelSettings, Sessions
from desk.profile import VolumeProfile, build_profile
from desk.timeutil import Clocks, globex_is_open, previous_weekday, trade_dates

GROUP_NAMES = {
    "prior_day": "Prior day (RTH)",
    "vwap": "VWAP",
    "value": "Prior value area",
    "overnight": "Overnight (Globex)",
    "weekly": "Weekly",
    "naked_poc": "Naked POC",
}


@dataclass
class Level:
    key: str  # short tag for the chart, e.g. "PDH"
    label: str  # full name for the table
    price: float
    group: str  # see GROUP_NAMES
    note: str = ""


@dataclass
class Gap:
    kind: str  # "opening" (RTH has opened) or "pre-open" (using the last price)
    reference: float  # prior RTH close
    price: float
    points: float
    percent: float


@dataclass
class PrepResult:
    instrument: Instrument
    target_date: dt.date
    as_of: pd.Timestamp
    prior_date: dt.date | None = None
    last_price: float | None = None
    last_bar_time: pd.Timestamp | None = None
    levels: list[Level] = field(default_factory=list)
    prior_profile: VolumeProfile | None = None
    gap: Gap | None = None
    context: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    prior_resolution: str = ""
    prior_range: float | None = None
    overnight_range: float | None = None

    def level(self, key: str) -> Level | None:
        return next((lv for lv in self.levels if lv.key == key), None)

    def to_dict(self) -> dict:
        """JSON-friendly summary for the journal."""
        return {
            "instrument": self.instrument.key,
            "symbol": self.instrument.yahoo_symbol,
            "target_date": self.target_date.isoformat(),
            "prior_date": self.prior_date.isoformat() if self.prior_date else None,
            "as_of": self.as_of.isoformat(),
            "last_price": self.last_price,
            "levels": [vars(lv) for lv in self.levels],
            "gap": vars(self.gap) if self.gap else None,
            "context": self.context,
            "warnings": self.warnings,
            "prior_range": self.prior_range,
            "overnight_range": self.overnight_range,
        }


def _minutes(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def _rth_mask(index: pd.DatetimeIndex, sessions: Sessions) -> np.ndarray:
    mod = index.hour * 60 + index.minute
    return np.asarray((mod >= _minutes(sessions.rth_start)) & (mod < _minutes(sessions.rth_end)))


def _r(price: float, tick: float) -> float:
    return round(round(float(price) / tick) * tick, 6)


def _resolution(bars: pd.DataFrame) -> str:
    if "Res" not in bars or bars.empty:
        return ""
    share_fine = float((bars["Res"] == 1).mean())
    if share_fine > 0.9:
        return "1-minute"
    return "5-minute" if share_fine < 0.1 else "mixed 1/5-minute"


def compute_prep(
    bars: pd.DataFrame,
    instrument: Instrument,
    target_date: dt.date,
    now: pd.Timestamp,
    sessions: Sessions,
    settings: LevelSettings,
    clocks: Clocks,
) -> PrepResult:
    tick = instrument.tick_size
    rth_open = clocks.market_ts(target_date, sessions.rth_start)
    as_of = min(pd.Timestamp(now).tz_convert(clocks.market), rth_open)
    result = PrepResult(instrument=instrument, target_date=target_date, as_of=as_of)

    hist = bars[bars.index < as_of]
    if hist.empty:
        result.warnings.append("No price data before this session. Try Refresh, or pick a more recent date.")
        return result

    td = trade_dates(hist.index, sessions.globex_start)
    rth = _rth_mask(hist.index, sessions)
    target_ts = pd.Timestamp(target_date)

    result.last_price = float(hist["Close"].iloc[-1])
    result.last_bar_time = hist.index[-1]

    # ---- prior RTH session
    rth_days = pd.DatetimeIndex(td[rth]).unique().sort_values()
    rth_days = rth_days[rth_days < target_ts]
    if len(rth_days) == 0:
        result.warnings.append("No finished regular session (09:30-16:00 NY) found before this date.")
        return result
    prior_ts = rth_days[-1]
    prior_date = prior_ts.date()
    result.prior_date = prior_date
    if prior_date != previous_weekday(target_date):
        result.warnings.append(
            f"The last finished session in the data is {prior_date:%a %d %b}, not the weekday before "
            f"{target_date:%a %d %b} (holiday, missing data, or a date in the future)."
        )

    prior = hist[(td == prior_ts) & rth]
    pdh, pdl, pdc = float(prior["High"].max()), float(prior["Low"].min()), float(prior["Close"].iloc[-1])
    result.prior_range = pdh - pdl
    result.prior_resolution = _resolution(prior)
    if result.prior_resolution and result.prior_resolution != "1-minute":
        result.warnings.append(
            f"The prior day's profile uses {result.prior_resolution} bars (Yahoo keeps 1-minute bars only "
            "for about 8 days) - VAH/VAL/POC are less precise than usual."
        )
    levels: list[Level] = []
    if settings.prior_day_high_low_close:
        levels += [
            Level("PDH", "Prior day high (RTH)", _r(pdh, tick), "prior_day"),
            Level("PDL", "Prior day low (RTH)", _r(pdl, tick), "prior_day"),
            Level("PDC", "Prior day close (RTH)", _r(pdc, tick), "prior_day"),
        ]

    if settings.prior_day_vwap:
        vol = prior["Volume"].to_numpy(float)
        if vol.sum() > 0:
            typical = ((prior["High"] + prior["Low"] + prior["Close"]) / 3).to_numpy(float)
            vwap = float((typical * vol).sum() / vol.sum())
            levels.append(Level("pVWAP", "Prior day VWAP (RTH, final)", _r(vwap, tick), "vwap"))
        else:
            result.warnings.append("Yahoo returned no volume for the prior day, so VWAP can't be calculated.")

    session_end = clocks.market_ts(prior_date, sessions.rth_end)
    after_prior = hist[hist.index >= session_end]
    profile = build_profile(prior, tick, settings.value_area_percent)
    result.prior_profile = profile
    if profile and settings.value_area:
        poc_note = "tested since the close" if _touched(after_prior, profile.poc) else "naked: untested since the close"
        levels += [
            Level("VAH", "Prior value area high", profile.vah, "value"),
            Level("POC", "Prior point of control", profile.poc, "value", poc_note),
            Level("VAL", "Prior value area low", profile.val, "value"),
        ]
        if profile.uses_time_not_volume:
            result.warnings.append(
                "No volume in the prior day's data: the value area uses time-at-price (like a TPO profile) instead."
            )

    # ---- overnight (Globex) session: from overnight_start on the prior day until the open
    on_start = max(clocks.market_ts(prior_date, sessions.overnight_start), session_end)
    overnight = hist[hist.index >= on_start]
    if not overnight.empty:
        onh, onl = float(overnight["High"].max()), float(overnight["Low"].min())
        result.overnight_range = onh - onl
        if settings.overnight_high_low:
            so_far = " so far" if as_of < rth_open else ""
            levels += [
                Level("ONH", f"Overnight high{so_far}", _r(onh, tick), "overnight"),
                Level("ONL", f"Overnight low{so_far}", _r(onl, tick), "overnight"),
            ]
    elif settings.overnight_high_low:
        result.warnings.append("No overnight (Globex) trading in the data yet for this session.")

    # ---- weekly range (all hours, by trade date, Monday-Friday)
    if settings.weekly_high_low:
        monday = target_ts - pd.Timedelta(days=target_date.weekday())
        this_week = hist[td >= monday]
        last_week = hist[(td >= monday - pd.Timedelta(days=7)) & (td < monday)]
        if not this_week.empty:
            levels += [
                Level("WkH", "This week high (so far)", _r(this_week["High"].max(), tick), "weekly"),
                Level("WkL", "This week low (so far)", _r(this_week["Low"].min(), tick), "weekly"),
            ]
        if not last_week.empty:
            partial = td.min() > monday - pd.Timedelta(days=7)
            note = "partial week (data starts mid-week)" if partial else ""
            levels += [
                Level("PWH", "Prior week high", _r(last_week["High"].max(), tick), "weekly", note),
                Level("PWL", "Prior week low", _r(last_week["Low"].min(), tick), "weekly", note),
            ]

    # ---- naked POCs from older sessions: POCs no later bar has traded through
    if settings.naked_pocs and settings.naked_poc_max_shown > 0:
        naked = []
        for day_ts in rth_days[:-1][-settings.naked_poc_lookback_days :]:
            day_bars = hist[(td == day_ts) & rth]
            day_profile = build_profile(day_bars, tick, settings.value_area_percent)
            if day_profile is None:
                continue
            later = hist[hist.index >= clocks.market_ts(day_ts.date(), sessions.rth_end)]
            if not _touched(later, day_profile.poc):
                age = int((rth_days > day_ts).sum()) + 1  # the prior day is 1 session ago
                naked.append(
                    Level(
                        "nPOC",
                        f"Naked POC {day_ts:%a %d %b}",
                        day_profile.poc,
                        "naked_poc",
                        f"{age} sessions ago, {_resolution(day_bars)} data",
                    )
                )
        naked.sort(key=lambda lv: abs(lv.price - result.last_price))
        levels += naked[: settings.naked_poc_max_shown]

    result.levels = levels

    # ---- gap vs prior close
    first_rth = bars[(bars.index >= rth_open) & (bars.index < rth_open + pd.Timedelta(minutes=5))]
    first_rth = first_rth[first_rth.index <= now]
    if not first_rth.empty:
        gap_price, kind = float(first_rth["Open"].iloc[0]), "opening"
    else:
        gap_price, kind = result.last_price, "pre-open"
    points = gap_price - pdc
    result.gap = Gap(kind, _r(pdc, tick), _r(gap_price, tick), _r(points, tick), points / pdc * 100)

    result.context = _context_notes(result, pdh, pdl, pdc, profile, overnight)

    if as_of == pd.Timestamp(now).tz_convert(clocks.market) and globex_is_open(as_of, sessions.globex_start):
        stale_minutes = (as_of - result.last_bar_time).total_seconds() / 60
        if stale_minutes > 45:
            result.warnings.append(
                f"The newest Yahoo bar is {stale_minutes:.0f} minutes old ({clocks.dual(result.last_bar_time)}). "
                "Data may be stale - press Refresh."
            )
    return result


def _touched(bars: pd.DataFrame, price: float) -> bool:
    if bars.empty:
        return False
    return bool(((bars["Low"] <= price) & (bars["High"] >= price)).any())


def _context_notes(
    result: PrepResult,
    pdh: float,
    pdl: float,
    pdc: float,
    profile: VolumeProfile | None,
    overnight: pd.DataFrame,
) -> list[str]:
    """Plain-language observations for the Context step (textbook Auction Market Theory readings)."""
    notes = []
    ref = result.gap.price if result.gap else result.last_price
    where = "opened" if result.gap and result.gap.kind == "opening" else "is trading"
    if profile is not None:
        vah, val = profile.vah, profile.val
        if ref > pdh:
            notes.append(
                f"Price {where} ABOVE yesterday's range (PDH {pdh:,.2f}): out of balance to the upside. "
                "Watch whether buyers keep control (acceptance above) or the breakout fails back into the range."
            )
        elif ref > vah:
            notes.append(
                f"Price {where} above yesterday's value but inside the range (between VAH {vah:,.2f} and PDH). "
                "Holding above VAH favours buyers; falling back into value often rotates toward the POC."
            )
        elif ref >= val:
            notes.append(
                f"Price {where} INSIDE yesterday's value ({val:,.2f}-{vah:,.2f}): balance/rotation is more "
                "likely - the value edges are the locations to watch."
            )
        elif ref >= pdl:
            notes.append(
                f"Price {where} below yesterday's value but inside the range (between PDL and VAL {val:,.2f}). "
                "Holding below VAL favours sellers; getting back into value often rotates toward the POC."
            )
        else:
            notes.append(
                f"Price {where} BELOW yesterday's range (PDL {pdl:,.2f}): out of balance to the downside. "
                "Watch whether sellers keep control or the breakdown fails back into the range."
            )

    if pdh > pdl:
        close_pos = (pdc - pdl) / (pdh - pdl)
        where = f"{close_pos:.0%} of the day's range, where 0% = low and 100% = high"
        if close_pos >= 0.8:
            notes.append(f"Yesterday closed near its high ({where}): buyers finished strong.")
        elif close_pos <= 0.2:
            notes.append(f"Yesterday closed near its low ({where}): sellers finished strong.")

    if not overnight.empty:
        above = float((overnight["Close"] > pdc).mean())
        if above >= 0.8:
            notes.append(
                f"Overnight inventory is mostly LONG ({above:.0%} of overnight bars closed above yesterday's close) - "
                "watch for an early inventory correction (dip) after the open."
            )
        elif above <= 0.2:
            notes.append(
                f"Overnight inventory is mostly SHORT ({1 - above:.0%} of overnight bars closed below yesterday's close) - "
                "watch for an early inventory correction (pop) after the open."
            )
        if result.prior_range and result.overnight_range is not None:
            ratio = result.overnight_range / result.prior_range
            notes.append(
                f"Overnight range is {result.overnight_range:,.2f} pts = {ratio:.0%} of yesterday's RTH range "
                f"({result.prior_range:,.2f} pts)."
            )
    return notes


def chart_window(
    bars: pd.DataFrame, target_date: dt.date, sessions_to_show: int, sessions: Sessions, now: pd.Timestamp
) -> pd.DataFrame:
    """Bars for the last N full trading days before the target, plus the target day so far."""
    bars = bars[bars.index <= now]
    if bars.empty:
        return bars
    td = trade_dates(bars.index, sessions.globex_start)
    target_ts = pd.Timestamp(target_date)
    days = pd.DatetimeIndex(td).unique().sort_values()
    days = days[days <= target_ts]
    prior = days[days < target_ts][-sessions_to_show:]
    keep = prior.append(days[days == target_ts])
    return bars[td.isin(keep)]
