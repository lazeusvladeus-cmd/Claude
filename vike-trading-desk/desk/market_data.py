"""Download intraday futures bars from Yahoo Finance (via yfinance) and keep a local copy.

Yahoo limits (free, unofficial): 1-minute bars only for about the last 8 days, 5-minute
bars for about the last 60 days. Every download is merged into data/cache, so if you open
the app every day your own 1-minute history grows beyond Yahoo's 8-day window.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
KEEP_DAYS = {"1m": 60, "5m": 400}
RESOLUTION_MINUTES = {"1m": 1, "5m": 5}


def yahoo_download(symbol: str, interval: str) -> pd.DataFrame:
    """Raw download. period='max' = the most Yahoo allows for that bar size."""
    import yfinance as yf

    return yf.Ticker(symbol).history(
        period="max", interval=interval, auto_adjust=False, actions=False, raise_errors=True
    )


@dataclass
class Bars:
    symbol: str
    combined: pd.DataFrame  # best available: 1-minute bars where we have them, 5-minute elsewhere
    coarse: pd.DataFrame  # 5-minute bars only (used for the chart)
    downloaded_at: pd.Timestamp
    problems: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return self.combined.empty


def normalize_bars(raw: pd.DataFrame | None, market_tz) -> pd.DataFrame:
    """Clean a yfinance frame: exchange-clock index, numeric OHLCV, no broken bars."""
    if raw is None or raw.empty:
        return _empty(market_tz)
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):  # yf.download style columns
        df.columns = df.columns.get_level_values(0)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = 0.0 if col == "Volume" else float("nan")
    df = df[COLUMNS].apply(pd.to_numeric, errors="coerce")
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx
    df.index = idx.tz_convert(market_tz)
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df["Volume"] = df["Volume"].fillna(0).clip(lower=0)
    df["High"] = df[["Open", "High", "Low", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "High", "Low", "Close"]].min(axis=1)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.index.name = "time"
    return df


def _empty(market_tz) -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], tz=market_tz, name="time"), dtype=float)


def _cache_path(cache_dir: Path, symbol: str, interval: str) -> Path:
    return Path(cache_dir) / f"{re.sub(r'[^A-Za-z0-9]+', '_', symbol)}_{interval}.parquet"


def _read_cache(path: Path, market_tz) -> pd.DataFrame:
    try:
        return normalize_bars(pd.read_parquet(path), market_tz) if path.exists() else _empty(market_tz)
    except Exception:  # a damaged cache file is not worth crashing for; it gets rewritten
        return _empty(market_tz)


def _merge(old: pd.DataFrame, new: pd.DataFrame, keep_days: int) -> pd.DataFrame:
    frames = [f for f in (old, new) if not f.empty]
    if not frames:
        return old
    merged = pd.concat(frames)
    merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    cutoff = merged.index.max() - pd.Timedelta(days=keep_days)
    return merged[merged.index >= cutoff]


def combine_resolutions(fine: pd.DataFrame, coarse: pd.DataFrame) -> pd.DataFrame:
    """Use 1-minute bars wherever they exist, 5-minute bars to fill everything else.

    Adds a 'Res' column (1 or 5) so the app can say which resolution a session used.
    """
    fine = fine.assign(Res=1)
    coarse = coarse.assign(Res=5)
    if fine.empty:
        return coarse
    if coarse.empty:
        return fine
    covered = fine.index.floor("5min").unique()
    coarse_only = coarse[~coarse.index.isin(covered)]
    out = pd.concat([coarse_only, fine]).sort_index()
    return out[~out.index.duplicated(keep="last")]


def friendly_error(exc: Exception, symbol: str, interval: str) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if "RateLimit" in text or "Too Many Requests" in text or "429" in text:
        return (
            f"Yahoo is limiting requests right now ({symbol}, {interval}). "
            "Wait 5-10 minutes, then press Refresh. If it keeps happening, run update.bat."
        )
    if "Failed to resolve" in text or "ConnectionError" in text or "NameResolution" in text or "timed out" in text:
        return f"No internet connection to Yahoo Finance ({symbol}, {interval}). Check your internet and press Refresh."
    return f"Couldn't download {interval} bars for {symbol} from Yahoo ({text[:200]}). If this persists, run update.bat."


def load_bars(
    symbol: str,
    cache_dir: Path,
    market_tz,
    downloader: Callable[[str, str], pd.DataFrame] = yahoo_download,
) -> Bars:
    """Download fresh bars, merge them with the saved copy, and return the best available data."""
    cache_dir = Path(cache_dir)
    problems: list[str] = []
    frames: dict[str, pd.DataFrame] = {}
    any_fresh = False
    for interval in ("1m", "5m"):
        path = _cache_path(cache_dir, symbol, interval)
        cached = _read_cache(path, market_tz)
        try:
            fresh = normalize_bars(downloader(symbol, interval), market_tz)
            if fresh.empty:
                problems.append(f"Yahoo returned no {interval} bars for {symbol}.")
        except Exception as exc:  # network, rate limit, Yahoo changes - show it, keep going with the cache
            fresh = _empty(market_tz)
            problems.append(friendly_error(exc, symbol, interval))
        merged = _merge(cached, fresh, KEEP_DAYS[interval])
        if not fresh.empty:
            any_fresh = True
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
                merged.to_parquet(path)
            except Exception as exc:
                problems.append(f"Couldn't save the local data copy ({exc}).")
        frames[interval] = merged

    combined = combine_resolutions(frames["1m"], frames["5m"])
    if not any_fresh and not combined.empty:
        problems.append(
            f"Showing SAVED data for {symbol} (last bar {combined.index.max():%a %d %b %H:%M} NY) "
            "because the download failed."
        )
    return Bars(
        symbol=symbol,
        combined=combined,
        coarse=frames["5m"],
        downloaded_at=pd.Timestamp.now(tz=market_tz),
        problems=problems,
    )


def stock_prices(ticker: str, downloader: Callable | None = None) -> tuple[float | None, pd.Series, str]:
    """Latest price and ~10 years of month-end closes for a stock (Yahoo Finance)."""
    try:
        if downloader is None:
            import yfinance as yf

            hist = yf.Ticker(ticker).history(period="10y", interval="1mo", auto_adjust=False, actions=False, raise_errors=True)
            last = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=False, actions=False, raise_errors=True)
        else:
            hist, last = downloader(ticker)
        monthly = hist["Close"].dropna()
        monthly.index = pd.DatetimeIndex(monthly.index).tz_localize(None) if pd.DatetimeIndex(monthly.index).tz else pd.DatetimeIndex(monthly.index)
        price = float(last["Close"].dropna().iloc[-1]) if not last.empty else (float(monthly.iloc[-1]) if len(monthly) else None)
        return price, monthly, ""
    except Exception as exc:
        return None, pd.Series(dtype=float), friendly_error(exc, ticker, "price")
