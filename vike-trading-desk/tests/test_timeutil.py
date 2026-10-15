import datetime as dt

import pandas as pd

from desk.timeutil import (
    Clocks,
    default_target_date,
    front_contract,
    globex_is_open,
    rollover_warning,
    third_friday,
    trade_dates,
)

NY = "America/New_York"
GLOBEX = dt.time(18, 0)
RTH_END = dt.time(16, 0)


def ts(text: str) -> pd.Timestamp:
    return pd.Timestamp(text, tz=NY)


def test_evening_session_belongs_to_next_trade_date():
    idx = pd.DatetimeIndex(
        [ts("2026-10-11 18:00"), ts("2026-10-12 09:30"), ts("2026-10-12 16:59"), ts("2026-10-12 18:00"), ts("2026-10-16 16:59")]
    )
    got = [d.date() for d in trade_dates(idx, GLOBEX)]
    assert got == [
        dt.date(2026, 10, 12),  # Sunday evening opens Monday
        dt.date(2026, 10, 12),
        dt.date(2026, 10, 12),
        dt.date(2026, 10, 13),  # Monday 18:00 is Tuesday's session
        dt.date(2026, 10, 16),
    ]


def test_default_target_date():
    assert default_target_date(ts("2026-10-15 07:00"), RTH_END) == dt.date(2026, 10, 15)
    assert default_target_date(ts("2026-10-15 10:00"), RTH_END) == dt.date(2026, 10, 15)
    assert default_target_date(ts("2026-10-15 16:30"), RTH_END) == dt.date(2026, 10, 16)
    assert default_target_date(ts("2026-10-16 16:30"), RTH_END) == dt.date(2026, 10, 19)  # Friday -> Monday
    assert default_target_date(ts("2026-10-17 12:00"), RTH_END) == dt.date(2026, 10, 19)  # Saturday
    assert default_target_date(ts("2026-10-18 19:00"), RTH_END) == dt.date(2026, 10, 19)  # Sunday evening


def test_globex_hours():
    assert not globex_is_open(ts("2026-10-17 12:00"), GLOBEX)  # Saturday
    assert not globex_is_open(ts("2026-10-18 17:59"), GLOBEX)
    assert globex_is_open(ts("2026-10-18 18:00"), GLOBEX)
    assert globex_is_open(ts("2026-10-14 03:00"), GLOBEX)
    assert not globex_is_open(ts("2026-10-14 17:30"), GLOBEX)  # daily pause
    assert not globex_is_open(ts("2026-10-16 17:00"), GLOBEX)  # Friday close


def test_contract_months_and_roll():
    assert third_friday(2026, 12) == dt.date(2026, 12, 18)
    assert third_friday(2027, 3) == dt.date(2027, 3, 19)
    assert front_contract("NQ", dt.date(2026, 10, 15)).code == "NQZ26"
    assert front_contract("NQ", dt.date(2026, 12, 9)).code == "NQZ26"
    assert front_contract("NQ", dt.date(2026, 12, 10)).code == "NQH27"  # roll date = expiry - 8 days
    assert front_contract("ES", dt.date(2027, 1, 5)).label == "ESH27 (Mar 2027)"


def test_rollover_warning_window():
    assert rollover_warning("NQ", dt.date(2026, 10, 15)) is None
    warning = rollover_warning("NQ", dt.date(2026, 12, 8))
    assert warning and "NQZ26" in warning and "NQH27" in warning
    assert rollover_warning("NQ", dt.date(2026, 12, 18)) is not None
    assert rollover_warning("NQ", dt.date(2026, 12, 19)) is None


def test_dual_clock_format():
    clocks = Clocks("Europe/Kyiv", NY, "Kyiv", "NY")
    winter = pd.Timestamp("2026-01-15 13:30", tz="UTC")
    assert clocks.dual(winter) == "15:30 Kyiv · 08:30 NY"
    assert clocks.offset_hours(winter) == 7


def test_offset_note_flags_clock_change_weeks():
    clocks = Clocks("Europe/Berlin", NY, "Berlin", "NY")
    normal = clocks.offset_note(pd.Timestamp("2026-10-15 12:00", tz="UTC"))
    assert "6 hours" in normal and "usually" not in normal
    mismatch = clocks.offset_note(pd.Timestamp("2026-10-28 12:00", tz="UTC"))  # Europe changed, US not yet
    assert "5 hours" in mismatch and "usually" in mismatch
