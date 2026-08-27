from datetime import datetime, timedelta, timezone

import pytest

from app.models import Direction, Transaction
from app.services.stats import (
    compute_period_stats,
    format_stats_message,
    format_trend,
    month_key,
    since_days_ago,
    start_of_this_month,
)
from app.services.recurring import detect_recurring_charges


def _tx(days_ago: int, amount: float, category: str = "Groceries", direction: Direction = Direction.EXPENSE, merchant=None):
    return Transaction(
        amount=amount,
        currency="USD",  # matches BASE_CURRENCY in tests, so fx conversion is a no-op (no network)
        category=category,
        description="test",
        direction=direction,
        merchant=merchant,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


@pytest.mark.asyncio
async def test_compute_period_stats_excludes_transactions_before_window():
    txs = [_tx(days_ago=1, amount=10), _tx(days_ago=40, amount=999)]
    stats = await compute_period_stats(txs, since=since_days_ago(7))
    assert stats.total_spent == 10
    assert stats.transaction_count == 1


@pytest.mark.asyncio
async def test_compute_period_stats_separates_income_and_expense():
    txs = [_tx(days_ago=1, amount=100), _tx(days_ago=1, amount=500, direction=Direction.INCOME)]
    stats = await compute_period_stats(txs, since=since_days_ago(7))
    assert stats.total_spent == 100
    assert stats.total_income == 500
    assert stats.net == 400


@pytest.mark.asyncio
async def test_compute_period_stats_groups_by_category():
    txs = [_tx(days_ago=1, amount=10, category="Groceries"), _tx(days_ago=1, amount=20, category="Transport")]
    stats = await compute_period_stats(txs, since=since_days_ago(7))
    assert stats.by_category["Groceries"] == 10
    assert stats.by_category["Transport"] == 20


@pytest.mark.asyncio
async def test_format_stats_message_handles_empty_period():
    stats = await compute_period_stats([], since=since_days_ago(7))
    text = format_stats_message(stats, "last 7 days")
    assert "No transactions" in text


def test_detect_recurring_charges_flags_monthly_same_amount():
    txs = [
        _tx(days_ago=90, amount=9.99, merchant="Netflix"),
        _tx(days_ago=60, amount=9.99, merchant="Netflix"),
        _tx(days_ago=30, amount=9.99, merchant="Netflix"),
    ]
    results = detect_recurring_charges(txs)
    assert len(results) == 1
    assert results[0].label == "Netflix"
    assert results[0].occurrences == 3


def test_detect_recurring_charges_ignores_one_off_purchases():
    txs = [_tx(days_ago=5, amount=42, merchant="Random Shop")]
    results = detect_recurring_charges(txs)
    assert results == []


def test_detect_recurring_charges_ignores_irregular_intervals():
    txs = [
        _tx(days_ago=90, amount=9.99, merchant="Sometimes Store"),
        _tx(days_ago=85, amount=9.99, merchant="Sometimes Store"),  # 5 days apart, not monthly
    ]
    results = detect_recurring_charges(txs)
    assert results == []


@pytest.mark.asyncio
async def test_compute_period_stats_respects_until_bound():
    txs = [_tx(days_ago=5, amount=10), _tx(days_ago=15, amount=20), _tx(days_ago=25, amount=30)]
    stats = await compute_period_stats(txs, since=since_days_ago(20), until=since_days_ago(10))
    assert stats.total_spent == 20  # only the days_ago=15 transaction falls in [20, 10) days ago
    assert stats.transaction_count == 1


def test_format_trend_reports_increase():
    trend = format_trend(current_total=150, previous_total=100)
    assert "50%" in trend
    assert "more" in trend
    assert "📈" in trend


def test_format_trend_reports_decrease():
    trend = format_trend(current_total=50, previous_total=100)
    assert "50%" in trend
    assert "less" in trend
    assert "📉" in trend


def test_format_trend_handles_no_previous_baseline():
    assert format_trend(current_total=50, previous_total=0) is None


def test_format_trend_handles_roughly_equal():
    trend = format_trend(current_total=100.5, previous_total=100)
    assert "same" in trend.lower()


def test_start_of_this_month_is_first_day_midnight():
    start = start_of_this_month()
    assert start.day == 1
    assert start.hour == 0 and start.minute == 0 and start.second == 0


def test_month_key_format():
    key = month_key()
    assert len(key) == 7  # "YYYY-MM"
    assert key[4] == "-"


def test_detect_recurring_charges_ignores_income():
    txs = [
        _tx(days_ago=60, amount=1000, merchant="Employer", direction=Direction.INCOME),
        _tx(days_ago=30, amount=1000, merchant="Employer", direction=Direction.INCOME),
    ]
    results = detect_recurring_charges(txs)
    assert results == []
