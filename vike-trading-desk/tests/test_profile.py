import numpy as np
import pandas as pd

from desk.profile import build_profile


def bars_at(prices, volumes, spread=0.0):
    idx = pd.date_range("2026-10-14 09:30", periods=len(prices), freq="1min", tz="America/New_York")
    prices = np.asarray(prices, float)
    return pd.DataFrame(
        {"Open": prices, "High": prices + spread, "Low": prices - spread, "Close": prices, "Volume": volumes},
        index=idx,
    )


def test_volume_spread_across_bar_range_and_poc():
    # bar 1 spreads 1000 over 100.00-101.00 (5 ticks = 200 each); bar 2 adds 600 at 100.50
    df = pd.DataFrame(
        {"Open": [100, 100.5], "High": [101, 100.5], "Low": [100, 100.5], "Close": [101, 100.5], "Volume": [1000, 600]},
        index=pd.date_range("2026-10-14 09:30", periods=2, freq="1min", tz="America/New_York"),
    )
    profile = build_profile(df, 0.25)
    assert profile.poc == 100.5
    assert np.isclose(profile.total_volume, 1600)
    assert np.allclose(profile.volumes, [200, 200, 800, 200, 200])


def test_value_area_classic_two_row_method():
    prices = 100 + 0.25 * np.arange(10)
    volumes = [1, 1, 2, 3, 10, 4, 2, 1, 1, 1]  # total 26 -> 70% = 18.2
    profile = build_profile(bars_at(prices, volumes), 0.25, 70)
    assert profile.poc == 101.0
    # POC 10 -> add rows above (4+2=6) -> 16 -> add rows below (3+2=5) -> 21 >= 18.2
    assert profile.vah == 101.5
    assert profile.val == 100.5


def test_no_volume_falls_back_to_time_at_price():
    profile = build_profile(bars_at([100, 100, 100.25, 101], [0, 0, 0, 0]), 0.25)
    assert profile.uses_time_not_volume
    assert profile.poc == 100.0


def test_bucketed_rows_keep_total_volume():
    rng = np.random.default_rng(1)
    prices = 20000 + np.round(rng.normal(0, 20, 390) * 4) / 4
    profile = build_profile(bars_at(prices, rng.integers(1, 500, 390).astype(float), spread=2), 0.25)
    rows = profile.bucketed(60)
    assert len(rows) <= 60
    assert np.isclose(rows["volume"].sum(), profile.total_volume)
    assert rows["is_poc"].sum() >= 1
