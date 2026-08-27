"""Shared logic between the voice and text entry points: text -> parsed transaction
-> pending confirmation message. Kept in one place so both paths behave identically."""
from __future__ import annotations

import logging

from aiogram.types import Message

from app.formatting import format_parsed_transaction
from app.keyboards import confirm_transaction_kb
from app.pending_store import put
from app.services.nlp import NlpParseError, parse_transaction

logger = logging.getLogger(__name__)


async def handle_transcript(message: Message, text: str, source: str, status: Message | None = None) -> None:
    """Parse `text` (already-transcribed voice, or typed text) and ask the user to confirm.

    If `status` is given (an existing "..." status message), it's edited in place
    instead of sending a new message — keeps a voice note down to one status
    message that progresses through its stages rather than a pile of separate ones.
    """
    if status is None:
        status = await message.answer("🧠 Parsing…")

    try:
        parsed = await parse_transaction(text)
    except NlpParseError as exc:
        await status.edit_text(f"❓ {exc}")
        return
    except Exception:
        logger.exception("Unexpected error parsing transcript")
        await status.edit_text(
            "⚠️ Something went wrong talking to the AI service. Please try again in a moment."
        )
        return

    pending_id = put(parsed, raw_text=text, source=source, user_id=message.from_user.id)
    await status.edit_text(
        format_parsed_transaction(parsed),
        reply_markup=confirm_transaction_kb(pending_id),
    )
