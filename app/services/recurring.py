"""Recurring-charge detection: the classic silent money leak (forgotten subscriptions).

Purely statistical, no AI call needed: groups transactions by (merchant-or-description,
currency), and flags groups that recur on a roughly-monthly cadence with a similar
amount each time. Cheap, deterministic, and explainable to the user.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, pstdev

from app.models import Direction, Transaction

_MIN_OCCURRENCES = 2
_MONTHLY_PERIOD_DAYS = 30
_PERIOD_TOLERANCE_DAYS = 6
_AMOUNT_TOLERANCE_RATIO = 0.15  # amounts within 15% of the mean count as "the same charge"


@dataclass
class RecurringCharge:
    label: str
    currency: str
    average_amount: float
    occurrences: int
    estimated_monthly_total: float


def detect_recurring_charges(transactions: list[Transaction]) -> list[RecurringCharge]:
    groups: dict[tuple[str, str], list[Transaction]] = defaultdict(list)
    for tx in transactions:
        if tx.direction != Direction.EXPENSE:
            continue
        key = ((tx.merchant or tx.description).strip().lower(), tx.currency)
        groups[key].append(tx)

    results: list[RecurringCharge] = []
    for (label, currency), txs in groups.items():
        if len(txs) < _MIN_OCCURRENCES:
            continue

        txs_sorted = sorted(txs, key=lambda t: t.timestamp)
        amounts = [t.amount for t in txs_sorted]
        avg_amount = mean(amounts)
        if avg_amount == 0:
            continue
        amount_spread = pstdev(amounts) / avg_amount if len(amounts) > 1 else 0
        if amount_spread > _AMOUNT_TOLERANCE_RATIO:
            continue

        gaps_days = [
            (txs_sorted[i].timestamp - txs_sorted[i - 1].timestamp).days for i in range(1, len(txs_sorted))
        ]
        if not gaps_days:
            continue
        avg_gap = mean(gaps_days)
        if abs(avg_gap - _MONTHLY_PERIOD_DAYS) > _PERIOD_TOLERANCE_DAYS:
            continue  # not roughly monthly

        results.append(
            RecurringCharge(
                label=txs_sorted[-1].merchant or txs_sorted[-1].description,
                currency=currency,
                average_amount=round(avg_amount, 2),
                occurrences=len(txs_sorted),
                estimated_monthly_total=round(avg_amount, 2),
            )
        )

    results.sort(key=lambda r: -r.estimated_monthly_total)
    return results
