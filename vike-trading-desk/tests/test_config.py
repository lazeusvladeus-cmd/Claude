from pathlib import Path

import pytest

from desk.config import ConfigError, ensure_user_config, load_config

APP_DIR = Path(__file__).resolve().parents[1]


def test_shipped_config_loads():
    cfg = load_config(APP_DIR / "config.example.toml")
    assert [i.key for i in cfg.enabled_instruments] == ["NQ", "ES"]
    nq = cfg.enabled_instruments[0]
    assert nq.yahoo_symbol == "NQ=F" and nq.tick_size == 0.25 and nq.point_value_usd == 20
    assert cfg.journal_dir == APP_DIR / "journal"
    assert cfg.coverage == {"quality": ["MSFT"], "banks": ["JPM"], "ad_driven": ["META"]}
    assert cfg.calendar.impact_levels == ("High",)
    assert cfg.sessions.rth_start.strftime("%H:%M") == "09:30"


def write(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_typo_is_explained(tmp_path):
    path = write(tmp_path, '[you]\nname = "Vike\n[instruments.NQ]\nyahoo_symbol = "NQ=F"\n')
    with pytest.raises(ConfigError, match="typo"):
        load_config(path)


def test_wrong_type_names_the_setting(tmp_path):
    path = write(tmp_path, '[instruments.NQ]\nyahoo_symbol = "NQ=F"\n[levels]\nvalue_area_percent = "70%"\n')
    with pytest.raises(ConfigError, match="value_area_percent"):
        load_config(path)


def test_bad_time_and_timezone(tmp_path):
    with pytest.raises(ConfigError, match="09:30"):
        load_config(write(tmp_path, '[instruments.NQ]\n[sessions]\nrth_start = "9.30"\n'))
    with pytest.raises(ConfigError, match="time zone"):
        load_config(write(tmp_path, '[instruments.NQ]\n[you]\nhome_timezone = "Kyiv"\n'))


def test_absolute_journal_folder(tmp_path):
    folder = (tmp_path / "MyJournal").as_posix()
    cfg = load_config(write(tmp_path, f'[instruments.NQ]\n[journal]\nfolder = "{folder}"\n'))
    assert cfg.journal_dir == Path(folder)


def test_user_config_created_from_template_once(tmp_path):
    (tmp_path / "config.example.toml").write_text('[instruments.NQ]\n[you]\nname = "Template"\n', encoding="utf-8")
    path = ensure_user_config(tmp_path)
    assert load_config(path).you.name == "Template"
    path.write_text('[instruments.NQ]\n[you]\nname = "Mine"\n', encoding="utf-8")
    ensure_user_config(tmp_path)  # must never overwrite your edits
    assert load_config(path).you.name == "Mine"
