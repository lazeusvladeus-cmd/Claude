"""Plain typed messages are treated as manual expense entries — the fallback/correction
path when voice transcription gets something wrong, or you'd just rather type it."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.handlers.common import handle_transcript
from app.security import rate_limiter

router = Router(name="text")


@router.message(F.text & ~F.text.startswith("/"))
async def on_text_message(message: Message) -> None:
    if not rate_limiter.allow(message.from_user.id):
        await message.answer("⏳ You're sending requests a bit fast — please wait a minute and try again.")
        return
    await handle_transcript(message, message.text, source="text")


@router.message()
async def on_unsupported_content(message: Message) -> None:
    """Anything that isn't voice/audio/text/a recognized command falls through to here
    (registered last, so it never steals messages other handlers already claimed)."""
    await message.answer(
        "I can only understand voice messages or typed text for logging expenses. "
        "Send /help to see what I can do."
    )
