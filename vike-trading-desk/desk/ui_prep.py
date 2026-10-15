"""Tab 1 - Pre-Session Prep: levels, events, chart, checklist, PDF/PNG export, journal and review."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

from desk import econ_calendar, journal
from desk.charts import build_chart
from desk.config import Config, Instrument
from desk.levels import Level, PrepResult, chart_window, compute_prep
from desk.market_data import Bars, load_bars
from desk.sheet_export import SheetPage, sheet_pdf, sheet_png
from desk.theme import FAMILY, palette
from desk.timeutil import Clocks, default_target_date, front_contract, previous_weekday, rollover_warning

MARKET_STATES = [
    "Balance (rotating inside a range)",
    "Imbalance up (trending higher)",
    "Imbalance down (trending lower)",
    "Not clear yet",
]
OPEN_LOCATIONS = [
    "Above prior range",
    "Above value, inside range",
    "Inside value",
    "Below value, inside range",
    "Below prior range",
]
CONFIRMATIONS = [
    "Absorption at the level (heavy volume, price stops)",
    "Delta divergence / delta flip at the level",
    "Stacked imbalances (3+) in my direction",
    "Exhaustion: thin volume at the extreme / failed auction",
    "Cumulative delta confirms the move",
    "DOM: big orders refreshing (iceberg) or pulled",
    "Acceptance: time spent beyond the level (or fast rejection)",
    "Initiative volume pushing through the level",
]
DAY_TYPES = [
    "Not sure yet",
    "Trend day up",
    "Trend day down",
    "Normal day (stayed inside the first hour's range)",
    "Normal variation (range extended one side)",
    "Double distribution",
    "Neutral (extended both sides)",
    "Non-trend / quiet rotation",
]
MISTAKES = [
    "None today",
    "Entered without confirmation",
    "Traded in the middle (no location)",
    "Ignored the context",
    "Moved or removed my stop",
    "Position too big",
    "Revenge trade",
    "Chased / FOMO",
    "Traded into news",
    "Broke my max loss / max trades",
]
FAMILY_SHORT = {"value": "Profile", "prior": "Prior day", "overnight": "ON / weekly"}

DATA_NOTES = """
**Yahoo Finance (via yfinance): free, and good enough for daily prep levels, but know its limits:**
- **Unofficial.** yfinance reads Yahoo's website data. Yahoo sometimes rate-limits or changes things;
  then the library needs an update (double-click `update.bat`).
- **Delayed.** CME futures on Yahoo are delayed (usually 10+ minutes). Fine for prep, never for live
  entries: ATAS is your live data.
- **Short intraday history.** 1-minute bars only for about the last 8 days, 5-minute bars for about 60 days,
  hourly for about 2 years. The app saves everything it downloads, so if you open it daily your own
  1-minute history keeps growing.
- **Bars, not trades.** No bid/ask, no delta, no footprint. The volume profile spreads each bar's volume
  over its range, so VAH / VAL / POC are close to ATAS (usually within a few ticks) but not identical.
  Always confirm levels on your ATAS chart.
- **Continuous contract.** NQ=F / ES=F are Yahoo's front-month series. In rollover weeks they may show a
  different contract than your ATAS chart (the app warns you).

**For coded backtesting (weeks 8-12), the cheapest reliable source: Databento, pay-as-you-go.**
Official CME Globex data back to 2010: 1-minute bars plus tick-by-tick trades that record which side was the
aggressor, so you can rebuild real delta and footprint. No subscription is needed for historical data. You
pay per GB, and new accounts get $125 of free credit (it expires after 6 months). Databento's own example:
the free credit covers about 16 months of ES tick-by-tick trades, and 1-minute bars are far smaller. Their
estimator shows the exact price before you download.
Alternative: **FirstRate Data**, a one-time $199.95 for NQ 1-minute bars back to 2008 (simple CSV files,
bars only, no order flow) plus $99.95/year if you want updates.
*Prices checked 15 Oct 2026. Nothing has been bought or signed up for.*
"""


# ------------------------------------------------------------------ cached data


@st.cache_data(ttl=300, show_spinner=False)
def _bars(symbol: str, cache_dir: str, market_tz: str, refresh: int) -> Bars:
    return load_bars(symbol, Path(cache_dir), market_tz)


@st.cache_data(ttl=600, show_spinner=False)
def _events(day: dt.date, cache_dir: str, manual_csv: str, market_tz: str, use_feed: bool,
            countries: tuple, impacts: tuple, max_age: float, refresh: int, manual_mtime: float):
    return econ_calendar.get_events(day, Path(cache_dir), Path(manual_csv), market_tz,
                                    pd.Timestamp.now(tz=market_tz), use_feed, countries, impacts, max_age)


def _is_dark() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def _until(delta: pd.Timedelta) -> str:
    minutes = int(abs(delta).total_seconds() // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


def _clocks(cfg: Config) -> Clocks:
    return Clocks(cfg.you.home_tz, cfg.you.market_tz, cfg.you.home_label, cfg.you.market_label)


def _load_all(cfg: Config, clocks: Clocks, day: dt.date, now: pd.Timestamp) -> dict[str, tuple[Bars, PrepResult | None]]:
    out = {}
    refresh = st.session_state.get("refresh", 0)
    for inst in cfg.enabled_instruments:
        bars = _bars(inst.yahoo_symbol, str(cfg.cache_dir), cfg.you.market_tz, refresh)
        prep = None
        if not bars.empty:
            prep = compute_prep(bars.combined, inst, day, now, cfg.sessions, cfg.levels, clocks)
        out[inst.key] = (bars, prep)
    return out


def _get_events(cfg: Config, day: dt.date):
    csv = cfg.manual_events_csv
    mtime = csv.stat().st_mtime if csv.exists() else 0.0
    return _events(day, str(cfg.cache_dir), str(csv), cfg.you.market_tz, cfg.calendar.use_free_online_feed,
                   cfg.calendar.countries, cfg.calendar.impact_levels, cfg.calendar.refresh_every_hours,
                   st.session_state.get("refresh", 0), mtime)


# ------------------------------------------------------------------ entry point


def render(cfg: Config) -> None:
    st.session_state.setdefault("refresh", 0)
    clocks = _clocks(cfg)
    colors = palette(_is_dark())
    prep_tab, journal_tab = st.tabs(["📋 Today's prep", "📓 Journal & review"])
    with prep_tab:
        _render_prep(cfg, clocks, colors)
    with journal_tab:
        _render_journal(cfg, clocks, colors)


# ------------------------------------------------------------------ prep sheet


def _render_prep(cfg: Config, clocks: Clocks, colors: dict) -> None:
    now = clocks.now()
    default_day = default_target_date(now, cfg.sessions.rth_end)
    cols = st.columns([1.1, 1, 1.15, 1.25, 0.8], vertical_alignment="bottom")
    day = cols[0].date_input(
        "Session to prepare for", value=default_day, key="prep_day", format="YYYY-MM-DD",
        help="Defaults to the next session. Pick an earlier date to see the sheet as it was before that day's open.",
    )
    rth_open = clocks.market_ts(day, cfg.sessions.rth_start)
    deadline = clocks.home_ts(day, cfg.you.shift_start)
    with cols[1].container(border=True):
        st.markdown(f"**Now**  \n{clocks.dual(now)}")
    with cols[2].container(border=True):
        when = f"in {_until(rth_open - now)}" if rth_open > now else f"opened {_until(now - rth_open)} ago"
        st.markdown(f"**RTH open** ({when})  \n{clocks.dual(rth_open)}")
    with cols[3].container(border=True):
        if deadline > now:
            status = f"✅ {_until(deadline - now)} left"
        else:
            status = f"⏰ passed {_until(now - deadline)} ago"
        st.markdown(f"**Prep deadline: your shift** ({status})  \n{clocks.dual(deadline)}")
    if cols[4].button("🔄 Refresh data", help="Download the newest prices (the calendar feed refreshes on its own every few hours)"):
        st.session_state["refresh"] += 1
        st.rerun()
    st.caption(clocks.offset_note(now))

    with st.expander("ℹ️ About this data (please read once) + which paid data to use later"):
        st.markdown(DATA_NOTES)
        st.caption(f"Settings: `{cfg.app_dir / 'config.toml'}` · journal folder: `{cfg.journal_dir}`")

    instruments = cfg.enabled_instruments
    with st.spinner("Downloading prices from Yahoo Finance..."):
        loaded = _load_all(cfg, clocks, day, now)

    main = instruments[0]
    warning = rollover_warning(main.cme_root, day)
    if warning:
        st.warning(warning + (" The same applies to ES." if len(instruments) > 1 else ""), icon="⚠️")

    tabs = st.tabs([f"{inst.key} · {inst.name}" for inst in instruments])
    for tab, inst in zip(tabs, instruments):
        bars, prep = loaded[inst.key]
        with tab:
            _instrument_panel(cfg, clocks, colors, inst, bars, prep, day, now)

    events = _get_events(cfg, day)
    _events_section(cfg, clocks, events, day)

    preps = [loaded[i.key][1] for i in instruments if loaded[i.key][1] is not None and loaded[i.key][1].levels]
    _checklist_and_export(cfg, clocks, day, now, loaded, preps, events)


def _instrument_panel(cfg, clocks, colors, inst: Instrument, bars: Bars, prep: PrepResult | None, day, now) -> None:
    for problem in bars.problems:
        st.warning(problem, icon="⚠️")
    if prep is None:
        st.error(f"No price data for {inst.key} ({inst.yahoo_symbol}). Check your internet connection and press Refresh.")
        return
    if not prep.levels:
        for warning in prep.warnings:
            st.warning(warning, icon="⚠️")
        return

    contract = front_contract(inst.cme_root, day)
    m = st.columns(4)
    before_open = prep.as_of < now
    m[0].metric("Last price before the open" if before_open else "Last price", f"{prep.last_price:,.2f}",
                help=f"Bar used: {clocks.dual(prep.last_bar_time, '%a %d %b %H:%M')}. "
                     + ("The sheet shows the situation as of the 09:30 NY open." if before_open else "Yahoo data is delayed."))
    if prep.gap:
        label = "Opening gap" if prep.gap.kind == "opening" else "Gap vs prior close (pre-open)"
        m[1].metric(label, f"{prep.gap.points:+,.2f} pts", f"{prep.gap.percent:+.2f}%",
                    help=f"Prior RTH close {prep.gap.reference:,.2f}. "
                         + ("Uses today's 09:30 open." if prep.gap.kind == "opening" else "Uses the last price, since RTH hasn't opened yet."))
    if prep.prior_range is not None:
        m[2].metric("Prior RTH range", f"{prep.prior_range:,.2f} pts", help=f"= ${prep.prior_range * inst.point_value_usd:,.0f} per contract")
    if prep.overnight_range is not None:
        m[3].metric("Overnight range", f"{prep.overnight_range:,.2f} pts", help=f"= ${prep.overnight_range * inst.point_value_usd:,.0f} per contract")
    st.caption(
        f"Contract: {contract.label} · prior session {prep.prior_date:%a %d %b}"
        + (f" ({prep.prior_resolution} bars)" if prep.prior_resolution else "")
        + f" · levels as of {clocks.dual(prep.as_of, '%a %H:%M')}"
    )
    if prep.context:
        st.info("**Context hints** (textbook auction-market reading; confirm on your own chart):\n\n"
                + "\n".join(f"- {note}" for note in prep.context))
    for warning in prep.warnings:
        st.warning(warning, icon="⚠️")

    left, right = st.columns([0.37, 0.63])
    with left:
        st.markdown("**Price ladder** (highest first)")
        ladder = _ladder(prep)
        st.dataframe(_style_ladder(ladder), hide_index=True, height=min(38 + 35 * len(ladder), 640))
    with right:
        window = chart_window(bars.combined, day, cfg.chart.sessions_to_show, cfg.sessions, now)
        fig = build_chart(window, prep.levels, prep.prior_profile, clocks, cfg.sessions, cfg.chart.bar_minutes,
                          colors, cfg.chart.show_volume_profile)
        st.plotly_chart(fig, theme=None, key=f"chart_{inst.key}_{day}", config={"displaylogo": False})
        st.caption("Shaded = regular session (RTH). Hover a candle for both clocks. Thin dotted blue lines = naked POCs.")


def _ladder(prep: PrepResult) -> pd.DataFrame:
    rows = []
    last = prep.last_price
    marker_done = False
    for lv in sorted(prep.levels, key=lambda l: -l.price):
        if not marker_done and lv.price < last:
            rows.append(_last_row(prep))
            marker_done = True
        rows.append({
            "Level": lv.key,
            "What": lv.label + (f" ({lv.note})" if lv.note else ""),
            "Price": f"{lv.price:,.2f}",
            "vs last": f"{lv.price - last:+,.2f}",
            "Type": FAMILY_SHORT[FAMILY.get(lv.group, "value")],
        })
    if not marker_done:
        rows.append(_last_row(prep))
    return pd.DataFrame(rows, columns=["Level", "What", "Price", "vs last", "Type"])


def _last_row(prep: PrepResult) -> dict:
    when = prep.last_bar_time.strftime("%H:%M") if prep.last_bar_time is not None else ""
    return {"Level": "▶ LAST", "What": f"last price ({when} NY)", "Price": f"{prep.last_price:,.2f}", "vs last": "", "Type": ""}


def _style_ladder(df: pd.DataFrame):
    def highlight(row):
        style = "font-weight: bold; background-color: rgba(137,135,129,0.22)" if row["Level"] == "▶ LAST" else ""
        return [style] * len(row)

    return df.style.apply(highlight, axis=1)


# ------------------------------------------------------------------ events


def _events_section(cfg: Config, clocks: Clocks, events, day: dt.date) -> None:
    st.subheader(f"📅 Economic events · {day:%a %d %b}")
    impacts = " / ".join(cfg.calendar.impact_levels)
    countries = ", ".join(cfg.calendar.countries)
    if events.table.empty:
        if events.feed_ok:
            st.success(f"No {impacts.lower()}-impact events for {countries} on this day (holidays would show here too).")
        else:
            st.warning("No events available for this day. Add them manually below.", icon="⚠️")
    else:
        rth_open = clocks.market_ts(day, cfg.sessions.rth_start)
        rth_close = clocks.market_ts(day, cfg.sessions.rth_end)
        rows = []
        for _, ev in events.table.iterrows():
            if ev["all_day"]:
                kyiv = ny = "all day"
                when = "all day"
            else:
                kyiv = ev["time"].tz_convert(clocks.home).strftime("%H:%M")
                ny = ev["time"].strftime("%H:%M")
                when = "before the open" if ev["time"] < rth_open else ("during RTH" if ev["time"] < rth_close else "after the close")
            rows.append({cfg.you.home_label: kyiv, cfg.you.market_label: ny, "When": when, "Event(s)": ev["events"],
                         "Impact": ev["impact"], "Forecast / previous": ev["details"], "Source": ev["source"]})
        st.dataframe(pd.DataFrame(rows), hide_index=True)
    for note in events.notes:
        st.caption(note)

    with st.expander("Official calendars + add your own events"):
        st.markdown("Cross-check important days against the official schedules:\n\n"
                    + "\n".join(f"- [{name}]({url})" for name, url in econ_calendar.OFFICIAL_SOURCES))
        st.markdown(
            "**Your own events** (always shown, whatever the free feed says). One row per event: date as "
            "YYYY-MM-DD, time in **New York** time as HH:MM (leave empty for all-day), e.g. "
            "`2026-10-28 · 14:00 · FOMC rate decision · High`. Click **+** below the table to add a row."
        )
        manual = econ_calendar.load_manual(cfg.manual_events_csv)
        edited = st.data_editor(
            manual, num_rows="dynamic", hide_index=True, key="manual_events",
            column_config={
                "date": st.column_config.TextColumn("date (YYYY-MM-DD)"),
                "time_ny": st.column_config.TextColumn("time NY (HH:MM)"),
                "event": st.column_config.TextColumn("event", width="large"),
                "impact": st.column_config.SelectboxColumn("impact", options=["High", "Medium", "Low", "Holiday"]),
                "notes": st.column_config.TextColumn("notes"),
            },
        )
        if st.button("💾 Save my events"):
            econ_calendar.save_manual(edited, cfg.manual_events_csv)
            st.success("Saved.")
            st.rerun()


# ------------------------------------------------------------------ checklist + export


def _suggest_open_location(prep: PrepResult | None) -> int | None:
    if prep is None:
        return None
    pdh, pdl, vah, val = (prep.level(k) for k in ("PDH", "PDL", "VAH", "VAL"))
    if not all((pdh, pdl, vah, val)):
        return None
    ref = prep.gap.price if prep.gap else prep.last_price
    if ref > pdh.price:
        return 0
    if ref > vah.price:
        return 1
    if ref >= val.price:
        return 2
    if ref >= pdl.price:
        return 3
    return 4


def _events_summary(events, clocks: Clocks) -> str:
    if events.table.empty:
        return ""
    parts = []
    for _, ev in events.table.iterrows():
        when = "all day" if ev["all_day"] else clocks.dual(ev["time"])
        parts.append(f"{when}: {ev['events']}")
    return "\n".join(parts)


def _checklist_and_export(cfg: Config, clocks: Clocks, day: dt.date, now: pd.Timestamp, loaded, preps, events) -> None:
    st.subheader("🧭 Context → Location → Confirmation")
    saved = journal.load_entry(cfg.journal_dir, day)
    c = saved.get("checklist", {})
    if saved.get("saved_at"):
        st.caption(f"Loaded your saved plan for this day (saved {saved['saved_at']}). Saving again updates it.")

    level_options = list(dict.fromkeys(
        f"{p.instrument.key} {lv.key} {lv.price:,.2f}" + (f" ({lv.label.removeprefix('Naked POC ')})" if lv.key == "nPOC" else "")
        for p in preps for lv in sorted(p.levels, key=lambda l: -l.price)
    ))
    for old in c.get("key_locations", []):
        if old not in level_options:
            level_options.append(old)
    main_prep = preps[0] if preps else None
    suggested = _suggest_open_location(main_prep)
    k = day.isoformat()

    with st.form(f"checklist_{k}"):
        st.markdown("##### 1 · Context: what kind of day is this likely to be?")
        a, b = st.columns(2)
        market_state = a.radio(
            "Market state", MARKET_STATES,
            index=MARKET_STATES.index(c["market_state"]) if c.get("market_state") in MARKET_STATES else 3,
        )
        saved_loc = c.get("open_location")
        loc_index = OPEN_LOCATIONS.index(saved_loc) if saved_loc in OPEN_LOCATIONS else suggested
        open_location = b.selectbox(
            "Where is price vs yesterday?", OPEN_LOCATIONS, index=loc_index,
            placeholder="Choose...", help="Pre-selected from the main instrument's levels when possible.",
        )
        htf = st.text_area("Higher-timeframe context (multi-day balance or trend? where is weekly value?)", c.get("htf_context", ""))
        news = st.text_area("News / event risk today", c.get("news_risk") or _events_summary(events, clocks))
        scenarios = st.text_area("Scenarios: plan A / plan B (if price does X at level Y, I expect Z)", c.get("scenarios", ""))

        st.markdown("##### 2 · Location: where will I act?")
        key_locations = st.multiselect("Key levels I'll trade from", level_options,
                                       default=[x for x in c.get("key_locations", []) if x in level_options])
        extra = st.text_area(
            "Extra levels: options levels (QuantData / OptionsDepth: gamma flip, call/put walls) and levels from ATAS",
            c.get("extra_levels", ""),
        )
        plan = st.text_area("What I'll do at each location (long / short / only watch)", c.get("location_plan", ""))

        st.markdown("##### 3 · Confirmation: what must ATAS show before I enter?")
        checks = st.columns(2)
        saved_conf = set(c.get("confirmations", []))
        confirmations = [item for i, item in enumerate(CONFIRMATIONS)
                         if checks[i % 2].checkbox(item, value=item in saved_conf, key=f"conf_{k}_{i}")]
        trigger = st.text_area("Entry trigger, stop placement, and what invalidates the idea", c.get("trigger_invalidation", ""))

        st.markdown("##### 4 · Risk")
        r = st.columns(3)
        max_loss = r[0].number_input("Max daily loss ($)", min_value=0.0, step=50.0,
                                     value=float(c.get("max_daily_loss_usd", cfg.risk.max_daily_loss_usd)))
        max_trades = r[1].number_input("Max trades today", min_value=0, step=1,
                                       value=int(c.get("max_trades", cfg.risk.max_trades_per_day)))
        risk_trade = r[2].number_input("Risk per trade ($)", min_value=0.0, step=25.0,
                                       value=float(c.get("risk_per_trade_usd", cfg.risk.risk_per_trade_usd)))
        submitted = st.form_submit_button("💾 Save plan to journal + create PDF & PNG", type="primary")

    if submitted:
        checklist = {
            "market_state": market_state,
            "open_location": open_location or "",
            "htf_context": htf,
            "news_risk": news,
            "scenarios": scenarios,
            "key_locations": key_locations,
            "extra_levels": extra,
            "location_plan": plan,
            "confirmations": confirmations,
            "trigger_invalidation": trigger,
            "max_daily_loss_usd": max_loss,
            "max_trades": int(max_trades),
            "risk_per_trade_usd": risk_trade,
        }
        if not preps:
            st.error("There are no levels to put on the sheet yet (no price data). Your plan was not saved.")
            return
        with st.spinner("Creating the PDF/PNG and saving to your journal..."):
            pages = []
            for p in preps:
                bars = loaded[p.instrument.key][0]
                window = chart_window(bars.combined, day, cfg.chart.sessions_to_show, cfg.sessions, now)
                pages.append(SheetPage(p, window, events.table, checklist, front_contract(p.instrument.cme_root, day).label,
                                       rollover_warning(p.instrument.cme_root, day)))
            pdf = sheet_pdf(pages, clocks, cfg.sessions, now, cfg.chart.bar_minutes)
            pngs = {f"sheet_{pg.prep.instrument.key}.png": sheet_png(pg, clocks, cfg.sessions, now, cfg.chart.bar_minutes) for pg in pages}
            event_rows = [{**row, "time": row["time"].isoformat()} for row in events.table.to_dict("records")]
            folder = journal.save_entry(
                cfg.journal_dir, day,
                {
                    "saved_at": clocks.dual(now, "%a %d %b %H:%M"),
                    "instruments": {p.instrument.key: p.to_dict() for p in preps},
                    "events": event_rows,
                    "checklist": checklist,
                },
                files={"sheet.pdf": pdf, **pngs},
            )
        st.success(f"Saved to your journal: {folder}")

    _downloads(cfg, day)


def _downloads(cfg: Config, day: dt.date) -> None:
    folder = journal.entry_dir(cfg.journal_dir, day)
    pdf = folder / "sheet.pdf"
    pngs = sorted(folder.glob("sheet_*.png"))
    if not pdf.exists():
        st.caption("Save your plan to create the PDF/PNG sheet (it's also stored in your journal folder).")
        return
    st.markdown("**Download the sheet**")
    cols = st.columns(len(pngs) + 1)
    cols[0].download_button("⬇️ PDF (all instruments)", pdf.read_bytes(), file_name=f"prep_{day}.pdf",
                            mime="application/pdf", key=f"dl_pdf_{day}")
    for col, png in zip(cols[1:], pngs):
        name = png.stem.replace("sheet_", "")
        col.download_button(f"⬇️ PNG {name}", png.read_bytes(), file_name=f"prep_{day}_{name}.png",
                            mime="image/png", key=f"dl_{png.stem}_{day}")
    with st.expander("Preview the sheet"):
        for png in pngs:
            st.image(str(png))


# ------------------------------------------------------------------ journal & review


def _last_completed_session(now: pd.Timestamp, rth_end: dt.time) -> dt.date:
    if now.weekday() < 5 and now.time() >= rth_end:
        return now.date()
    return previous_weekday(now.date())


def _render_journal(cfg: Config, clocks: Clocks, colors: dict) -> None:
    st.markdown(
        "Review each session after it ends (weeks 1-4 of your plan): compare your plan with what price actually did, "
        "grade yourself honestly, and attach ATAS screenshots."
    )
    s = journal.stats(cfg.journal_dir)
    m = st.columns(4)
    m[0].metric("Days saved", s["days_saved"])
    m[1].metric("Days reviewed", s["days_reviewed"])
    m[2].metric("Followed my plan", f"{s['plan_followed_pct']:.0f}%" if s["plan_followed_pct"] is not None else "-")
    m[3].metric("Average grade", s["average_grade"] or "-")
    if s["top_mistake"]:
        st.caption(f"Most common mistake so far: **{s['top_mistake'][0]}** ({s['top_mistake'][1]}x)")

    now = clocks.now()
    day = st.date_input("Session to review", value=_last_completed_session(now, cfg.sessions.rth_end),
                        key="review_day", format="YYYY-MM-DD")
    saved_days = journal.list_entries(cfg.journal_dir)
    if saved_days:
        marks = []
        for d in saved_days[:12]:
            done = "review" in journal.load_entry(cfg.journal_dir, d)
            marks.append(f"{d:%a %d %b}{' ✅' if done else ''}")
        st.caption("Saved days: " + " · ".join(marks) + "  (✅ = reviewed)")

    entry = journal.load_entry(cfg.journal_dir, day)
    if "_unreadable" in entry:
        st.error(f"This day's journal file can't be read: {entry['_unreadable']}")
        entry = {}
    if not entry.get("checklist"):
        st.info("No prep sheet was saved for this day. You can still review it: the levels below are recalculated "
                "as they were before that day's open.")
    else:
        _show_saved_plan(cfg, day, entry)

    _review_charts(cfg, clocks, colors, day, now, entry)
    _review_form(cfg, clocks, day, now, entry)


def _show_saved_plan(cfg: Config, day: dt.date, entry: dict) -> None:
    c = entry["checklist"]
    folder = journal.entry_dir(cfg.journal_dir, day)
    with st.expander(f"Your plan for {day:%a %d %b} (saved {entry.get('saved_at', '')})", expanded=False):
        left, right = st.columns([0.45, 0.55])
        with left:
            st.markdown(
                f"**Market state:** {c.get('market_state', '')}  \n"
                f"**Open vs yesterday:** {c.get('open_location', '')}  \n"
                f"**Higher timeframe:** {c.get('htf_context', '') or '-'}  \n"
                f"**News risk:** {c.get('news_risk', '') or '-'}  \n"
                f"**Scenarios:** {c.get('scenarios', '') or '-'}  \n"
                f"**Key locations:** {', '.join(c.get('key_locations', [])) or '-'}  \n"
                f"**Extra levels:** {c.get('extra_levels', '') or '-'}  \n"
                f"**Plan at locations:** {c.get('location_plan', '') or '-'}  \n"
                f"**Confirmation needed:** {'; '.join(c.get('confirmations', [])) or '-'}  \n"
                f"**Trigger / invalidation:** {c.get('trigger_invalidation', '') or '-'}  \n"
                f"**Risk:** max loss ${c.get('max_daily_loss_usd', 0):,.0f} · max {c.get('max_trades', 0)} trades · "
                f"${c.get('risk_per_trade_usd', 0):,.0f}/trade"
            )
        with right:
            for png in sorted(folder.glob("sheet_*.png")):
                st.image(str(png), caption=png.name)


def _review_charts(cfg: Config, clocks: Clocks, colors: dict, day: dt.date, now: pd.Timestamp, entry: dict) -> None:
    st.markdown(f"##### How price actually traded around your levels · {day:%a %d %b}")
    instruments = cfg.enabled_instruments
    tabs = st.tabs([inst.key for inst in instruments])
    refresh = st.session_state.get("refresh", 0)
    for tab, inst in zip(tabs, instruments):
        with tab:
            bars = _bars(inst.yahoo_symbol, str(cfg.cache_dir), cfg.you.market_tz, refresh)
            if bars.empty:
                st.warning("No price data available.")
                continue
            saved_levels = entry.get("instruments", {}).get(inst.key, {}).get("levels")
            prep = compute_prep(bars.combined, inst, day, now, cfg.sessions, cfg.levels, clocks)
            levels = [Level(**lv) for lv in saved_levels] if saved_levels else prep.levels
            window = chart_window(bars.combined, day, 1, cfg.sessions, now)
            if window.empty or not levels:
                st.info("This day is outside the data the app has (Yahoo keeps intraday bars for about 60 days).")
                continue
            fig = build_chart(window, levels, prep.prior_profile, clocks, cfg.sessions, cfg.chart.bar_minutes, colors,
                              cfg.chart.show_volume_profile, height=560)
            st.plotly_chart(fig, theme=None, key=f"review_chart_{inst.key}_{day}", config={"displaylogo": False})
            source = "your saved levels" if saved_levels else "levels recalculated as of that open"
            st.caption(f"Lines = {source}. The last shaded block is the session you're reviewing.")


def _review_form(cfg: Config, clocks: Clocks, day: dt.date, now: pd.Timestamp, entry: dict) -> None:
    r = entry.get("review", {})
    k = day.isoformat()
    st.markdown("##### Your review")
    with st.form(f"review_{k}", clear_on_submit=False):
        a, b = st.columns(2)
        day_type = a.selectbox("What kind of day was it?", DAY_TYPES,
                               index=DAY_TYPES.index(r["day_type"]) if r.get("day_type") in DAY_TYPES else 0)
        followed = b.radio("Did I follow my plan?", ["Yes", "Partly", "No", "Didn't trade"], horizontal=True,
                           index=["Yes", "Partly", "No", "Didn't trade"].index(r["followed_plan"])
                           if r.get("followed_plan") in ("Yes", "Partly", "No", "Didn't trade") else 3)
        happened = st.text_area("What happened? (context in hindsight: balance or trend, who was in control)", r.get("what_happened", ""))
        reactions = st.text_area("Which levels mattered, and what did order flow show there (absorption, delta, imbalances)?",
                                 r.get("level_reactions", ""))
        c1, c2 = st.columns(2)
        trades = c1.number_input("Trades taken (live or sim)", min_value=0, step=1, value=int(r.get("trades", 0)))
        result_r = c2.number_input("Result in R (e.g. +1.5 or -1)", step=0.25, value=float(r.get("result_r", 0.0)))
        mistakes = st.multiselect("Mistakes", MISTAKES, default=[m for m in r.get("mistakes", []) if m in MISTAKES])
        lessons = st.text_area("Lessons: what will I do differently tomorrow?", r.get("lessons", ""))
        grade = st.select_slider("Grade my process (not my P/L)", ["F", "D", "C", "B", "A"], value=r.get("grade", "C"))
        shots = st.file_uploader("Attach ATAS screenshots (PNG/JPG)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
        saved = st.form_submit_button("💾 Save review", type="primary")
    if saved:
        review = {
            "day_type": day_type, "followed_plan": followed, "what_happened": happened, "level_reactions": reactions,
            "trades": int(trades), "result_r": float(result_r), "mistakes": mistakes, "lessons": lessons, "grade": grade,
            "reviewed_at": clocks.dual(now, "%a %d %b %H:%M"),
        }
        journal.save_entry(cfg.journal_dir, day, {"review": review})
        for shot in shots or []:
            journal.save_screenshot(cfg.journal_dir, day, shot.name, shot.getvalue())
        st.success("Review saved.")
    images = journal.list_screenshots(cfg.journal_dir, day)
    if images:
        st.markdown("**Screenshots**")
        st.image([str(p) for p in images], caption=[p.name for p in images], width=360)
