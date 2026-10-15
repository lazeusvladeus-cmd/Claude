"""Interactive price chart (Plotly) with the prep levels and the prior day's volume profile."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from desk.config import Sessions
from desk.levels import Level
from desk.profile import VolumeProfile
from desk.theme import FAMILY, FAMILY_NAMES, LINE_STYLE, level_color
from desk.timeutil import Clocks


def resample_bars(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.resample(f"{minutes}min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    )
    return out.dropna(subset=["Open"])


def visible_range(bars: pd.DataFrame, levels: list[Level], stretch: float = 0.6, pad: float = 0.04):
    """Y-range that shows the candles plus nearby levels; far-away levels are listed as off-chart."""
    lo, hi = float(bars["Low"].min()), float(bars["High"].max())
    span = max(hi - lo, 1e-6)
    near = [lv for lv in levels if lo - stretch * span <= lv.price <= hi + stretch * span]
    far = [lv for lv in levels if lv not in near]
    ymin = min([lo] + [lv.price for lv in near])
    ymax = max([hi] + [lv.price for lv in near])
    margin = (ymax - ymin) * pad
    return ymin - margin, ymax + margin, far


def spread_labels(prices: list[float], min_gap: float, lo: float, hi: float) -> list[float]:
    """Nudge label positions apart so labels for nearby levels don't overlap."""
    if not prices:
        return []
    order = np.argsort(prices)
    ys = np.asarray(prices, float)[order]
    for i in range(1, len(ys)):
        ys[i] = max(ys[i], ys[i - 1] + min_gap)
    if ys[-1] > hi:
        ys[-1] = hi
        for i in range(len(ys) - 2, -1, -1):
            ys[i] = min(ys[i], ys[i + 1] - min_gap)
    out = np.empty_like(ys)
    out[order] = ys
    return out.tolist()


def session_ticks(index: pd.DatetimeIndex, sessions: Sessions, clocks: Clocks) -> tuple[list[int], list[str]]:
    """One tick at each RTH open, labelled on both clocks (the shading shows where RTH ends)."""
    vals, texts = [], []
    for start, _ in rth_spans(index, sessions):
        vals.append(start)
        texts.append(f"<b>{index[start]:%a %d %b}</b><br>{clocks.dual(index[start])}")
    return vals, texts


def rth_spans(index: pd.DatetimeIndex, sessions: Sessions) -> list[tuple[int, int]]:
    mod = index.hour * 60 + index.minute
    open_min = sessions.rth_start.hour * 60 + sessions.rth_start.minute
    close_min = sessions.rth_end.hour * 60 + sessions.rth_end.minute
    in_rth = np.asarray((mod >= open_min) & (mod < close_min))
    spans, start = [], None
    for i, flag in enumerate(in_rth):
        new_day = i > 0 and index[i].date() != index[i - 1].date()
        if flag and (start is None or new_day):
            if start is not None:
                spans.append((start, i - 1))
            start = i
        elif not flag and start is not None:
            spans.append((start, i - 1))
            start = None
    if start is not None:
        spans.append((start, len(in_rth) - 1))
    return spans


def build_chart(
    window: pd.DataFrame,
    levels: list[Level],
    profile: VolumeProfile | None,
    clocks: Clocks,
    sessions: Sessions,
    bar_minutes: int,
    colors: dict,
    show_profile: bool = True,
    height: int = 640,
) -> go.Figure:
    bars = resample_bars(window, bar_minutes)
    with_profile = show_profile and profile is not None
    fig = make_subplots(
        rows=1,
        cols=2 if with_profile else 1,
        shared_yaxes=True,
        column_widths=[0.85, 0.15] if with_profile else [1.0],
        horizontal_spacing=0.005,
    )
    if bars.empty:
        fig.add_annotation(text="No price data to draw", showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5)
        return fig

    x = np.arange(len(bars))
    hover = [
        f"{ts:%a %d %b} · {clocks.dual(ts)}<br>O {o:,.2f}  H {h:,.2f}<br>L {lo:,.2f}  C {c:,.2f}<br>Vol {v:,.0f}"
        for ts, o, h, lo, c, v in zip(bars.index, bars["Open"], bars["High"], bars["Low"], bars["Close"], bars["Volume"])
    ]
    fig.add_trace(
        go.Candlestick(
            x=x,
            open=bars["Open"],
            high=bars["High"],
            low=bars["Low"],
            close=bars["Close"],
            increasing=dict(line=dict(color=colors["ink2"], width=1), fillcolor=colors["surface"]),
            decreasing=dict(line=dict(color=colors["ink2"], width=1), fillcolor=colors["ink2"]),
            hovertext=hover,
            hoverinfo="text",
            name="Price",
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    for start, end in rth_spans(bars.index, sessions):
        fig.add_vrect(x0=start - 0.5, x1=end + 0.5, fillcolor=colors["rth_shade"], line_width=0, layer="below", row=1, col=1)

    ymin, ymax, far = visible_range(bars, levels)
    near = [lv for lv in levels if lv not in far]
    label_y = spread_labels([lv.price for lv in near], (ymax - ymin) * 0.035, ymin, ymax)
    for lv, ly in zip(near, label_y):
        color = level_color(lv.group, colors)
        dash, _, width = LINE_STYLE.get(lv.key, ("solid", "-", 1.5))
        fig.add_shape(
            type="line", xref="paper", x0=0, x1=1, yref="y", y0=lv.price, y1=lv.price,
            line=dict(color=color, width=width, dash=dash), layer="above",
        )
        fig.add_annotation(
            xref="paper", x=1.0, xanchor="left", yref="y", y=ly, showarrow=False,
            text=f"{lv.key} {lv.price:,.2f}", font=dict(size=11, color=colors["ink"]),
            bgcolor=colors["surface"], bordercolor=color, borderwidth=1.5, borderpad=2,
        )
    for direction, items, y_paper, anchor in (("above", [lv for lv in far if lv.price > ymax], 1.0, "top"),
                                              ("below", [lv for lv in far if lv.price < ymin], 0.0, "bottom")):
        if items:
            arrow = "▲" if direction == "above" else "▼"
            text = f"{arrow} Off chart {direction}: " + " · ".join(f"{lv.key} {lv.price:,.2f}" for lv in items)
            fig.add_annotation(
                xref="paper", x=0.005, xanchor="left", yref="paper", y=y_paper, yanchor=anchor,
                text=text, showarrow=False, font=dict(size=11, color=colors["muted"]), bgcolor=colors["surface"],
            )

    if with_profile:
        rows = profile.bucketed(70)
        row_colors = np.where(rows["is_poc"], colors["profile_poc"], np.where(rows["in_value"], colors["profile_in"], colors["profile_out"]))
        fig.add_trace(
            go.Bar(
                y=rows["mid"], x=rows["volume"], orientation="h",
                width=(rows["high"] - rows["low"] + profile.tick).to_numpy() * 0.9,
                marker=dict(color=row_colors.tolist(), line=dict(width=0)),
                hovertemplate="%{customdata[0]:,.2f}-%{customdata[1]:,.2f}<br>volume %{x:,.0f}<extra>prior day profile</extra>",
                customdata=np.stack([rows["low"], rows["high"]], axis=1),
                showlegend=False,
            ),
            row=1,
            col=2,
        )
        fig.update_xaxes(visible=False, row=1, col=2)
        fig.add_annotation(
            xref="x2 domain", x=0.5, yref="paper", y=1.0, yanchor="bottom", showarrow=False,
            text="prior day<br>profile", font=dict(size=10, color=colors["muted"]),
        )

    # Legend: one entry per level family (identity is also carried by each line's text label)
    used = []
    for lv in levels:
        fam = FAMILY.get(lv.group, "value")
        if fam not in used:
            used.append(fam)
    for fam in used:
        fig.add_trace(
            go.Scatter(x=[None], y=[None], mode="lines", line=dict(color=colors[fam], width=2), name=FAMILY_NAMES[fam]),
            row=1,
            col=1,
        )

    tick_vals, tick_text = session_ticks(bars.index, sessions, clocks)
    fig.update_xaxes(
        tickmode="array", tickvals=tick_vals, ticktext=tick_text, showgrid=True, gridcolor=colors["grid"],
        rangeslider_visible=False, range=[-1, len(bars)], tickfont=dict(size=10, color=colors["ink2"]), tickangle=0, automargin=True,
        row=1, col=1,
    )
    fig.update_yaxes(
        range=[ymin, ymax], gridcolor=colors["grid"], tickformat=",.2f", tickfont=dict(color=colors["ink2"]),
        zeroline=False, automargin=True, row=1, col=1,
    )
    fig.update_layout(
        height=height,
        margin=dict(l=70, r=135, t=40, b=75),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=11, color=colors["ink2"])),
        hovermode="closest",
        bargap=0,
        plot_bgcolor=colors["surface"],
        paper_bgcolor=colors["surface"],
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=colors["ink"]),
    )
    return fig
