"""The one-page prep sheet as PNG / PDF (A4 portrait, one page per instrument).

Rendered with matplotlib so it works offline, needs no browser, and supports Cyrillic
text in your notes (DejaVu Sans font, bundled with matplotlib).
"""
from __future__ import annotations

import io
import textwrap
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import StrMethodFormatter

from desk.charts import resample_bars, rth_spans, spread_labels, visible_range
from desk.config import Sessions
from desk.levels import PrepResult
from desk.theme import FAMILY, FAMILY_NAMES, LIGHT, LINE_STYLE, level_color
from desk.timeutil import Clocks

# parse_math off: a "$" in your notes must print as "$", not switch to formula mode
matplotlib.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42, "axes.unicode_minus": False, "text.parse_math": False})

A4 = (8.27, 11.69)
C = LIGHT  # paper is white
BLANK = "______________________________"


@dataclass
class SheetPage:
    prep: PrepResult
    window: pd.DataFrame  # bars for the chart
    events: pd.DataFrame  # econ_calendar.EVENT_COLUMNS
    checklist: dict
    contract_label: str
    rollover: str | None = None


def _wrap(text: str, width: int) -> list[str]:
    lines = []
    for para in str(text).splitlines() or [""]:
        lines += textwrap.wrap(para, width) or [""]
    return lines


class _Column:
    """Writes wrapped text top-down inside a box and stops cleanly when the box is full."""

    def __init__(self, fig: Figure, x: float, top: float, bottom: float, width_chars: int, size: float = 7.0):
        self.fig, self.x, self.y, self.bottom = fig, x, top, bottom
        self.width, self.size = width_chars, size
        self.step = size * 1.35 / 72 / fig.get_figheight()
        self.full = False

    def line(self, text: str, bold: bool = False, color: str = C["ink"], size: float | None = None, indent: int = 0):
        if self.full:
            return
        if self.y - self.step < self.bottom:
            self.fig.text(self.x, self.y, "…", fontsize=self.size, color=C["muted"], va="top")
            self.full = True
            return
        self.fig.text(self.x + indent * 0.012, self.y, text, fontsize=size or self.size, color=color,
                      fontweight="bold" if bold else "normal", va="top")
        self.y -= self.step * ((size or self.size) / self.size)

    def para(self, text: str, color: str = C["ink"], indent: int = 0, prefix: str = ""):
        for i, chunk in enumerate(_wrap(text, self.width - indent * 2)):
            self.line((prefix if i == 0 else " " * len(prefix)) + chunk, color=color, indent=indent)

    def field(self, label: str, value) -> None:
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(v) for v in value if str(v).strip())
        value = str(value or "").strip()
        self.line(label, bold=True, color=C["ink2"])
        self.para(value if value else BLANK, color=C["ink"] if value else C["muted"], indent=1)

    def gap(self, factor: float = 0.5):
        self.y -= self.step * factor


def _levels_ladder(fig: Figure, page: SheetPage, box: tuple[float, float, float, float]) -> None:
    x, y, w, h = box
    prep = page.prep
    fig.text(x, y + h, "Key levels (price ladder)", fontsize=9.5, fontweight="bold", va="bottom", color=C["ink"])
    rows = sorted(prep.levels, key=lambda lv: -lv.price)
    entries: list[tuple] = []
    inserted = False
    for lv in rows:
        if not inserted and prep.last_price is not None and lv.price < prep.last_price:
            entries.append(("last", None))
            inserted = True
        entries.append(("level", lv))
    if not inserted and prep.last_price is not None:
        entries.append(("last", None))
    if not entries:
        fig.text(x, y + h - 0.02, "No levels - see warnings in the app.", fontsize=8, color=C["muted"], va="top")
        return
    row_h = min(h / max(len(entries), 1), 0.017)
    size = 7.4 if row_h >= 0.013 else 6.4
    top = y + h - 0.006
    fig.text(x + w * 0.80, top + 0.001, "price", fontsize=6.3, color=C["muted"], ha="right", va="bottom")
    fig.text(x + w, top + 0.001, "vs last", fontsize=6.3, color=C["muted"], ha="right", va="bottom")
    for i, (kind, lv) in enumerate(entries):
        cy = top - (i + 0.5) * row_h
        if kind == "last":
            fig.add_artist(Rectangle((x, cy - row_h / 2), w, row_h, transform=fig.transFigure,
                                         facecolor="#eeeeea", edgecolor="none", zorder=0))
            when = prep.last_bar_time.strftime("%H:%M") if prep.last_bar_time is not None else ""
            fig.text(x + 0.004, cy, f"▶ Last price ({when} NY)", fontsize=size, fontweight="bold", va="center", color=C["ink"])
            fig.text(x + w * 0.80, cy, f"{prep.last_price:,.2f}", fontsize=size, fontweight="bold", ha="right", va="center")
            continue
        color = level_color(lv.group, C)
        _, mpl_style, width = LINE_STYLE.get(lv.key, ("solid", "-", 1.5))
        fig.add_artist(Line2D([x, x + w * 0.05], [cy, cy], transform=fig.transFigure, color=color,
                                linestyle=mpl_style, linewidth=width))
        fig.text(x + w * 0.065, cy, lv.key, fontsize=size, fontweight="bold", va="center", color=C["ink"])
        label = lv.label + (" (naked)" if lv.key == "POC" and lv.note.startswith("naked") else "")
        fig.text(x + w * 0.205, cy, textwrap.shorten(label, 31, placeholder="…"), fontsize=size - 0.6, va="center", color=C["ink2"])
        fig.text(x + w * 0.80, cy, f"{lv.price:,.2f}", fontsize=size, ha="right", va="center", color=C["ink"])
        if prep.last_price is not None:
            fig.text(x + w, cy, f"{lv.price - prep.last_price:+,.2f}", fontsize=size - 0.6, ha="right", va="center", color=C["ink2"])


def _chart(fig: Figure, page: SheetPage, clocks: Clocks, sessions: Sessions, bar_minutes: int, box) -> None:
    x, y, w, h = box
    prep = page.prep
    bars = resample_bars(page.window, max(bar_minutes, 15))
    ax = fig.add_axes((x, y, w * 0.82, h))
    pax = fig.add_axes((x + w * 0.82, y, w * 0.11, h), sharey=ax)
    for a in (ax, pax):
        a.set_facecolor(C["surface"])
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            a.spines[side].set_color(C["axis"])
        a.tick_params(colors=C["ink2"], labelsize=6)
    pax.spines["left"].set_visible(False)
    pax.tick_params(left=False, labelleft=False, bottom=False, labelbottom=False)
    if bars.empty:
        ax.text(0.5, 0.5, "No price data", ha="center", transform=ax.transAxes, color=C["muted"])
        return

    xs = np.arange(len(bars))
    up = (bars["Close"] >= bars["Open"]).to_numpy()
    ax.vlines(xs, bars["Low"], bars["High"], color=C["ink2"], linewidth=0.5, zorder=2)
    body_low = np.minimum(bars["Open"], bars["Close"]).to_numpy()
    body_h = np.maximum(np.abs(bars["Close"] - bars["Open"]).to_numpy(), prep.instrument.tick_size * 0.5)
    ax.bar(xs[up], body_h[up], bottom=body_low[up], width=0.7, color=C["surface"], edgecolor=C["ink2"], linewidth=0.4, zorder=3)
    ax.bar(xs[~up], body_h[~up], bottom=body_low[~up], width=0.7, color=C["ink2"], edgecolor=C["ink2"], linewidth=0.4, zorder=3)
    for start, end in rth_spans(bars.index, sessions):
        ax.axvspan(start - 0.5, end + 0.5, color="#898781", alpha=0.10, linewidth=0, zorder=0)
        ax.text(start, 1.0, f"{bars.index[start]:%a %d %b}\nopen {clocks.dual(bars.index[start])}",
                transform=ax.get_xaxis_transform(), fontsize=5.6, color=C["ink2"], va="bottom")
    ax.set_xlim(-1, len(bars))
    ax.set_xticks([])
    ax.grid(axis="y", color=C["grid"], linewidth=0.5)
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))

    ymin, ymax, far = visible_range(bars, prep.levels)
    ax.set_ylim(ymin, ymax)
    near = [lv for lv in prep.levels if lv not in far]
    label_y = spread_labels([lv.price for lv in near], (ymax - ymin) * 0.045, ymin, ymax)
    to_fig = ax.transData + fig.transFigure.inverted()
    for lv, ly in zip(near, label_y):
        color = level_color(lv.group, C)
        _, mpl_style, width = LINE_STYLE.get(lv.key, ("solid", "-", 1.5))
        for a in (ax, pax):
            a.axhline(lv.price, color=color, linestyle=mpl_style, linewidth=width * 0.8, zorder=4)
        fy = to_fig.transform((0, ly))[1]
        fig.text(x + w * 0.935, fy, f"{lv.key} {lv.price:,.2f}", fontsize=6.2, va="center", color=C["ink"],
                 bbox=dict(boxstyle="square,pad=0.15", facecolor=C["surface"], edgecolor=color, linewidth=0.9))
    above = [lv for lv in far if lv.price > ymax]
    below = [lv for lv in far if lv.price < ymin]
    if above:
        ax.text(0.01, 0.985, "▲ off chart: " + " · ".join(f"{lv.key} {lv.price:,.2f}" for lv in above),
                transform=ax.transAxes, fontsize=5.8, color=C["muted"], va="top")
    if below:
        ax.text(0.01, 0.015, "▼ off chart: " + " · ".join(f"{lv.key} {lv.price:,.2f}" for lv in below),
                transform=ax.transAxes, fontsize=5.8, color=C["muted"], va="bottom")

    profile = prep.prior_profile
    if profile is not None:
        rows = profile.bucketed(60)
        colors = np.where(rows["is_poc"], C["profile_poc"], np.where(rows["in_value"], C["profile_in"], C["profile_out"]))
        pax.barh(rows["mid"], rows["volume"], height=(rows["high"] - rows["low"] + profile.tick) * 0.9, color=colors, linewidth=0)
        pax.set_title("prior day\nprofile", fontsize=5.6, color=C["muted"])

    families = list(dict.fromkeys(FAMILY.get(lv.group, "value") for lv in prep.levels))
    handles = [Line2D([], [], color=C[f], linewidth=1.6, label=FAMILY_NAMES[f]) for f in families]
    if handles:
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.01), ncol=3, fontsize=5.8, frameon=False)


def render_page(fig: Figure, page: SheetPage, clocks: Clocks, sessions: Sessions, generated_at: pd.Timestamp, bar_minutes: int) -> None:
    prep = page.prep
    inst = prep.instrument
    rth_open = clocks.market_ts(prep.target_date, sessions.rth_start)
    left, right = 0.05, 0.95

    fig.text(left, 0.968, f"{inst.key} pre-session prep · {prep.target_date:%A %d %B %Y}", fontsize=15, fontweight="bold", color=C["ink"])
    fig.text(left, 0.952,
             f"{inst.name} · {page.contract_label} · RTH opens {clocks.dual(rth_open)} · "
             f"generated {clocks.dual(generated_at, '%d %b %H:%M')}", fontsize=7.6, color=C["ink2"])
    fig.text(left, 0.940,
             "Prices: Yahoo Finance (free, delayed, approximate) - confirm every level on your ATAS chart. "
             "Overnight = Globex since the prior close.", fontsize=6.4, color=C["muted"])
    top = 0.925
    if page.rollover:
        fig.text(left, top, "⚠ " + textwrap.shorten(page.rollover, 200, placeholder="…"), fontsize=6.4, color="#8a5a00")
        top -= 0.014

    _levels_ladder(fig, page, (left, 0.605, 0.43, top - 0.62))

    col = _Column(fig, 0.53, top, 0.605, 60, size=7.0)
    col.line("Gap & context", bold=True, size=9.5)
    col.gap(0.3)
    if prep.gap:
        kind = "Opening gap" if prep.gap.kind == "opening" else "Pre-open gap (last price)"
        col.para(f"{kind} vs prior close {prep.gap.reference:,.2f}: {prep.gap.points:+,.2f} pts ({prep.gap.percent:+.2f}%)")
    if prep.prior_range is not None:
        col.para(f"Prior RTH range: {prep.prior_range:,.2f} pts"
                 + (f" · overnight range: {prep.overnight_range:,.2f} pts" if prep.overnight_range is not None else ""))
    for note in prep.context:
        col.para(note, prefix="• ")
    for warning in prep.warnings:
        col.para(warning, color="#8a5a00", prefix="⚠ ")
    col.gap(0.6)
    col.line("Economic events today (US, high impact)", bold=True, size=9.5)
    col.gap(0.3)
    if page.events is None or page.events.empty:
        col.para("None found. Check the Fed / BLS / BEA calendars before trading.", color=C["muted"])
    else:
        for _, ev in page.events.iterrows():
            when = "all day" if ev["all_day"] else clocks.dual(ev["time"])
            col.para(f"{when}  {ev['events']}  [{ev['impact']}]")

    _chart(fig, page, clocks, sessions, bar_minutes, (left, 0.315, right - left, 0.255))

    c = page.checklist or {}
    fig.add_artist(Line2D([left, right], [0.265, 0.265], transform=fig.transFigure, color=C["axis"], linewidth=0.6))
    fig.text(left, 0.257, "Context → Location → Confirmation", fontsize=10, fontweight="bold", va="top", color=C["ink"])
    col_w = (right - left) / 3
    ctx = _Column(fig, left, 0.237, 0.02, 42, size=6.6)
    ctx.line("1 · CONTEXT", bold=True, size=7.6)
    ctx.field("Market state", c.get("market_state"))
    ctx.field("Open vs yesterday", c.get("open_location"))
    ctx.field("Higher-timeframe context", c.get("htf_context"))
    ctx.field("News / event risk", c.get("news_risk"))
    ctx.field("Scenarios (plan A / plan B)", c.get("scenarios"))
    loc = _Column(fig, left + col_w, 0.237, 0.02, 42, size=6.6)
    loc.line("2 · LOCATION", bold=True, size=7.6)
    loc.field("Key locations", c.get("key_locations"))
    loc.field("Extra levels (options / ATAS)", c.get("extra_levels"))
    loc.field("What I do at each location", c.get("location_plan"))
    con = _Column(fig, left + 2 * col_w, 0.237, 0.02, 42, size=6.6)
    con.line("3 · CONFIRMATION (ATAS)", bold=True, size=7.6)
    signals = c.get("confirmations") or []
    con.line("Signals I need to see", bold=True, color=C["ink2"])
    if signals:
        for s in signals:
            con.para(s, prefix="✓ ", indent=1)
    else:
        con.para(BLANK, color=C["muted"], indent=1)
    con.field("Entry trigger / stop / invalidation", c.get("trigger_invalidation"))
    risk = (f"max daily loss ${c.get('max_daily_loss_usd', 0):,.0f} · max {c.get('max_trades', 0)} trades · "
            f"${c.get('risk_per_trade_usd', 0):,.0f} per trade") if c else ""
    con.field("Risk", risk)


def _new_figure() -> Figure:
    fig = Figure(figsize=A4, facecolor=C["surface"])
    FigureCanvasAgg(fig)
    return fig


def sheet_png(page: SheetPage, clocks: Clocks, sessions: Sessions, generated_at: pd.Timestamp, bar_minutes: int, dpi: int = 150) -> bytes:
    fig = _new_figure()
    render_page(fig, page, clocks, sessions, generated_at, bar_minutes)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=C["surface"])
    return buf.getvalue()


def sheet_pdf(pages: list[SheetPage], clocks: Clocks, sessions: Sessions, generated_at: pd.Timestamp, bar_minutes: int) -> bytes:
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        for page in pages:
            fig = _new_figure()
            render_page(fig, page, clocks, sessions, generated_at, bar_minutes)
            pdf.savefig(fig, facecolor=C["surface"])
    return buf.getvalue()
