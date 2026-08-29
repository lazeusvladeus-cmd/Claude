"""Tests for Telegram Mini App initData verification (app/webapp/auth.py) — the
sole gate between the dashboard and your financial data, so this earns direct
coverage of the HMAC signing algorithm itself, not just the happy path."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.config import settings
from app.webapp.auth import InitDataInvalid, verify_init_data


def _sign(data: dict, bot_token: str) -> str:
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()


def _build_init_data(user_id: int, bot_token: str, *, age_seconds: int = 10, extra: dict | None = None) -> str:
    data = {
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
        "auth_date": str(int(time.time()) - age_seconds),
        "query_id": "AAABBBCCC",
        **(extra or {}),
    }
    data["hash"] = _sign(data, bot_token)
    return urlencode(data)


ALLOWED_ID = 111  # matches tests/conftest.py's ALLOWED_TELEGRAM_USER_IDS
OTHER_ID = 222
UNAUTHORIZED_ID = 999999


def test_valid_init_data_returns_user_id():
    init_data = _build_init_data(ALLOWED_ID, settings.telegram_bot_token)
    assert verify_init_data(init_data) == ALLOWED_ID


def test_second_allowed_user_also_accepted():
    init_data = _build_init_data(OTHER_ID, settings.telegram_bot_token)
    assert verify_init_data(init_data) == OTHER_ID


def test_rejects_user_not_in_allowlist():
    init_data = _build_init_data(UNAUTHORIZED_ID, settings.telegram_bot_token)
    with pytest.raises(InitDataInvalid, match="isn't authorized"):
        verify_init_data(init_data)


def test_rejects_signature_signed_with_wrong_token():
    init_data = _build_init_data(ALLOWED_ID, "wrong-bot-token")
    with pytest.raises(InitDataInvalid, match="Signature verification failed"):
        verify_init_data(init_data)


def test_rejects_tampered_payload_after_signing():
    """A valid signature for a *different* user shouldn't validate once the user
    field is swapped post-signing — catches naive implementations that verify
    the hash but read fields from the raw (attacker-editable) string instead."""
    init_data = _build_init_data(ALLOWED_ID, settings.telegram_bot_token)
    tampered = init_data.replace(str(ALLOWED_ID), str(UNAUTHORIZED_ID))
    with pytest.raises(InitDataInvalid, match="Signature verification failed"):
        verify_init_data(tampered)


def test_rejects_stale_auth_date():
    init_data = _build_init_data(ALLOWED_ID, settings.telegram_bot_token, age_seconds=2 * 60 * 60)
    with pytest.raises(InitDataInvalid, match="stale"):
        verify_init_data(init_data)


def test_accepts_data_just_under_the_staleness_window():
    init_data = _build_init_data(ALLOWED_ID, settings.telegram_bot_token, age_seconds=30 * 60)
    assert verify_init_data(init_data) == ALLOWED_ID


def test_rejects_missing_hash():
    with pytest.raises(InitDataInvalid, match="Missing signature"):
        verify_init_data("user=%7B%22id%22%3A111%7D&auth_date=123")


def test_rejects_empty_string():
    with pytest.raises(InitDataInvalid, match="Missing"):
        verify_init_data("")


def test_rejects_missing_user_field():
    data = {"auth_date": str(int(time.time()))}
    data["hash"] = _sign(data, settings.telegram_bot_token)
    with pytest.raises(InitDataInvalid, match="Missing user info"):
        verify_init_data(urlencode(data))


def test_rejects_malformed_user_json():
    data = {"auth_date": str(int(time.time())), "user": "not-json"}
    data["hash"] = _sign(data, settings.telegram_bot_token)
    with pytest.raises(InitDataInvalid, match="Malformed user info"):
        verify_init_data(urlencode(data))
