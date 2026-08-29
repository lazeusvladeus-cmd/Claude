"""Telegram Mini App initData verification.

This is the only thing standing between "a private dashboard only you can open"
and "anyone who finds the URL can read your finances" — the Mini App's frontend
runs in a browser-like WebView, so nothing about the request can be trusted
just because it came from the right-looking URL. Telegram signs a payload
(`initData`) with an HMAC derived from the bot token every time the Mini App is
opened; verifying that signature server-side, on every request, is the only way
to know a request genuinely came from Telegram and genuinely came from you.

Algorithm per Telegram's docs: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from app.config import settings

# Telegram regenerates initData fresh every time the Mini App is opened, and the frontend
# fetches data within seconds of that — so this isn't a real session lifetime, it's a
# ceiling on how long a captured initData string could be replayed if it ever leaked (e.g.
# via a proxy log or browser history). Kept short since normal usage never needs it long;
# generous enough that leaving the dashboard open and idle for a while doesn't cause errors.
MAX_INIT_DATA_AGE_SECONDS = 60 * 60


class InitDataInvalid(RuntimeError):
    pass


def verify_init_data(init_data: str) -> int:
    """Verify Telegram WebApp initData and return the authenticated user's Telegram id.

    Raises InitDataInvalid if the signature is wrong, the data is stale, or the
    resulting user isn't in ALLOWED_TELEGRAM_USER_IDS — the same allowlist the bot
    itself enforces, so the dashboard can never be a side door around it.
    """
    if not init_data:
        raise InitDataInvalid("Missing Telegram init data.")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataInvalid("Missing signature.")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise InitDataInvalid("Signature verification failed.")

    auth_date_raw = pairs.get("auth_date")
    if not auth_date_raw:
        raise InitDataInvalid("Missing auth_date.")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise InitDataInvalid("Malformed auth_date.") from exc
    if (time.time() - auth_date) > MAX_INIT_DATA_AGE_SECONDS:
        raise InitDataInvalid("This session is stale — please reopen the app from Telegram.")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InitDataInvalid("Missing user info.")
    try:
        user = json.loads(user_raw)
        user_id = int(user["id"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise InitDataInvalid("Malformed user info.") from exc

    if user_id not in settings.allowed_user_ids:
        raise InitDataInvalid("This Telegram account isn't authorized for this bot.")

    return user_id
