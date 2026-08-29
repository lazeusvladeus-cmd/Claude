"""Google Sheets as the transaction store.

Authenticates with the same user-OAuth credentials as Calendar (see
services/google_oauth.py) rather than a service-account key — Google now
blocks service-account key creation by default on many accounts, and signing
in as yourself means the Sheet just needs to be yours; no "share with a robot
email" step.

gspread is synchronous, so every call is pushed to a thread executor to avoid
blocking the bot's event loop. All writes are append-only (we never edit/delete
rows programmatically except the explicit "undo last" path), so the sheet stays
a trustworthy, human-readable ledger the user can also open and read directly.
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

import gspread

from app.config import settings
from app.models import Transaction
from app.services.google_oauth import GoogleAuthNotConfigured, load_credentials

logger = logging.getLogger(__name__)

_TRANSACTIONS_SHEET = "Transactions"
_SETTINGS_SHEET = "Settings"

_lock = asyncio.Lock()  # serialize writes; gspread client isn't safe for concurrent use
_settings_lock = asyncio.Lock()  # separate lock: settings reads/writes shouldn't queue behind transaction ones
_worksheet_cache: gspread.Worksheet | None = None  # avoids re-opening the sheet on every call
_settings_worksheet_cache: gspread.Worksheet | None = None


class SheetsError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _client() -> gspread.Client:
    try:
        creds = load_credentials()
    except GoogleAuthNotConfigured as exc:
        raise SheetsError(str(exc)) from exc
    return gspread.authorize(creds)


def _open_spreadsheet_sync() -> gspread.Spreadsheet:
    try:
        return _client().open_by_key(settings.google_sheet_id)
    except gspread.exceptions.APIError as exc:
        raise SheetsError(
            "Could not open the configured Google Sheet. Double-check GOOGLE_SHEET_ID and that "
            "the sheet is shared with the service account's client_email as an Editor."
        ) from exc


def _get_or_create_worksheet_sync() -> gspread.Worksheet:
    sh = _open_spreadsheet_sync()
    try:
        ws = sh.worksheet(_TRANSACTIONS_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=_TRANSACTIONS_SHEET, rows=1000, cols=len(Transaction.header_row()))
        ws.append_row(Transaction.header_row())
    return ws


async def _worksheet(force_refresh: bool = False) -> gspread.Worksheet:
    global _worksheet_cache
    if _worksheet_cache is None or force_refresh:
        _worksheet_cache = await asyncio.to_thread(_get_or_create_worksheet_sync)
    return _worksheet_cache


async def _get_all_values() -> list[list[str]]:
    """Read the full sheet, transparently recovering once if the cached worksheet
    handle went stale (e.g. the tab was renamed/recreated out-of-band)."""
    ws = await _worksheet()
    try:
        return await asyncio.to_thread(ws.get_all_values)
    except gspread.exceptions.APIError:
        logger.warning("Cached worksheet handle failed; refreshing and retrying once")
        ws = await _worksheet(force_refresh=True)
        return await asyncio.to_thread(ws.get_all_values)


async def append_transaction(tx: Transaction) -> None:
    async with _lock:
        ws = await _worksheet()
        try:
            await asyncio.to_thread(ws.append_row, tx.to_row(), value_input_option="USER_ENTERED")
        except gspread.exceptions.APIError:
            logger.warning("Cached worksheet handle failed on append; refreshing and retrying once")
            ws = await _worksheet(force_refresh=True)
            await asyncio.to_thread(ws.append_row, tx.to_row(), value_input_option="USER_ENTERED")


async def delete_last_transaction(user_confirmation_id: str) -> bool:
    """Delete the most recent row IF its id matches `user_confirmation_id`.

    The id check exists so /undo can't accidentally delete a row that changed
    between the user seeing it and confirming the undo (e.g. a concurrent add).
    """
    async with _lock:
        all_values = await _get_all_values()
        if len(all_values) <= 1:
            return False  # only header, nothing to delete
        last_row_index = len(all_values)  # 1-indexed, includes header offset
        last_row = all_values[-1]
        if not last_row or last_row[0] != user_confirmation_id:
            return False
        ws = await _worksheet()
        await asyncio.to_thread(ws.delete_rows, last_row_index)
        return True


async def get_last_transaction() -> Transaction | None:
    all_values = await _get_all_values()
    if len(all_values) <= 1:
        return None
    return _row_to_transaction(all_values[-1])


async def get_all_transactions() -> list[Transaction]:
    all_values = await _get_all_values()
    if len(all_values) <= 1:
        return []
    rows = all_values[1:]
    out: list[Transaction] = []
    for row in rows:
        try:
            out.append(_row_to_transaction(row))
        except Exception:
            logger.exception("Skipping malformed sheet row: %r", row)
    return out


def _row_to_transaction(row: list[str]) -> Transaction:
    # Pad defensively in case a row was manually edited and left short.
    row = row + [""] * (len(Transaction.header_row()) - len(row))
    return Transaction(
        id=row[0],
        timestamp=row[1],
        direction=row[2] or "expense",
        amount=float(row[3]),
        currency=row[4],
        category=row[5],
        description=row[6],
        merchant=row[7] or None,
        source=row[8] or "unknown",
        raw_text=row[9],
    )


def sheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{settings.google_sheet_id}/edit"


# --- Settings tab: a tiny key/value store for things that should be user-adjustable at
# runtime (e.g. the monthly budget) without needing a redeploy to change an env var. ---


def _get_or_create_settings_worksheet_sync() -> gspread.Worksheet:
    sh = _open_spreadsheet_sync()
    try:
        ws = sh.worksheet(_SETTINGS_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=_SETTINGS_SHEET, rows=50, cols=2)
        ws.append_row(["key", "value"])
    return ws


async def _settings_worksheet(force_refresh: bool = False) -> gspread.Worksheet:
    global _settings_worksheet_cache
    if _settings_worksheet_cache is None or force_refresh:
        _settings_worksheet_cache = await asyncio.to_thread(_get_or_create_settings_worksheet_sync)
    return _settings_worksheet_cache


async def get_setting(key: str) -> str | None:
    """Look up a value from the Settings tab, or None if it isn't set."""
    async with _settings_lock:
        ws = await _settings_worksheet()
        try:
            rows = await asyncio.to_thread(ws.get_all_values)
        except gspread.exceptions.APIError:
            ws = await _settings_worksheet(force_refresh=True)
            rows = await asyncio.to_thread(ws.get_all_values)

    for row in rows[1:]:  # skip header
        if len(row) >= 2 and row[0] == key:
            return row[1]
    return None


async def set_setting(key: str, value: str) -> None:
    """Upsert a key/value pair in the Settings tab."""
    async with _settings_lock:
        ws = await _settings_worksheet()
        rows = await asyncio.to_thread(ws.get_all_values)

        for i, row in enumerate(rows[1:], start=2):  # 1-indexed, +1 for header
            if len(row) >= 1 and row[0] == key:
                await asyncio.to_thread(ws.update, f"A{i}:B{i}", [[key, value]])
                return

        await asyncio.to_thread(ws.append_row, [key, value])
