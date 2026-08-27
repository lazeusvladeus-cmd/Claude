"""Handles Telegram voice notes (and audio file uploads) — the primary input path,
since this is what a Back Tap Shortcut and manual voice messages both produce."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message

from app.handlers.common import handle_transcript
from app.security import rate_limiter
from app.services.transcription import TranscriptionError, transcribe_voice

logger = logging.getLogger(__name__)
router = Router(name="voice")


@router.message(F.voice)
@router.message(F.audio)
async def on_voice_message(message: Message) -> None:
    if not rate_limiter.allow(message.from_user.id):
        await message.answer("⏳ You're sending requests a bit fast — please wait a minute and try again.")
        return

    file = message.voice or message.audio
    if file is None:
        return

    status = await message.answer("🎙️ Transcribing…")
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        tg_file = await message.bot.get_file(file.file_id)
        buf = await message.bot.download_file(tg_file.file_path)
        audio_bytes = buf.read()
    except Exception:
        logger.exception("Failed to download voice file from Telegram")
        await status.edit_text("⚠️ Couldn't download that voice message from Telegram. Please try again.")
        return

    try:
        text = await transcribe_voice(audio_bytes, filename="voice.ogg")
    except TranscriptionError as exc:
        await status.edit_text(f"❓ {exc}")
        return
    except Exception:
        logger.exception("Unexpected transcription failure")
        await status.edit_text("⚠️ Transcription failed. Please try again in a moment.")
        return

    await status.edit_text(f"🗣️ Heard: <i>“{text}”</i>\n\n🧠 Parsing…")
    await handle_transcript(message, text, source="voice", status=status)
