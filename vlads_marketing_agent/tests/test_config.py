"""Тести завантаження та валідації конфігурації (src/config.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import load_settings
from src.exceptions import AgentConfigError

_VALID_YAML = """
searches:
  - category: "кав'ярні"
    location: "Львів"
max_new_leads_per_run: 10
max_results_per_search: 10
min_reviews_count: 5
"""


def _write_env(tmp_path: Path, content: str) -> Path:
    env_path = tmp_path / ".env"
    env_path.write_text(content, encoding="utf-8")
    return env_path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Гарантує чистий os.environ для кожного тесту (load_dotenv не перезаписує існуючі змінні)."""
    for var in ("GOOGLE_PLACES_API_KEY", "ANTHROPIC_API_KEY", "LEADS_CONFIG_PATH"):
        monkeypatch.delenv(var, raising=False)


class TestLoadSettings:
    def test_loads_valid_config(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "leads_config.yaml").write_text(_VALID_YAML, encoding="utf-8")
        env_path = _write_env(
            tmp_path,
            "GOOGLE_PLACES_API_KEY=fake-places-key\nANTHROPIC_API_KEY=sk-ant-fake-key-123\n",
        )

        settings = load_settings(env_file=env_path)

        assert settings.google_places_api_key == "fake-places-key"
        assert settings.anthropic_api_key == "sk-ant-fake-key-123"
        assert len(settings.leads_config.searches) == 1
        assert settings.leads_config.max_new_leads_per_run == 10

    def test_missing_required_env_var_raises_clear_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        (tmp_path / "leads_config.yaml").write_text(_VALID_YAML, encoding="utf-8")
        env_path = _write_env(tmp_path, "GOOGLE_PLACES_API_KEY=\nANTHROPIC_API_KEY=\n")

        with pytest.raises(AgentConfigError, match="GOOGLE_PLACES_API_KEY"):
            load_settings(env_file=env_path)

    def test_require_secrets_false_skips_env_check(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        (tmp_path / "leads_config.yaml").write_text(_VALID_YAML, encoding="utf-8")
        env_path = _write_env(tmp_path, "GOOGLE_PLACES_API_KEY=\nANTHROPIC_API_KEY=\n")

        settings = load_settings(env_file=env_path, require_secrets=False)
        assert settings.google_places_api_key == ""

    def test_missing_leads_config_file_raises_clear_error(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        env_path = _write_env(
            tmp_path,
            "GOOGLE_PLACES_API_KEY=x\nANTHROPIC_API_KEY=sk-ant-x\nLEADS_CONFIG_PATH=does_not_exist.yaml\n",
        )

        with pytest.raises(AgentConfigError, match="не знайдено"):
            load_settings(env_file=env_path)

    def test_invalid_yaml_syntax_raises_clear_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "leads_config.yaml").write_text(
            "searches: [\n  broken: yaml: :", encoding="utf-8"
        )
        env_path = _write_env(tmp_path, "GOOGLE_PLACES_API_KEY=x\nANTHROPIC_API_KEY=sk-ant-x\n")

        with pytest.raises(AgentConfigError, match="YAML"):
            load_settings(env_file=env_path)

    def test_yaml_missing_searches_raises_clear_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "leads_config.yaml").write_text("max_new_leads_per_run: 5\n", encoding="utf-8")
        env_path = _write_env(tmp_path, "GOOGLE_PLACES_API_KEY=x\nANTHROPIC_API_KEY=sk-ant-x\n")

        with pytest.raises(AgentConfigError, match="searches"):
            load_settings(env_file=env_path)

    def test_yaml_search_entry_missing_location_raises_clear_error(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "leads_config.yaml").write_text(
            'searches:\n  - category: "кав\'ярні"\n', encoding="utf-8"
        )
        env_path = _write_env(tmp_path, "GOOGLE_PLACES_API_KEY=x\nANTHROPIC_API_KEY=sk-ant-x\n")

        with pytest.raises(AgentConfigError):
            load_settings(env_file=env_path)

    def test_yaml_negative_limit_raises_clear_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "leads_config.yaml").write_text(
            'searches:\n  - category: "кав\'ярні"\n    location: "Львів"\n'
            "max_new_leads_per_run: -5\n",
            encoding="utf-8",
        )
        env_path = _write_env(tmp_path, "GOOGLE_PLACES_API_KEY=x\nANTHROPIC_API_KEY=sk-ant-x\n")

        with pytest.raises(AgentConfigError, match=">"):
            load_settings(env_file=env_path)

    def test_yaml_not_a_mapping_raises_clear_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "leads_config.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
        env_path = _write_env(tmp_path, "GOOGLE_PLACES_API_KEY=x\nANTHROPIC_API_KEY=sk-ant-x\n")

        with pytest.raises(AgentConfigError, match="словником"):
            load_settings(env_file=env_path)
