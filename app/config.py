"""Centralized, validated configuration loaded once from environment variables.

Fails fast at startup if anything required is missing/malformed, rather than
surfacing a confusing error deep inside a handler at 2am.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str
    allowed_telegram_user_ids: str  # comma-separated, parsed below

    # OpenAI
    openai_api_key: str
    openai_transcribe_model: str = "whisper-1"
    openai_text_model: str = "gpt-4o-mini"

    # Google Sheets
    google_sheet_id: str

    # Google (shared OAuth for both Sheets and Calendar)
    google_oauth_client_file: str = "./secrets/oauth_client.json"
    google_token_file: str = "./secrets/calendar_token.json"
    google_calendar_id: str = "primary"
    calendar_reminder_minutes_before: int = 20

    # Currency
    base_currency: str = "USD"
    tracked_currencies: str = "USD,UAH"

    # Budget / advice
    monthly_budget: float | None = None
    weekly_digest_dow: int = 6
    weekly_digest_hour: int = 19

    # Misc
    timezone: str = "Europe/Kyiv"
    rate_limit_per_minute: int = 15
    log_level: str = "INFO"

    @field_validator("allowed_telegram_user_ids")
    @classmethod
    def _must_have_at_least_one_owner(cls, v: str) -> str:
        ids = [x.strip() for x in v.split(",") if x.strip()]
        if not ids:
            raise ValueError(
                "ALLOWED_TELEGRAM_USER_IDS is empty. Refusing to start: without it, "
                "ANYONE who finds your bot on Telegram could read/write your finances."
            )
        for x in ids:
            if not x.lstrip("-").isdigit():
                raise ValueError(f"ALLOWED_TELEGRAM_USER_IDS contains a non-numeric id: {x!r}")
        return v

    @field_validator("monthly_budget", mode="before")
    @classmethod
    def _blank_budget_is_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("monthly_budget")
    @classmethod
    def _budget_must_be_positive(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("MONTHLY_BUDGET must be a positive number if set.")
        return v

    @property
    def allowed_user_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.allowed_telegram_user_ids.split(",") if x.strip()}

    @property
    def tracked_currency_list(self) -> list[str]:
        return [c.strip().upper() for c in self.tracked_currencies.split(",") if c.strip()]

    def ensure_secret_dirs_exist(self) -> None:
        for path_str in (self.google_oauth_client_file, self.google_token_file):
            Path(path_str).parent.mkdir(parents=True, exist_ok=True)


settings = Settings()  # type: ignore[call-arg]  # populated from .env / real env vars
