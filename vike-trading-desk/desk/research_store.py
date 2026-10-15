"""Your research per company: thesis notes, KPI tracker rows, manual inputs and saved valuation assumptions.

Stored as data/research/<TICKER>.json (private, never uploaded to GitHub).
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd

AD_KPI_METRICS = [
    "Ad revenue ($ millions)",
    "Daily active users / people (millions)",
    "ARPU / ARPP ($)",
    "Ad impressions growth (% YoY)",
    "Average price per ad growth (% YoY)",
    "Other",
]
KPI_COLUMNS = ["period", "metric", "value", "source"]


def _path(root: Path, ticker: str) -> Path:
    return Path(root) / f"{ticker.upper()}.json"


def load(root: Path, ticker: str) -> dict:
    data = {"notes": {}, "dcf": {}, "bank": {}, "manual": {}, "kpis": [], "saved_at": None}
    path = _path(root, ticker)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, ValueError):
            path.replace(path.with_name(f"{path.stem}.unreadable-{dt.datetime.now():%Y%m%d-%H%M%S}.json"))
    return data


def save(root: Path, ticker: str, updates: dict) -> dict:
    data = load(root, ticker)
    data.update(updates)
    data["saved_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    path = _path(root, ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)
    return data


def kpi_frame(data: dict) -> pd.DataFrame:
    df = pd.DataFrame(data.get("kpis", []), columns=KPI_COLUMNS)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def kpi_rows(df: pd.DataFrame) -> list[dict]:
    clean = df.reindex(columns=KPI_COLUMNS).copy()
    clean = clean[clean["period"].astype(str).str.strip().ne("") & clean["period"].notna() & clean["metric"].notna()]
    clean["value"] = pd.to_numeric(clean["value"], errors="coerce")
    clean = clean.dropna(subset=["value"])
    return [{k: (None if pd.isna(v) else v) for k, v in row.items()} for row in clean.to_dict("records")]
