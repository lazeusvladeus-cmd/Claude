"""Sets required env vars before any `app.*` module is imported (app.config.settings
is instantiated at import time), so tests never touch real credentials or the network."""
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-token-aaaaaaaaaaaaaaaaaaaaaaaaaaa")
os.environ.setdefault("ALLOWED_TELEGRAM_USER_IDS", "111,222")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
os.environ.setdefault("GOOGLE_SHEET_ID", "fake_sheet_id")
os.environ.setdefault("BASE_CURRENCY", "USD")
os.environ.setdefault("TRACKED_CURRENCIES", "USD,UAH")
