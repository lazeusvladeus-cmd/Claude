"""A real, runtime-adjustable monthly budget — not just an env var.

Catching overspending *in the moment* (right after the transaction that tips you
over) is far more actionable than finding out in next week's digest, so this also
tracks which alert thresholds have already fired this calendar month and returns
a message exactly once per threshold crossing.
"""
from __future__ import annotations

from app.config import settings
from app.services.sheets import get_setting, set_setting

_BUDGET_SETTING_KEY = "monthly_budget"
_ALERT_THRESHOLDS = (0.8, 1.0)  # 80% and 100% of budget

# In-memory "have we already alerted for this threshold, this month" tracker.
# Resets naturally when the month rolls over (see _reset_if_new_month). Losing this
# on a restart just risks one duplicate alert, never a missed one — an acceptable
# tradeoff for not needing another sheet round-trip on every single transaction.
_alerted_month_key: str | None = None
_alerted_threshold_index: int = -1


async def get_effective_budget() -> float | None:
    """The Sheet's stored budget takes priority (it's the one you can change live);
    falls back to MONTHLY_BUDGET from .env if nothing's been set via /setbudget."""
    stored = await get_setting(_BUDGET_SETTING_KEY)
    if stored:
        try:
            value = float(stored)
            if value > 0:
                return value
        except ValueError:
            pass
    return settings.monthly_budget


async def set_budget(amount: float) -> None:
    await set_setting(_BUDGET_SETTING_KEY, f"{amount:.2f}")


def _reset_if_new_month(month_key: str) -> None:
    global _alerted_month_key, _alerted_threshold_index
    if month_key != _alerted_month_key:
        _alerted_month_key = month_key
        _alerted_threshold_index = -1


def check_threshold_alert(month_key: str, used_fraction: float) -> str | None:
    """Returns an alert message the first time `used_fraction` crosses a new
    threshold within the given calendar month (`month_key`, e.g. "2026-08"),
    otherwise None. Call this right after logging an expense.
    """
    global _alerted_threshold_index
    _reset_if_new_month(month_key)

    crossed_index = -1
    for i, threshold in enumerate(_ALERT_THRESHOLDS):
        if used_fraction >= threshold:
            crossed_index = i

    if crossed_index <= _alerted_threshold_index:
        return None

    _alerted_threshold_index = crossed_index
    pct = used_fraction * 100
    if _ALERT_THRESHOLDS[crossed_index] >= 1.0:
        return f"🚨 <b>Budget alert:</b> you've gone over your monthly budget ({pct:.0f}% used)."
    return f"⚠️ <b>Budget alert:</b> you've used {pct:.0f}% of your monthly budget."
