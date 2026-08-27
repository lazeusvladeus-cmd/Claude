"""Aggregation + chart generation for the /stats command and weekly digest.

All amounts are normalized to settings.base_currency before aggregating, so a
mixed UAH/USD history still produces one coherent picture.
"""
from __future__ import annotations

import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import matplotlib

matplotlib.use("Agg")  # headless rendering, no display server on a server box
import matplotlib.pyplot as plt

from app.config import settings
from app.models import Direction, Transaction, category_label
from app.services.fx import to_base_currency


@dataclass
class PeriodStats:
    total_spent: float = 0.0
    total_income: float = 0.0
    by_category: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    transaction_count: int = 0

    @property
    def net(self) -> float:
        return self.total_income - self.total_spent


async def compute_period_stats(transactions: list[Transaction], since: datetime) -> PeriodStats:
    stats = PeriodStats()
    for tx in transactions:
        tx_time = tx.timestamp if tx.timestamp.tzinfo else tx.timestamp.replace(tzinfo=timezone.utc)
        if tx_time < since:
            continue
        amount_base = await to_base_currency(tx.amount, tx.currency)
        if tx.direction == Direction.EXPENSE:
            stats.total_spent += amount_base
            stats.by_category[tx.category] += amount_base
        else:
            stats.total_income += amount_base
        stats.transaction_count += 1
    return stats


def render_category_pie_chart(stats: PeriodStats, title: str) -> bytes | None:
    """Returns PNG bytes of a category breakdown pie chart, or None if there's nothing to plot."""
    categories = {k: v for k, v in stats.by_category.items() if v > 0}
    if not categories:
        return None

    labels = list(categories.keys())
    values = list(categories.values())

    fig, ax = plt.subplots(figsize=(6, 6), dpi=150)
    colors = plt.get_cmap("tab20").colors
    ax.pie(
        values,
        # Plain text here (no emoji): matplotlib's default font can't render most emoji
        # glyphs, which would show as broken tofu boxes in the chart image.
        labels=[f"{lbl}\n{settings.base_currency} {val:,.0f}" for lbl, val in zip(labels, values)],
        autopct="%1.0f%%",
        colors=colors,
        textprops={"fontsize": 9},
        pctdistance=0.75,
    )
    ax.set_title(title, fontsize=13, fontweight="bold")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def format_stats_message(stats: PeriodStats, label: str) -> str:
    if stats.transaction_count == 0:
        return f"No transactions logged {label}."

    lines = [f"📊 <b>Spending {label}</b>", ""]
    lines.append(f"💸 Spent: <b>{settings.base_currency} {stats.total_spent:,.2f}</b>")
    if stats.total_income > 0:
        lines.append(f"💰 Income: <b>{settings.base_currency} {stats.total_income:,.2f}</b>")
        net_emoji = "✅" if stats.net >= 0 else "⚠️"
        lines.append(f"{net_emoji} Net: <b>{settings.base_currency} {stats.net:,.2f}</b>")
    lines.append("")

    if stats.by_category:
        lines.append("<b>By category:</b>")
        for cat, amount in sorted(stats.by_category.items(), key=lambda kv: -kv[1]):
            pct = (amount / stats.total_spent * 100) if stats.total_spent else 0
            lines.append(f"  {category_label(cat)}: {settings.base_currency} {amount:,.2f} ({pct:.0f}%)")

    lines.append("")
    lines.append(f"🧾 {stats.transaction_count} transaction(s)")
    return "\n".join(lines)


def since_days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)
