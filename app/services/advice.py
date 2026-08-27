"""Ties together stats + recurring-charge detection + the LLM to produce the
weekly savings digest and on-demand /advice replies.
"""
from __future__ import annotations

from app.config import settings
from app.models import Transaction
from app.services.nlp import generate_savings_advice
from app.services.recurring import detect_recurring_charges
from app.services.stats import PeriodStats, compute_period_stats, since_days_ago


def _build_summary_text(stats: PeriodStats, recurring, budget_used_pct: float | None) -> str:
    lines = [f"Currency: {settings.base_currency}", f"Total spent (last 30 days): {stats.total_spent:.2f}"]
    if budget_used_pct is not None:
        lines.append(f"Monthly budget usage so far: {budget_used_pct:.0f}%")
    if stats.by_category:
        lines.append("Spending by category:")
        for cat, amount in sorted(stats.by_category.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - {cat}: {amount:.2f}")
    if recurring:
        lines.append("Detected recurring monthly charges:")
        for r in recurring:
            lines.append(f"  - {r.label}: {r.average_amount:.2f} {r.currency} ({r.occurrences}x seen)")
    return "\n".join(lines)


async def build_savings_digest(all_transactions: list[Transaction]) -> str:
    stats = await compute_period_stats(all_transactions, since=since_days_ago(30))
    recurring = detect_recurring_charges([t for t in all_transactions if t.timestamp >= since_days_ago(90)])

    budget_used_pct = None
    if settings.monthly_budget:
        budget_used_pct = (stats.total_spent / settings.monthly_budget) * 100

    if stats.transaction_count == 0:
        return (
            "📭 No spending logged in the last 30 days, so there's nothing to analyze yet.\n"
            "Send a voice note or text whenever you spend something and check back next week!"
        )

    summary = _build_summary_text(stats, recurring, budget_used_pct)
    advice_text = await generate_savings_advice(summary)

    header = "💡 <b>Your weekly savings digest</b>\n\n"
    body = f"Last 30 days: <b>{settings.base_currency} {stats.total_spent:,.2f}</b> spent across {stats.transaction_count} transactions.\n"
    if budget_used_pct is not None:
        warn = " ⚠️" if budget_used_pct >= 90 else ""
        body += f"Monthly budget used: <b>{budget_used_pct:.0f}%</b>{warn}\n"

    recurring_block = ""
    if recurring:
        recurring_lines = "\n".join(
            f"  • {r.label}: {settings.base_currency} {r.average_amount:,.2f}/mo" for r in recurring[:5]
        )
        recurring_total = sum(r.estimated_monthly_total for r in recurring)
        recurring_block = (
            f"\n🔁 <b>Recurring charges detected</b> (~{settings.base_currency} {recurring_total:,.2f}/mo):\n"
            f"{recurring_lines}\n"
        )

    return f"{header}{body}{recurring_block}\n{advice_text}"
