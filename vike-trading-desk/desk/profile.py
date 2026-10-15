"""Volume profile (POC / value area) built from OHLCV bars.

Yahoo only gives 1-minute (or 5-minute) bars, not every trade, so each bar's volume is
spread evenly over the prices between its low and high. That is an approximation of the
tick-by-tick profile ATAS draws: expect the POC/VAH/VAL to differ by a few ticks.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class VolumeProfile:
    prices: np.ndarray  # one row per tick, ascending
    volumes: np.ndarray
    tick: float
    poc: float
    vah: float
    val: float
    total_volume: float
    uses_time_not_volume: bool  # True when the data had no volume (falls back to time-at-price)

    def bucketed(self, max_rows: int = 80) -> pd.DataFrame:
        """Group ticks into bigger rows so the profile is readable on a chart."""
        n = len(self.prices)
        size = max(1, int(np.ceil(n / max_rows)))
        groups = np.arange(n) // size
        df = pd.DataFrame({"group": groups, "price": self.prices, "volume": self.volumes})
        out = df.groupby("group").agg(low=("price", "min"), high=("price", "max"), volume=("volume", "sum"))
        out["mid"] = (out["low"] + out["high"]) / 2
        out["in_value"] = (out["high"] >= self.val) & (out["low"] <= self.vah)
        out["is_poc"] = (out["low"] <= self.poc) & (out["high"] >= self.poc)
        return out.reset_index(drop=True)


def build_profile(bars: pd.DataFrame, tick: float, value_area_pct: float = 70.0) -> VolumeProfile | None:
    """Volume at each price (tick) for the given bars, plus POC, VAH and VAL."""
    bars = bars.dropna(subset=["High", "Low"])
    if bars.empty:
        return None

    low_all = np.floor(bars["Low"].min() / tick + 1e-9) * tick
    high_all = np.ceil(bars["High"].max() / tick - 1e-9) * tick
    n = int(round((high_all - low_all) / tick)) + 1
    prices = low_all + np.arange(n) * tick

    lo_idx = np.clip(np.rint((bars["Low"].to_numpy(float) - low_all) / tick).astype(int), 0, n - 1)
    hi_idx = np.clip(np.rint((bars["High"].to_numpy(float) - low_all) / tick).astype(int), 0, n - 1)
    hi_idx = np.maximum(hi_idx, lo_idx)

    volume = bars["Volume"].fillna(0).to_numpy(float) if "Volume" in bars else np.zeros(len(bars))
    uses_time = float(volume.sum()) <= 0
    weights = np.ones(len(bars)) if uses_time else volume

    # Spread each bar's weight evenly across its price levels (difference-array trick).
    per_level = weights / (hi_idx - lo_idx + 1)
    diff = np.zeros(n + 1)
    np.add.at(diff, lo_idx, per_level)
    np.add.at(diff, hi_idx + 1, -per_level)
    volumes = np.cumsum(diff[:-1])
    volumes[np.abs(volumes) < 1e-9] = 0.0

    poc_idx = _poc_index(volumes)
    val_idx, vah_idx = _value_area(volumes, poc_idx, value_area_pct / 100.0)

    return VolumeProfile(
        prices=prices,
        volumes=volumes,
        tick=tick,
        poc=_round_tick(prices[poc_idx], tick),
        vah=_round_tick(prices[vah_idx], tick),
        val=_round_tick(prices[val_idx], tick),
        total_volume=float(volumes.sum()),
        uses_time_not_volume=uses_time,
    )


def _round_tick(price: float, tick: float) -> float:
    return round(round(price / tick) * tick, 6)


def _poc_index(volumes: np.ndarray) -> int:
    """Price with the most volume; on a tie, the one closest to the middle of the range."""
    top = volumes.max()
    candidates = np.flatnonzero(np.isclose(volumes, top))
    middle = (len(volumes) - 1) / 2
    return int(candidates[np.argmin(np.abs(candidates - middle))])


def _value_area(volumes: np.ndarray, poc_idx: int, share: float) -> tuple[int, int]:
    """Classic value area: grow from the POC, adding whichever 2 rows (above or below) hold more volume."""
    target = volumes.sum() * share
    low = high = poc_idx
    total = volumes[poc_idx]
    n = len(volumes)
    while total < target and (low > 0 or high < n - 1):
        up = volumes[high + 1 : min(high + 3, n)]
        down = volumes[max(low - 2, 0) : low]
        up_sum = up.sum() if len(up) else -1.0
        down_sum = down.sum() if len(down) else -1.0
        if up_sum >= down_sum:
            high += len(up)
            total += up_sum
        else:
            low -= len(down)
            total += down_sum
    return low, high
