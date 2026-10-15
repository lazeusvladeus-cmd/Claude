"""Synthetic futures bars for tests ONLY - never shown in the app."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

NY = "America/New_York"


def globex_index(start: dt.date, end: dt.date, minutes: int = 1) -> pd.DatetimeIndex:
    """Bar start times when CME equity futures trade: Sun 18:00 - Fri 17:00 NY, pause 17:00-18:00."""
    idx = pd.date_range(f"{start} 00:00", f"{end} 23:59", freq=f"{minutes}min", tz=NY)
    wd = idx.weekday
    mod = idx.hour * 60 + idx.minute
    closed = (
        (wd == 5)
        | ((wd == 6) & (mod < 18 * 60))
        | ((wd == 4) & (mod >= 17 * 60))
        | ((mod >= 17 * 60) & (mod < 18 * 60))
    )
    return idx[~closed]


def random_walk_bars(
    start: dt.date, end: dt.date, minutes: int = 1, seed: int = 7, base: float = 20000.0
) -> pd.DataFrame:
    idx = globex_index(start, end, minutes)
    rng = np.random.default_rng(seed)
    close = base + np.cumsum(rng.normal(0, 1.5 * np.sqrt(minutes), len(idx)))
    close = np.round(close * 4) / 4
    open_ = np.concatenate([[base], close[:-1]])
    wick = np.round(np.abs(rng.normal(0, 1.0, len(idx))) * 4) / 4
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    mod = idx.hour * 60 + idx.minute
    rth = (mod >= 570) & (mod < 960)
    volume = np.where(rth, 400, 40) * minutes + rng.integers(0, 50, len(idx))
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume.astype(float)}, index=idx)


def flat_bars(index: pd.DatetimeIndex, price: float, volume: float = 100.0, spread: float = 0.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": price,
            "High": price + spread,
            "Low": price - spread,
            "Close": price,
            "Volume": volume,
        },
        index=index,
    )
