import datetime as dt

import numpy as np
import pandas as pd
from synthetic import NY, random_walk_bars

from desk.market_data import combine_resolutions, friendly_error, load_bars, normalize_bars


def test_normalize_converts_timezone_and_repairs_bars():
    raw = pd.DataFrame(
        {
            "Open": [100.0, 101.0, np.nan],
            "High": [99.0, 102.0, 1.0],  # first bar's high is below its open/close: broken
            "Low": [98.0, 100.0, 1.0],
            "Close": [100.5, 101.5, 1.0],
            "Volume": [10, np.nan, 5],
            "Adj Close": [1, 2, 3],
        },
        index=pd.DatetimeIndex(["2026-10-14 13:30", "2026-10-14 13:31", "2026-10-14 13:32"]),  # naive = UTC
    )
    df = normalize_bars(raw, NY)
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert str(df.index.tz) == NY
    assert df.index[0] == pd.Timestamp("2026-10-14 09:30", tz=NY)
    assert len(df) == 2  # NaN row dropped
    assert df["High"].iloc[0] == 100.5 and df["Low"].iloc[0] == 98.0
    assert df["Volume"].iloc[1] == 0


def test_combine_prefers_one_minute_bars_without_double_counting():
    fine = random_walk_bars(dt.date(2026, 10, 14), dt.date(2026, 10, 14), minutes=1)
    coarse = random_walk_bars(dt.date(2026, 10, 12), dt.date(2026, 10, 14), minutes=5)
    combined = combine_resolutions(fine, coarse)
    assert combined.index.is_monotonic_increasing and not combined.index.duplicated().any()
    oct14 = combined[combined.index.normalize() == pd.Timestamp("2026-10-14", tz=NY)]
    assert (oct14["Res"] == 1).all()
    assert (combined[combined.index < fine.index.min()]["Res"] == 5).all()


def test_load_bars_caches_and_falls_back_when_yahoo_fails(tmp_path):
    fine = random_walk_bars(dt.date(2026, 10, 13), dt.date(2026, 10, 14), minutes=1)
    coarse = random_walk_bars(dt.date(2026, 10, 1), dt.date(2026, 10, 14), minutes=5)

    def good(symbol, interval):
        return (fine if interval == "1m" else coarse).tz_convert("UTC")

    bars = load_bars("NQ=F", tmp_path, NY, downloader=good)
    assert not bars.empty and bars.problems == []
    assert (tmp_path / "NQ_F_1m.parquet").exists()

    def broken(symbol, interval):
        raise RuntimeError("YFRateLimitError: Too Many Requests. Rate limited.")

    again = load_bars("NQ=F", tmp_path, NY, downloader=broken)
    assert len(again.combined) == len(bars.combined)
    assert any("limiting requests" in p for p in again.problems)
    assert any("SAVED data" in p for p in again.problems)


def test_friendly_errors():
    assert "internet" in friendly_error(ConnectionError("Failed to resolve host"), "NQ=F", "1m")
    assert "update.bat" in friendly_error(ValueError("weird"), "NQ=F", "1m")
