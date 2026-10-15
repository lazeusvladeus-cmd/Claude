"""Runs the real Streamlit app headless with synthetic prices (no internet needed)."""
import dataclasses
import datetime as dt
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from synthetic import NY, random_walk_bars
from test_econ_calendar import FEED, FakeResponse

import desk.config
import desk.econ_calendar
import desk.ui_prep
from desk.market_data import load_bars

APP_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture()
def app(tmp_path, monkeypatch):
    real_cfg = desk.config.load_config(APP_DIR / "config.example.toml")
    cfg = dataclasses.replace(real_cfg, app_dir=tmp_path, journal_dir=tmp_path / "journal")
    monkeypatch.setattr(desk.config, "load_config", lambda path: cfg)
    monkeypatch.setattr(desk.config, "ensure_user_config", lambda app_dir: tmp_path / "config.toml")

    now = pd.Timestamp.now(tz=NY)
    start = (now - pd.Timedelta(days=20)).date()

    def fake_download(symbol, interval):
        minutes = 1 if interval == "1m" else 5
        bars = random_walk_bars(start, now.date(), minutes=minutes, base=25000 if symbol.startswith("NQ") else 6700)
        return bars[bars.index <= now]

    monkeypatch.setattr(desk.ui_prep, "load_bars", lambda symbol, cache_dir, tz: load_bars(symbol, cache_dir, tz, downloader=fake_download))
    real_get_events = desk.econ_calendar.get_events
    monkeypatch.setattr(desk.econ_calendar, "get_events",
                        lambda *a, **k: real_get_events(*a, **k, http_get=lambda url: FakeResponse(200, FEED)))
    desk.ui_prep._bars.clear()
    desk.ui_prep._events.clear()
    return AppTest.from_file(str(APP_DIR / "app.py"), default_timeout=120), cfg


def test_app_runs_and_saves_a_plan(app):
    at, cfg = app
    at.run()
    assert not at.exception, at.exception
    assert at.title[0].value.startswith("📈 Vike Trading Desk")
    assert any("Price ladder" in m.value for m in at.markdown)

    save = next(b for b in at.button if "Save plan" in b.label)
    save.click().run()
    assert not at.exception, at.exception
    day = at.date_input(key="prep_day").value
    folder = cfg.journal_dir / day.isoformat()
    assert (folder / "sheet.pdf").exists() and (folder / "sheet_NQ.png").exists() and (folder / "sheet_ES.png").exists()

    review = next(b for b in at.button if b.label.startswith("💾 Save review"))
    review.click().run()
    assert not at.exception, at.exception
    reviewed_day = at.date_input(key="review_day").value
    assert (cfg.journal_dir / reviewed_day.isoformat() / "prep.json").exists()


def test_config_typo_shows_friendly_error(monkeypatch):
    def broken(path):
        raise desk.config.ConfigError("config.toml has a typo: line 3")

    monkeypatch.setattr(desk.config, "load_config", broken)
    monkeypatch.setattr(desk.config, "ensure_user_config", lambda app_dir: app_dir / "config.toml")
    at = AppTest.from_file(str(APP_DIR / "app.py"), default_timeout=60).run()
    assert not at.exception
    assert "settings file needs a fix" in at.error[0].value


def test_learning_tab_checkbox_saves(app):
    at, cfg = app
    at.run()
    assert not at.exception, at.exception
    assert any("12-week plan" in h.value for h in at.subheader)
    box = next(c for c in at.checkbox if c.key and c.key.startswith("chk_link|T1|"))
    box.check().run()
    assert not at.exception, at.exception
    saved = (cfg.app_dir / "data" / "learning_progress.json").read_text(encoding="utf-8")
    assert "link|T1|" in saved
