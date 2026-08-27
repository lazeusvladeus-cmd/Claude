"""Transcript/text -> structured ParsedTransaction, via an OpenAI JSON-mode call."""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI
from pydantic import ValidationError
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.models import CATEGORIES, ParsedTransaction

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.openai_api_key)

_SYSTEM_PROMPT = f"""You turn a short spoken-language sentence about money into structured JSON.

The user speaks casually, possibly in English, Ukrainian, or Russian, about something
they spent or received money on. Extract exactly one transaction.

The user regularly spends in these currencies: {", ".join(settings.tracked_currency_list)}.

Respond with ONLY a JSON object with these fields:
- amount: number, always positive
- currency: 3-letter ISO code. If no currency is stated, infer from context (₴/грн/uah -> UAH,
  $/usd/dollars -> USD, and similarly for other currencies the user regularly uses); if truly
  ambiguous default to "{settings.base_currency}".
- category: exactly one of {CATEGORIES}
- description: short (<=8 words) human description, in English, e.g. "Coffee with Anna"
- direction: "expense" or "income" (default "expense" unless clearly a paycheck/refund/gift received)
- merchant: store/person/service name if mentioned, else null
- confidence: your confidence 0.0-1.0 that this extraction is correct

If the sentence contains NO identifiable amount of money at all, respond with:
{{"error": "no_amount_found"}}
"""


class NlpParseError(RuntimeError):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_not_exception_type(NlpParseError),
)
async def _call_model(text: str) -> str:
    response = await _client.chat.completions.create(
        model=settings.openai_text_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=300,
    )
    content = response.choices[0].message.content
    if not content:
        raise NlpParseError("Model returned an empty response.")
    return content


async def parse_transaction(text: str) -> ParsedTransaction:
    """Parse free-form text describing a purchase into a ParsedTransaction.

    Raises NlpParseError if no amount could be found, or the model's output
    doesn't fit our schema (bad amount, malformed JSON, etc).
    """
    text = text.strip()
    if not text:
        raise NlpParseError("There's no text to parse.")

    raw = await _call_model(text)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Model returned non-JSON output: %r", raw)
        raise NlpParseError("Sorry, I couldn't understand that as a transaction.") from exc

    if isinstance(data, dict) and data.get("error") == "no_amount_found":
        raise NlpParseError(
            "I couldn't find an amount in that. Try something like "
            "\"twenty dollars for groceries\"."
        )

    try:
        return ParsedTransaction(**data)
    except ValidationError as exc:
        logger.error("Model output failed validation: %r (%s)", data, exc)
        raise NlpParseError("Sorry, I couldn't understand that as a transaction. Could you rephrase?") from exc


async def generate_savings_advice(summary: str) -> str:
    """Ask the model for concrete, personalized savings suggestions given a spending summary.

    `summary` is a compact, pre-aggregated text block (category totals, trends, recurring
    charges) — we never send raw individual transaction descriptions beyond what's needed,
    keeping prompts small and cheap.
    """
    response = await _client.chat.completions.create(
        model=settings.openai_text_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a blunt but friendly personal-finance coach. Given a summary of "
                    "someone's recent spending, give 3-5 short, concrete, specific suggestions "
                    "for where they could realistically save money. Reference actual categories "
                    "and numbers from the summary. No generic advice like 'make a budget'. "
                    "Keep the whole reply under 120 words. Use plain text with a leading emoji "
                    "per bullet, no markdown headers."
                ),
            },
            {"role": "user", "content": summary},
        ],
        temperature=0.4,
        max_tokens=350,
    )
    content = response.choices[0].message.content
    return (content or "").strip() or "Not enough data yet to give tailored advice — keep logging expenses!"
