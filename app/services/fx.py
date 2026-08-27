"""Foreign-exchange rates for normalizing multi-currency spending into one base currency.

Uses the National Bank of Ukraine's public exchange-rate API — free, no API key,
no rate limit for reasonable use, and authoritative given UAH is a primary currency
here (many "free" third-party FX APIs have gone paid-key-only; NBU's is a stable
government data source that isn't going anywhere). Rates are UAH-per-unit-of-currency;
everything is converted via UAH as a pivot. Cached for a day in memory, with a
stale-cache and then 1:1 fallback if the network call fails, so stats always render.
"""
from __future__ import annotations

import logging
import time

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

_NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"
_CACHE_TTL_SECONDS = 24 * 60 * 60

# currency -> UAH per 1 unit of that currency. UAH itself is always 1.0.
_rates_uah: dict[str, float] = {"UAH": 1.0}
_fetched_at: float | None = None


async def _refresh_rates() -> bool:
    global _fetched_at
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(_NBU_URL, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    logger.warning("NBU FX API returned status %s", resp.status)
                    return False
                data = await resp.json(content_type=None)
    except Exception:
        logger.exception("NBU FX rate fetch failed")
        return False

    if not isinstance(data, list):
        logger.warning("Unexpected NBU FX API response shape: %r", type(data))
        return False

    updated = False
    for entry in data:
        cc = entry.get("cc")
        rate = entry.get("rate")
        if cc and isinstance(rate, (int, float)):
            _rates_uah[cc.upper()] = float(rate)
            updated = True

    if updated:
        _fetched_at = time.monotonic()
    return updated


async def _ensure_rates_fresh() -> None:
    if _fetched_at is None or (time.monotonic() - _fetched_at) >= _CACHE_TTL_SECONDS:
        await _refresh_rates()


async def to_base_currency(amount: float, currency: str) -> float:
    """Convert `amount` in `currency` into settings.base_currency."""
    base = settings.base_currency.upper()
    currency = currency.upper()
    if currency == base:
        return amount

    await _ensure_rates_fresh()

    from_rate = _rates_uah.get(currency)
    to_rate = _rates_uah.get(base)

    if from_rate is None or to_rate is None:
        missing = currency if from_rate is None else base
        logger.error("No FX rate available for currency %r; using 1:1 as a last resort", missing)
        return amount

    amount_uah = amount * from_rate
    return round(amount_uah / to_rate, 2)
