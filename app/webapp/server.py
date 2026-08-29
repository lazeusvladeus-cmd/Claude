"""FastAPI backend for the Mini App dashboard.

Runs inside the same process as the bot (see app/main.py, which serves this
alongside Telegram polling) and reuses every existing service — no separate
data layer, no duplicated business logic. Every route re-verifies Telegram's
initData itself; nothing here is reachable without it.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.models import CATEGORIES, category_label
from app.services import budget as budget_service
from app.services.sheets import (
    SheetsError,
    delete_transaction,
    get_all_transactions,
    update_transaction_category,
)
from app.services.stats import (
    compute_period_stats,
    format_trend,
    since_days_ago,
    start_of_this_month,
)
from app.webapp.auth import InitDataInvalid, verify_init_data

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
RECENT_TRANSACTIONS_LIMIT = 40

app = FastAPI(title="Finance Bot Dashboard", docs_url=None, redoc_url=None, openapi_url=None)


def _authenticate(x_telegram_init_data: str | None) -> int:
    try:
        return verify_init_data(x_telegram_init_data or "")
    except InitDataInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
async def healthz() -> dict:
    """Unauthenticated liveness check, for the hosting platform — carries no user data."""
    return {"ok": True}


def _period_payload(stats) -> dict:
    return {
        "total_spent": round(stats.total_spent, 2),
        "total_income": round(stats.total_income, 2),
        "by_category": {cat: round(amount, 2) for cat, amount in stats.by_category.items()},
        "count": stats.transaction_count,
    }


@app.get("/api/summary")
async def api_summary(x_telegram_init_data: str | None = Header(default=None)) -> dict:
    _authenticate(x_telegram_init_data)

    try:
        transactions = await get_all_transactions()

        week = await compute_period_stats(transactions, since=since_days_ago(7))
        month = await compute_period_stats(transactions, since=since_days_ago(30))
        prev_month = await compute_period_stats(transactions, since=since_days_ago(60), until=since_days_ago(30))
        month_to_date = await compute_period_stats(transactions, since=start_of_this_month())

        target = await budget_service.get_effective_budget()
    except SheetsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    budget_data = None
    if target:
        budget_data = {
            "target": round(target, 2),
            "spent": round(month_to_date.total_spent, 2),
            "used_pct": round((month_to_date.total_spent / target) * 100, 1) if target else 0,
        }

    recent = sorted(transactions, key=lambda t: t.timestamp, reverse=True)[:RECENT_TRANSACTIONS_LIMIT]

    return {
        "base_currency": settings.base_currency,
        "week": _period_payload(week),
        "month": {**_period_payload(month), "trend": format_trend(month.total_spent, prev_month.total_spent)},
        "budget": budget_data,
        "recent_transactions": [
            {
                "id": t.id,
                "timestamp": t.timestamp.isoformat(),
                "amount": t.amount,
                "currency": t.currency,
                "direction": t.direction.value,
                "category": t.category,
                "category_label": category_label(t.category),
                "description": t.description,
                "merchant": t.merchant,
            }
            for t in recent
        ],
        "categories": [{"value": c, "label": category_label(c)} for c in CATEGORIES],
    }


class SetBudgetRequest(BaseModel):
    amount: float = Field(gt=0, le=100_000_000)


@app.post("/api/budget")
async def api_set_budget(
    body: SetBudgetRequest, x_telegram_init_data: str | None = Header(default=None)
) -> dict:
    _authenticate(x_telegram_init_data)
    try:
        await budget_service.set_budget(body.amount)
    except SheetsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True}


@app.delete("/api/transactions/{tx_id}")
async def api_delete_transaction(
    tx_id: str, x_telegram_init_data: str | None = Header(default=None)
) -> dict:
    _authenticate(x_telegram_init_data)
    try:
        deleted = await delete_transaction(tx_id)
    except SheetsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return {"ok": True}


class UpdateCategoryRequest(BaseModel):
    category: str


@app.patch("/api/transactions/{tx_id}/category")
async def api_update_category(
    tx_id: str, body: UpdateCategoryRequest, x_telegram_init_data: str | None = Header(default=None)
) -> dict:
    _authenticate(x_telegram_init_data)
    if body.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Unknown category.")
    try:
        updated = await update_transaction_category(tx_id, body.category)
    except SheetsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return {"ok": True}
