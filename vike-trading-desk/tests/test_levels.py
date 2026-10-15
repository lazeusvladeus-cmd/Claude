import datetime as dt

import numpy as np
import pandas as pd
import pytest
from synthetic import NY, flat_bars, random_walk_bars

from desk.config import Instrument, LevelSettings, Sessions
from desk.levels import chart_window, compute_prep
from desk.profile import build_profile
from desk.timeutil import Clocks

CLOCKS = Clocks("Europe/Kyiv", NY, "Kyiv", "NY")
SESSIONS = Sessions(dt.time(9, 30), dt.time(16, 0), dt.time(18, 0), dt.time(16, 0))
SETTINGS = LevelSettings(True, True, True, True, True, True, True, 70.0, 20, 5)
NQ = Instrument("NQ", "E-mini Nasdaq-100", "NQ=F", "NQ", 0.25, 20.0, True)
TARGET = dt.date(2026, 10, 15)  # Thursday


def ts(text):
    return pd.Timestamp(text, tz=NY)


def between(df, start, end):
    return df[(df.index >= ts(start)) & (df.index < ts(end))]


@pytest.fixture(scope="module")
def walk():
    return random_walk_bars(dt.date(2026, 10, 4), dt.date(2026, 10, 15), minutes=1).assign(Res=1)


def test_levels_match_independent_slices(walk):
    now = ts("2026-10-15 07:00")
    result = compute_prep(walk[walk.index <= now], NQ, TARGET, now, SESSIONS, SETTINGS, CLOCKS)
    prior = between(walk, "2026-10-14 09:30", "2026-10-14 16:00")
    overnight = between(walk, "2026-10-14 16:00", "2026-10-15 07:00")
    this_week = between(walk, "2026-10-11 18:00", "2026-10-15 07:00")
    last_week = between(walk, "2026-10-04 18:00", "2026-10-09 17:00")

    assert result.prior_date == dt.date(2026, 10, 14)
    assert result.level("PDH").price == prior["High"].max()
    assert result.level("PDL").price == prior["Low"].min()
    assert result.level("PDC").price == prior["Close"].iloc[-1]
    vwap = ((prior["High"] + prior["Low"] + prior["Close"]) / 3 * prior["Volume"]).sum() / prior["Volume"].sum()
    assert result.level("pVWAP").price == pytest.approx(vwap, abs=0.125)
    assert result.level("ONH").price == overnight["High"].max()
    assert result.level("ONL").price == overnight["Low"].min()
    assert result.level("ONH").label == "Overnight high so far"
    assert result.level("WkH").price == this_week["High"].max()
    assert result.level("WkL").price == this_week["Low"].min()
    assert result.level("PWH").price == last_week["High"].max()
    assert result.level("PWL").price == last_week["Low"].min()

    profile = build_profile(prior, 0.25, 70)
    assert result.level("POC").price == profile.poc
    assert result.level("VAL").price <= profile.poc <= result.level("VAH").price

    assert result.gap.kind == "pre-open"
    assert result.gap.points == pytest.approx(overnight["Close"].iloc[-1] - prior["Close"].iloc[-1])
    assert result.last_price == overnight["Close"].iloc[-1]
    assert result.prior_resolution == "1-minute"


def crafted_week():
    """Mon POC 100 is never revisited (naked); Tue POC 115 is revisited; Wed POC 112 untested overnight."""
    pieces = [
        ("2026-10-11 18:00", "2026-10-12 09:30", 101, 50, 0.5),
        ("2026-10-12 09:30", "2026-10-12 12:00", 100, 1000, 0.0),
        ("2026-10-12 12:00", "2026-10-12 16:00", 105, 100, 0.0),
        ("2026-10-12 16:00", "2026-10-12 17:00", 110, 50, 0.0),
        ("2026-10-12 18:00", "2026-10-13 09:30", 115, 50, 0.0),
        ("2026-10-13 09:30", "2026-10-13 16:00", 115, 500, 1.0),
        ("2026-10-13 16:00", "2026-10-13 17:00", 112, 50, 0.0),
        ("2026-10-13 18:00", "2026-10-14 09:30", 116, 50, 1.0),
        ("2026-10-14 09:30", "2026-10-14 16:00", 112, 500, 0.5),
        ("2026-10-14 16:00", "2026-10-14 17:00", 118, 50, 0.0),
        ("2026-10-14 18:00", "2026-10-15 09:30", 118, 50, 0.0),
        ("2026-10-15 09:30", "2026-10-15 16:00", 120, 500, 0.0),
    ]
    frames = [
        flat_bars(pd.date_range(ts(a), ts(b), freq="5min", inclusive="left"), price, vol, spread)
        for a, b, price, vol, spread in pieces
    ]
    return pd.concat(frames).assign(Res=5)


def test_naked_pocs_and_context():
    bars = crafted_week()
    now = ts("2026-10-15 07:00")
    result = compute_prep(bars[bars.index <= now], NQ, TARGET, now, SESSIONS, SETTINGS, CLOCKS)
    assert (result.level("PDH").price, result.level("PDL").price, result.level("PDC").price) == (112.5, 111.5, 112.0)
    assert result.level("POC").price == 112.0
    assert "naked" in result.level("POC").note
    naked = [lv for lv in result.levels if lv.key == "nPOC"]
    assert [lv.price for lv in naked] == [100.0]
    assert "Mon 12 Oct" in naked[0].label
    assert result.level("ONH").price == result.level("ONL").price == 118.0
    assert result.gap.points == 6.0
    assert "ABOVE yesterday's range" in result.context[0]
    assert any("Overnight inventory is mostly LONG" in note for note in result.context)
    assert result.prior_resolution == "5-minute"


def test_past_date_is_computed_as_of_the_open():
    bars = crafted_week()
    now = ts("2026-10-15 20:00")  # after the session: levels must not include Thursday's RTH
    result = compute_prep(bars, NQ, TARGET, now, SESSIONS, SETTINGS, CLOCKS)
    assert result.as_of == ts("2026-10-15 09:30")
    assert result.level("ONH").price == 118.0  # Thursday RTH traded 120 but that's after the open
    assert result.level("ONH").label == "Overnight high"
    assert result.gap.kind == "opening"
    assert result.gap.points == 8.0


def test_level_toggles_hide_levels():
    bars = crafted_week()
    now = ts("2026-10-15 07:00")
    settings = LevelSettings(True, False, False, False, False, False, True, 70.0, 20, 5)
    result = compute_prep(bars, NQ, TARGET, now, SESSIONS, settings, CLOCKS)
    assert {lv.key for lv in result.levels} == {"PDH", "PDL", "PDC"}


def test_no_data_before_target_gives_warning_not_crash():
    bars = crafted_week()
    result = compute_prep(bars, NQ, dt.date(2026, 10, 1), ts("2026-10-15 07:00"), SESSIONS, SETTINGS, CLOCKS)
    assert result.levels == [] and result.warnings


def test_chart_window_includes_n_prior_sessions_plus_target(walk):
    now = ts("2026-10-15 07:00")
    window = chart_window(walk, TARGET, 2, SESSIONS, now)
    assert window.index.min() == ts("2026-10-12 18:00")  # Tuesday's session opens Monday 18:00
    assert window.index.max() <= now
    assert np.all(np.diff(window.index.asi8) > 0)
