import datetime as dt
import re

import pandas as pd
from synthetic import NY, random_walk_bars
from test_econ_calendar import FEED

from desk.config import Instrument, LevelSettings, Sessions
from desk.econ_calendar import events_for_day, load_manual, parse_feed
from desk.levels import chart_window, compute_prep
from desk.sheet_export import SheetPage, sheet_pdf, sheet_png
from desk.timeutil import Clocks

CLOCKS = Clocks("Europe/Kyiv", NY, "Kyiv", "NY")
SESSIONS = Sessions(dt.time(9, 30), dt.time(16, 0), dt.time(18, 0), dt.time(16, 0))
SETTINGS = LevelSettings(True, True, True, True, True, True, True, 70.0, 20, 5)
DAY = dt.date(2026, 10, 14)
NOW = pd.Timestamp("2026-10-14 06:55", tz=NY)

CHECKLIST = {
    "market_state": "Balance (rotating inside a range)",
    "open_location": "Inside value",
    "htf_context": "Тиждень у балансі між 24 800 і 25 300. " * 6,  # Cyrillic notes must render
    "news_risk": "CPI 15:30 Kyiv / 08:30 NY",
    "scenarios": "",
    "key_locations": ["NQ VAH 25,120.00", "NQ POC 25,080.25"],
    "extra_levels": "Gamma flip 25,000",
    "location_plan": "Fade VAH only with absorption; long VAL on delta divergence.",
    "confirmations": ["Absorption at the level (heavy volume, price stops)"],
    "trigger_invalidation": "",
    "max_daily_loss_usd": 500.0,
    "max_trades": 3,
    "risk_per_trade_usd": 150.0,
}


def page(key: str, base: float) -> SheetPage:
    inst = Instrument(key, f"Test {key}", f"{key}=F", key, 0.25, 20.0, True)
    bars = random_walk_bars(dt.date(2026, 10, 4), DAY, minutes=1, base=base).assign(Res=1)
    bars = bars[bars.index <= NOW]
    prep = compute_prep(bars, inst, DAY, NOW, SESSIONS, SETTINGS, CLOCKS)
    events, _ = events_for_day(parse_feed(FEED, NY), load_manual("missing.csv"), DAY, NY)
    return SheetPage(prep, chart_window(bars, DAY, 3, SESSIONS, NOW), events, CHECKLIST, f"{key}Z26 (Dec 2026)",
                     "Rollover period for NQ: test warning")


def test_png_and_two_page_pdf(tmp_path):
    nq, es = page("NQ", 25000), page("ES", 6700)
    png = sheet_png(nq, CLOCKS, SESSIONS, NOW, 5)
    assert png.startswith(b"\x89PNG") and len(png) > 50_000
    (tmp_path / "sheet_NQ.png").write_bytes(png)
    pdf = sheet_pdf([nq, es], CLOCKS, SESSIONS, NOW, 5)
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page[^s]", pdf)) == 2


def test_sheet_without_events_or_checklist():
    p = page("NQ", 25000)
    p.events = pd.DataFrame()
    p.checklist = {}
    p.rollover = None
    assert sheet_png(p, CLOCKS, SESSIONS, NOW, 5).startswith(b"\x89PNG")
