"""Voice note -> text, via OpenAI's transcription API."""
from __future__ import annotations

import logging
from io import BytesIO

from openai import AsyncOpenAI
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.openai_api_key)

# Telegram voice notes are small (a few minutes of speech, opus/ogg); this is a generous
# ceiling so a runaway/garbled recording can't turn into a giant, expensive upload.
MAX_VOICE_BYTES = 20 * 1024 * 1024  # 20 MB


class TranscriptionError(RuntimeError):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_not_exception_type(TranscriptionError),
)
async def _call_whisper(buf: BytesIO):
    try:
        return await _client.audio.transcriptions.create(
            model=settings.openai_transcribe_model,
            file=buf,
        )
    except Exception:
        logger.exception("Transcription request failed")
        raise


async def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Send raw audio bytes to Whisper and return the transcript text.

    Raises TranscriptionError for bad input (validated up-front, never retried);
    transient API/network errors are retried automatically.
    """
    if not audio_bytes:
        raise TranscriptionError("Received an empty voice message.")
    if len(audio_bytes) > MAX_VOICE_BYTES:
        raise TranscriptionError(
            f"Voice message is too large ({len(audio_bytes) / 1e6:.1f} MB). "
            f"Please keep recordings under {MAX_VOICE_BYTES / 1e6:.0f} MB."
        )

    buf = BytesIO(audio_bytes)
    buf.name = filename  # the OpenAI SDK reads .name to infer content type

    result = await _call_whisper(buf)

    text = (result.text or "").strip()
    if not text:
        raise TranscriptionError("Could not make out any speech in that recording — could you try again?")
    return text
