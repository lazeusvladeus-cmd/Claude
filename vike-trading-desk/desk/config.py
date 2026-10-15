"""Load config.toml into typed settings, with error messages a non-coder can act on."""
from __future__ import annotations

import datetime as dt
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from desk.timeutil import get_zone, parse_hhmm


class ConfigError(Exception):
    """A problem in config.toml, phrased so the user knows what to fix."""


@dataclass(frozen=True)
class You:
    name: str
    home_tz: str
    home_label: str
    market_tz: str
    market_label: str
    shift_start: dt.time
    shift_end: dt.time


@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    yahoo_symbol: str
    cme_root: str
    tick_size: float
    point_value_usd: float
    enabled: bool


@dataclass(frozen=True)
class Sessions:
    rth_start: dt.time
    rth_end: dt.time
    globex_start: dt.time
    overnight_start: dt.time


@dataclass(frozen=True)
class LevelSettings:
    prior_day_high_low_close: bool
    prior_day_vwap: bool
    overnight_high_low: bool
    value_area: bool
    weekly_high_low: bool
    naked_pocs: bool
    gap: bool
    value_area_percent: float
    naked_poc_lookback_days: int
    naked_poc_max_shown: int


@dataclass(frozen=True)
class ChartSettings:
    sessions_to_show: int
    bar_minutes: int
    show_volume_profile: bool


@dataclass(frozen=True)
class CalendarSettings:
    use_free_online_feed: bool
    countries: tuple[str, ...]
    impact_levels: tuple[str, ...]
    refresh_every_hours: float


@dataclass(frozen=True)
class RiskSettings:
    max_daily_loss_usd: float
    max_trades_per_day: int
    risk_per_trade_usd: float


@dataclass(frozen=True)
class ResearchSettings:
    sec_user_agent: str
    discount_rate: float
    terminal_growth: float
    bank_cost_of_equity: float


@dataclass(frozen=True)
class Config:
    app_dir: Path
    you: You
    instruments: tuple[Instrument, ...]
    sessions: Sessions
    levels: LevelSettings
    chart: ChartSettings
    calendar: CalendarSettings
    risk: RiskSettings
    journal_dir: Path
    coverage: dict[str, list[str]] = field(default_factory=dict)
    research: ResearchSettings = ResearchSettings("", 9.0, 2.5, 10.0)

    @property
    def enabled_instruments(self) -> list[Instrument]:
        return [i for i in self.instruments if i.enabled]

    @property
    def cache_dir(self) -> Path:
        return self.app_dir / "data" / "cache"

    @property
    def manual_events_csv(self) -> Path:
        return self.app_dir / "data" / "economic_events_manual.csv"


_TYPE_HINTS = {
    bool: "true or false (no quotes)",
    int: "a whole number without quotes, like 20",
    float: "a number without quotes, like 70",
    str: 'text in "double quotes"',
    list: 'a list in square brackets, like ["High", "Medium"]',
}


class _Section:
    """Reads one [section] of the TOML file and explains type mistakes."""

    def __init__(self, data: dict, name: str):
        raw = data.get(name, {})
        if not isinstance(raw, dict):
            raise ConfigError(f"[{name}] in config.toml should be a section header, not a value.")
        self.raw = raw
        self.name = name

    def get(self, key: str, default, kind: type):
        value = self.raw.get(key, default)
        ok = isinstance(value, kind)
        if kind is float and isinstance(value, int) and not isinstance(value, bool):
            ok = True
            value = float(value)
        if kind is int and isinstance(value, bool):
            ok = False
        if not ok:
            raise ConfigError(
                f'In [{self.name}], the setting "{key}" should be {_TYPE_HINTS[kind]}, '
                f"but it is: {value!r}"
            )
        return value

    def time(self, key: str, default: str) -> dt.time:
        text = self.get(key, default, str)
        try:
            return parse_hhmm(text)
        except ValueError:
            raise ConfigError(
                f'In [{self.name}], "{key}" should be a time like "09:30" (24-hour clock), but it is: {text!r}'
            ) from None

    def tz(self, key: str, default: str) -> str:
        text = self.get(key, default, str)
        try:
            get_zone(text)
        except Exception:
            raise ConfigError(
                f'In [{self.name}], "{key}" is not a known time zone: {text!r}. '
                'Examples: "Europe/Kyiv", "America/New_York".'
            ) from None
        return text

    def str_list(self, key: str, default: list[str]) -> list[str]:
        value = self.get(key, default, list)
        if not all(isinstance(v, str) for v in value):
            raise ConfigError(f'In [{self.name}], every item in "{key}" must be text in "double quotes".')
        return [v.strip() for v in value if v.strip()]


def ensure_user_config(app_dir: Path) -> Path:
    """Your settings live in config.toml; on first start it's copied from config.example.toml."""
    path = Path(app_dir) / "config.toml"
    template = Path(app_dir) / "config.example.toml"
    if not path.exists() and template.exists():
        shutil.copyfile(template, path)
    return path


def load_config(path: Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Settings file not found: {path}. It must sit next to app.py (copy config.example.toml to config.toml).")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"config.toml has a typo: {exc}. Common causes: missing \"quotes\" around text, "
            "a missing ] or \", or a Windows path with backslashes (use forward slashes /)."
        ) from None
    except UnicodeDecodeError:
        raise ConfigError("config.toml is not saved as UTF-8 text. In Notepad use File -> Save As -> Encoding: UTF-8.") from None

    app_dir = path.parent

    s = _Section(data, "you")
    you = You(
        name=s.get("name", "Trader", str),
        home_tz=s.tz("home_timezone", "Europe/Kyiv"),
        home_label=s.get("home_label", "Kyiv", str),
        market_tz=s.tz("market_timezone", "America/New_York"),
        market_label=s.get("market_label", "NY", str),
        shift_start=s.time("shift_start", "15:00"),
        shift_end=s.time("shift_end", "23:00"),
    )

    raw_instruments = data.get("instruments", {})
    if not isinstance(raw_instruments, dict) or not raw_instruments:
        raise ConfigError("config.toml needs at least one [instruments.XX] block (for example [instruments.NQ]).")
    instruments = []
    for key, raw in raw_instruments.items():
        s = _Section(raw_instruments, key)
        s.name = f"instruments.{key}"
        tick = s.get("tick_size", 0.25, float)
        point_value = s.get("point_value_usd", 20.0, float)
        if tick <= 0 or point_value <= 0:
            raise ConfigError(f"In [instruments.{key}], tick_size and point_value_usd must be above zero.")
        instruments.append(
            Instrument(
                key=key,
                name=s.get("name", key, str),
                yahoo_symbol=s.get("yahoo_symbol", f"{key}=F", str).strip(),
                cme_root=s.get("cme_root", key, str).strip(),
                tick_size=tick,
                point_value_usd=point_value,
                enabled=s.get("enabled", True, bool),
            )
        )
    if not any(i.enabled for i in instruments):
        raise ConfigError("All instruments are switched off. Set enabled = true for at least one of them.")

    s = _Section(data, "sessions")
    sessions = Sessions(
        rth_start=s.time("rth_start", "09:30"),
        rth_end=s.time("rth_end", "16:00"),
        globex_start=s.time("globex_start", "18:00"),
        overnight_start=s.time("overnight_start", "16:00"),
    )
    if sessions.rth_start >= sessions.rth_end:
        raise ConfigError("In [sessions], rth_start must be earlier than rth_end.")

    s = _Section(data, "levels")
    va_pct = s.get("value_area_percent", 70.0, float)
    if not 1 <= va_pct <= 99:
        raise ConfigError("In [levels], value_area_percent must be between 1 and 99 (the standard is 70).")
    levels = LevelSettings(
        prior_day_high_low_close=s.get("prior_day_high_low_close", True, bool),
        prior_day_vwap=s.get("prior_day_vwap", True, bool),
        overnight_high_low=s.get("overnight_high_low", True, bool),
        value_area=s.get("value_area", True, bool),
        weekly_high_low=s.get("weekly_high_low", True, bool),
        naked_pocs=s.get("naked_pocs", True, bool),
        gap=s.get("gap", True, bool),
        value_area_percent=va_pct,
        naked_poc_lookback_days=max(1, s.get("naked_poc_lookback_days", 20, int)),
        naked_poc_max_shown=max(0, s.get("naked_poc_max_shown", 5, int)),
    )

    s = _Section(data, "chart")
    bar_minutes = s.get("bar_minutes", 5, int)
    if bar_minutes not in (1, 2, 3, 5, 10, 15, 30, 60):
        raise ConfigError("In [chart], bar_minutes must be one of 1, 2, 3, 5, 10, 15, 30 or 60.")
    chart = ChartSettings(
        sessions_to_show=min(10, max(1, s.get("sessions_to_show", 3, int))),
        bar_minutes=bar_minutes,
        show_volume_profile=s.get("show_volume_profile", True, bool),
    )

    s = _Section(data, "economic_calendar")
    calendar = CalendarSettings(
        use_free_online_feed=s.get("use_free_online_feed", True, bool),
        countries=tuple(c.upper() for c in s.str_list("countries", ["USD"])),
        impact_levels=tuple(i.capitalize() for i in s.str_list("impact_levels", ["High"])),
        refresh_every_hours=max(1.0, s.get("refresh_every_hours", 4.0, float)),
    )

    s = _Section(data, "risk")
    risk = RiskSettings(
        max_daily_loss_usd=s.get("max_daily_loss_usd", 500.0, float),
        max_trades_per_day=s.get("max_trades_per_day", 3, int),
        risk_per_trade_usd=s.get("risk_per_trade_usd", 150.0, float),
    )

    s = _Section(data, "journal")
    folder = Path(s.get("folder", "journal", str).strip() or "journal").expanduser()
    journal_dir = folder if folder.is_absolute() else app_dir / folder

    s = _Section(data, "coverage")
    coverage = {key: [t.upper() for t in s.str_list(key, [])] for key in s.raw}

    s = _Section(data, "research")
    research = ResearchSettings(
        sec_user_agent=s.get("sec_user_agent", "", str).strip(),
        discount_rate=s.get("default_discount_rate", 9.0, float),
        terminal_growth=s.get("default_terminal_growth", 2.5, float),
        bank_cost_of_equity=s.get("bank_cost_of_equity", 10.0, float),
    )

    return Config(
        app_dir=app_dir,
        you=you,
        instruments=tuple(instruments),
        sessions=sessions,
        levels=levels,
        chart=chart,
        calendar=calendar,
        risk=risk,
        journal_dir=journal_dir,
        coverage=coverage,
        research=research,
    )
