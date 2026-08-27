"""Single source of truth for rendering a ParsedTransaction as a Telegram message,
so the initial confirmation and every subsequent edit (category, direction flip)
look identical."""
from __future__ import annotations

from app.models import Direction, ParsedTransaction, category_label


def format_parsed_transaction(p: ParsedTransaction, show_low_confidence_hint: bool = True) -> str:
    arrow = "📈" if p.direction == Direction.INCOME else "📉"
    lines = [
        f"{arrow} <b>{p.amount:,.2f} {p.currency}</b> — {p.description}",
        f"Category: <b>{category_label(p.category)}</b>",
    ]
    if p.merchant:
        lines.append(f"Merchant: {p.merchant}")
    if show_low_confidence_hint and p.confidence < 0.6:
        lines.append("\n⚠️ I'm not fully confident I understood this correctly — please check before saving.")
    return "\n".join(lines)
