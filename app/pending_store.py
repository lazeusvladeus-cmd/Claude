"""Short-lived in-memory holding area for a parsed-but-not-yet-confirmed transaction.

Telegram callback_data is capped at 64 bytes, so we can't stuff a full transaction
into it — instead we stash the pending ParsedTransaction here under a short id and
only send that id over the wire. Entries expire after PENDING_TTL_SECONDS so a
stale "Save" tap on a days-old message can't silently resurrect and write old data.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from app.models import Direction, ParsedTransaction

PENDING_TTL_SECONDS = 15 * 60


@dataclass
class PendingEntry:
    parsed: ParsedTransaction
    raw_text: str
    source: str
    user_id: int
    created_at: float


_store: dict[str, PendingEntry] = {}


def _purge_expired() -> None:
    now = time.monotonic()
    expired = [k for k, v in _store.items() if now - v.created_at > PENDING_TTL_SECONDS]
    for k in expired:
        _store.pop(k, None)


def put(parsed: ParsedTransaction, raw_text: str, source: str, user_id: int) -> str:
    _purge_expired()
    pending_id = uuid.uuid4().hex[:10]
    _store[pending_id] = PendingEntry(
        parsed=parsed, raw_text=raw_text, source=source, user_id=user_id, created_at=time.monotonic()
    )
    return pending_id


def get(pending_id: str, user_id: int) -> PendingEntry | None:
    _purge_expired()
    entry = _store.get(pending_id)
    if entry is None or entry.user_id != user_id:
        return None
    return entry


def update_category(pending_id: str, user_id: int, category: str) -> PendingEntry | None:
    entry = get(pending_id, user_id)
    if entry is None:
        return None
    entry.parsed = entry.parsed.model_copy(update={"category": category})
    return entry


def flip_direction(pending_id: str, user_id: int) -> PendingEntry | None:
    entry = get(pending_id, user_id)
    if entry is None:
        return None
    flipped = Direction.INCOME if entry.parsed.direction == Direction.EXPENSE else Direction.EXPENSE
    entry.parsed = entry.parsed.model_copy(update={"direction": flipped})
    return entry


def pop(pending_id: str, user_id: int) -> PendingEntry | None:
    entry = get(pending_id, user_id)
    if entry is not None:
        _store.pop(pending_id, None)
    return entry
