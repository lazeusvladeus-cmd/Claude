"""End-to-end tests for the Mini App's API endpoints (app/webapp/server.py),
with the Sheets layer mocked so these run offline and don't touch real credentials."""
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.models import Direction, Transaction
from app.webapp.server import app as webapp

ALLOWED_ID = 111  # matches tests/conftest.py


def _valid_init_data(user_id: int = ALLOWED_ID) -> str:
    data = {
        "user": json.dumps({"id": user_id}, separators=(",", ":")),
        "auth_date": str(int(time.time()) - 10),
    }
    secret_key = hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret_key, "\n".join(f"{k}={v}" for k, v in sorted(data.items())).encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


@pytest.fixture
def client():
    return TestClient(webapp)


@pytest.fixture
def auth_header():
    return {"X-Telegram-Init-Data": _valid_init_data()}


@pytest.fixture
def sample_transactions():
    return [
        Transaction(amount=25, currency="USD", category="Groceries", description="Eggs and bread"),
        Transaction(amount=500, currency="USD", category="Other", description="Paycheck", direction=Direction.INCOME),
    ]


def test_index_served_without_auth(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Finance Dashboard" in resp.text


def test_healthz_unauthenticated(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_openapi_schema_disabled(client):
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404


def test_summary_requires_auth(client):
    resp = client.get("/api/summary")
    assert resp.status_code == 401


def test_summary_rejects_bad_signature(client):
    resp = client.get("/api/summary", headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A111%7D&auth_date=1&hash=deadbeef"})
    assert resp.status_code == 401


def test_summary_happy_path(client, auth_header, sample_transactions):
    with patch("app.webapp.server.get_all_transactions", new=AsyncMock(return_value=sample_transactions)), \
         patch("app.webapp.server.budget_service.get_effective_budget", new=AsyncMock(return_value=1000.0)):
        resp = client.get("/api/summary", headers=auth_header)

    assert resp.status_code == 200
    body = resp.json()
    assert body["base_currency"] == "USD"
    assert body["week"]["total_spent"] == 25.0
    assert body["week"]["total_income"] == 500.0
    assert body["budget"] == {"target": 1000.0, "spent": 25.0, "used_pct": 2.5}
    assert len(body["recent_transactions"]) == 2
    assert len(body["categories"]) == 14


def test_summary_with_no_budget_set(client, auth_header, sample_transactions):
    with patch("app.webapp.server.get_all_transactions", new=AsyncMock(return_value=sample_transactions)), \
         patch("app.webapp.server.budget_service.get_effective_budget", new=AsyncMock(return_value=None)):
        resp = client.get("/api/summary", headers=auth_header)

    assert resp.status_code == 200
    assert resp.json()["budget"] is None


def test_summary_maps_sheets_error_to_502(client, auth_header):
    from app.services.sheets import SheetsError

    with patch("app.webapp.server.get_all_transactions", new=AsyncMock(side_effect=SheetsError("boom"))):
        resp = client.get("/api/summary", headers=auth_header)

    assert resp.status_code == 502


def test_set_budget_requires_auth(client):
    resp = client.post("/api/budget", json={"amount": 500})
    assert resp.status_code == 401


def test_set_budget_happy_path(client, auth_header):
    with patch("app.webapp.server.budget_service.set_budget", new=AsyncMock(return_value=None)) as mocked:
        resp = client.post("/api/budget", json={"amount": 750}, headers=auth_header)

    assert resp.status_code == 200
    mocked.assert_called_once_with(750.0)


def test_set_budget_rejects_nonpositive_amount(client, auth_header):
    resp = client.post("/api/budget", json={"amount": 0}, headers=auth_header)
    assert resp.status_code == 422
    resp = client.post("/api/budget", json={"amount": -10}, headers=auth_header)
    assert resp.status_code == 422


def test_set_budget_rejects_absurd_amount(client, auth_header):
    resp = client.post("/api/budget", json={"amount": 1e12}, headers=auth_header)
    assert resp.status_code == 422


def test_delete_transaction_happy_path(client, auth_header):
    with patch("app.webapp.server.delete_transaction", new=AsyncMock(return_value=True)):
        resp = client.delete("/api/transactions/abc123", headers=auth_header)
    assert resp.status_code == 200


def test_delete_transaction_not_found(client, auth_header):
    with patch("app.webapp.server.delete_transaction", new=AsyncMock(return_value=False)):
        resp = client.delete("/api/transactions/missing", headers=auth_header)
    assert resp.status_code == 404


def test_delete_transaction_requires_auth(client):
    resp = client.delete("/api/transactions/abc123")
    assert resp.status_code == 401


def test_update_category_happy_path(client, auth_header):
    with patch("app.webapp.server.update_transaction_category", new=AsyncMock(return_value=True)):
        resp = client.patch("/api/transactions/abc123/category", json={"category": "Groceries"}, headers=auth_header)
    assert resp.status_code == 200


def test_update_category_rejects_unknown_category(client, auth_header):
    resp = client.patch("/api/transactions/abc123/category", json={"category": "Yacht Fund"}, headers=auth_header)
    assert resp.status_code == 400


def test_update_category_not_found(client, auth_header):
    with patch("app.webapp.server.update_transaction_category", new=AsyncMock(return_value=False)):
        resp = client.patch("/api/transactions/missing/category", json={"category": "Groceries"}, headers=auth_header)
    assert resp.status_code == 404


def test_update_category_requires_auth(client):
    resp = client.patch("/api/transactions/abc123/category", json={"category": "Groceries"})
    assert resp.status_code == 401
