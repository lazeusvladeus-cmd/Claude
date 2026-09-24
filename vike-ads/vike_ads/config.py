"""Runtime settings, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

PACKAGE_ROOT = Path(__file__).resolve().parent.parent  # .../vike-ads


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw else default


@dataclass
class Settings:
    # Reasoning / copy
    openai_api_key: str = ""
    openai_model: str = "gpt-5"
    openai_base_url: str = "https://api.openai.com/v1"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    # Images
    gemini_api_key: str = ""
    gemini_image_model: str = "gemini-3-pro-image-preview"
    google_image_backend: str = "aistudio"  # "aistudio" or "vertex"
    vertex_project: str = ""
    vertex_location: str = "global"
    fal_key: str = ""
    fal_model: str = "fal-ai/nano-banana-pro"
    image_qa: bool = True
    image_max_attempts: int = 2

    # Research sources
    google_cse_api_key: str = ""
    google_cse_id: str = ""
    meta_ad_library_token: str = ""
    meta_ad_library_countries: list[str] = field(default_factory=lambda: ["IE", "NL"])
    fetch_pages: bool = True

    # Behaviour
    use_deepseek: bool = True

    # Scheduling
    weekly_research_day: str = "mon"
    weekly_research_hour: int = 8
    weekly_research_topic: str = ""
    timezone: str = "Europe/Kyiv"

    # Paths
    data_dir: Path = PACKAGE_ROOT / "data"
    brand_file: Path = PACKAGE_ROOT / "config" / "brand.json"
    references_dir: Path = PACKAGE_ROOT / "references"

    # Web dashboard
    web_host: str = "127.0.0.1"
    web_port: int = 8765

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        if load_dotenv is not None:
            load_dotenv(env_file or PACKAGE_ROOT / ".env", override=False)
        countries = [c.strip().upper() for c in _env("META_AD_LIBRARY_COUNTRIES", "IE,NL").split(",") if c.strip()]
        return cls(
            openai_api_key=_env("OPENAI_API_KEY"),
            openai_model=_env("OPENAI_MODEL", cls.openai_model),
            openai_base_url=_env("OPENAI_BASE_URL", cls.openai_base_url),
            deepseek_api_key=_env("DEEPSEEK_API_KEY"),
            deepseek_model=_env("DEEPSEEK_MODEL", cls.deepseek_model),
            deepseek_base_url=_env("DEEPSEEK_BASE_URL", cls.deepseek_base_url),
            gemini_api_key=_env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY"),
            gemini_image_model=_env("GEMINI_IMAGE_MODEL", cls.gemini_image_model),
            google_image_backend=_env("GOOGLE_IMAGE_BACKEND", cls.google_image_backend).lower(),
            vertex_project=_env("VERTEX_PROJECT"),
            vertex_location=_env("VERTEX_LOCATION", cls.vertex_location),
            fal_key=_env("FAL_KEY"),
            fal_model=_env("FAL_MODEL", cls.fal_model),
            image_qa=_env_bool("IMAGE_QA", True),
            image_max_attempts=max(1, _env_int("IMAGE_MAX_ATTEMPTS", 2)),
            google_cse_api_key=_env("GOOGLE_CSE_API_KEY"),
            google_cse_id=_env("GOOGLE_CSE_ID"),
            meta_ad_library_token=_env("META_AD_LIBRARY_TOKEN"),
            meta_ad_library_countries=countries or ["IE", "NL"],
            fetch_pages=_env_bool("FETCH_PAGES", True),
            use_deepseek=_env_bool("USE_DEEPSEEK", True),
            weekly_research_day=_env("WEEKLY_RESEARCH_DAY", cls.weekly_research_day).lower(),
            weekly_research_hour=_env_int("WEEKLY_RESEARCH_HOUR", cls.weekly_research_hour),
            weekly_research_topic=_env("WEEKLY_RESEARCH_TOPIC"),
            timezone=_env("TIMEZONE", cls.timezone),
            data_dir=Path(_env("VIKE_DATA_DIR") or cls.data_dir),
            brand_file=Path(_env("VIKE_BRAND_FILE") or cls.brand_file),
            references_dir=Path(_env("VIKE_REFERENCES_DIR") or cls.references_dir),
            web_host=_env("WEB_HOST", cls.web_host),
            web_port=_env_int("WEB_PORT", cls.web_port),
        )

    def status(self) -> dict[str, bool]:
        """Which integrations are configured (never exposes key values)."""
        return {
            "openai": bool(self.openai_api_key),
            "deepseek": bool(self.deepseek_api_key) and self.use_deepseek,
            "gemini (primary images)": bool(self.gemini_api_key)
            or (self.google_image_backend == "vertex" and bool(self.vertex_project)),
            "fal.ai (secondary images)": bool(self.fal_key),
            "google custom search": bool(self.google_cse_api_key and self.google_cse_id),
            "meta ad library api": bool(self.meta_ad_library_token),
        }
