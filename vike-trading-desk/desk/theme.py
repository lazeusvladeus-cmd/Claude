"""Colors for charts and the printed sheet (validated for colorblind-safety in light and dark).

Three level families, each with its own color; candles stay neutral so the levels stand out.
Identity never relies on color alone: every level line carries a text label, and the
levels table repeats every value.
"""
from __future__ import annotations

LIGHT = {
    "surface": "#ffffff",
    "ink": "#0b0b0b",
    "ink2": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "rth_shade": "rgba(137,135,129,0.10)",
    "value": "#2a78d6",  # volume-profile levels (VAH / POC / VAL / naked POCs)
    "prior": "#eb6834",  # prior day high / low / close / VWAP
    "overnight": "#1baf7a",  # overnight and weekly extremes
    "profile_out": "#86b6ef",
    "profile_in": "#3987e5",
    "profile_poc": "#184f95",
}

DARK = {
    "surface": "#0e1117",
    "ink": "#f0efec",
    "ink2": "#c3c2b7",
    "muted": "#898781",
    "grid": "#2c2c2a",
    "axis": "#383835",
    "rth_shade": "rgba(195,194,183,0.08)",
    "value": "#3987e5",
    "prior": "#d95926",
    "overnight": "#199e70",
    "profile_out": "#184f95",
    "profile_in": "#3987e5",
    "profile_poc": "#86b6ef",
}

FAMILY = {
    "value": "value",
    "naked_poc": "value",
    "prior_day": "prior",
    "vwap": "prior",
    "overnight": "overnight",
    "weekly": "overnight",
}
FAMILY_NAMES = {
    "value": "Volume profile (VAH / POC / VAL, naked POCs)",
    "prior": "Prior day (high / low / close / VWAP)",
    "overnight": "Overnight & weekly (high / low)",
}

# (plotly dash, matplotlib linestyle, width) per level tag
LINE_STYLE = {
    "POC": ("solid", "-", 2.5),
    "VAH": ("solid", "-", 1.5),
    "VAL": ("solid", "-", 1.5),
    "nPOC": ("dot", ":", 1.5),
    "PDH": ("solid", "-", 1.5),
    "PDL": ("solid", "-", 1.5),
    "PDC": ("dash", (0, (5, 3)), 1.5),
    "pVWAP": ("dashdot", "-.", 1.5),
    "ONH": ("solid", "-", 1.5),
    "ONL": ("solid", "-", 1.5),
    "WkH": ("dash", (0, (5, 3)), 1.5),
    "WkL": ("dash", (0, (5, 3)), 1.5),
    "PWH": ("longdash", (0, (9, 3)), 1.5),
    "PWL": ("longdash", (0, (9, 3)), 1.5),
}


def palette(dark: bool) -> dict:
    return DARK if dark else LIGHT


def level_color(group: str, colors: dict) -> str:
    return colors[FAMILY.get(group, "value")]
