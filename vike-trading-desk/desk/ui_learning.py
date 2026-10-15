"""Tab 3 - Learning Roadmap: modules, checked resource links, progress checkboxes that save."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

from desk.config import Config
from desk.learning import (
    Module,
    Progress,
    Roadmap,
    RoadmapError,
    add_my_link,
    complete_key,
    current_week,
    exercise_key,
    load_roadmap,
    module_progress,
    next_monday,
)

LEARNING_DIR = Path(__file__).resolve().parents[1] / "learning"


def _progress_path(cfg: Config) -> Path:
    return cfg.app_dir / "data" / "learning_progress.json"


def _save_tick(path: Path, key: str, widget_key: str) -> None:
    Progress(path).set_done(key, bool(st.session_state.get(widget_key)))


def _save_note(path: Path, module_id: str, widget_key: str) -> None:
    Progress(path).set_note(module_id, st.session_state.get(widget_key, ""))


def render(cfg: Config, learning_dir: Path = LEARNING_DIR) -> None:
    try:
        roadmap = load_roadmap(learning_dir)
    except RoadmapError as exc:
        st.error(str(exc))
        return
    path = _progress_path(cfg)
    progress = Progress(path)
    for problem in roadmap.problems:
        st.warning(problem, icon="⚠️")

    st.subheader(roadmap.title)
    today = dt.date.today()
    trading, equity = roadmap.track("Trading"), roadmap.track("Equity")
    cols = st.columns([1.2, 1, 1])
    start = progress.start_date
    picked = cols[0].date_input(
        "Week 1 starts on", value=start or next_monday(today), key="learn_start", format="YYYY-MM-DD",
        help="Pick the Monday your 12-week plan starts. The app then shows what to study each week.",
    )
    if picked != start:
        progress.set_start_date(picked)
        start = picked
    for col, name, mods in ((cols[1], "Trading track", trading), (cols[2], "Equity track", equity)):
        share = sum(module_progress(m, progress) for m in mods) / max(len(mods), 1)
        done = sum(module_progress(m, progress) >= 1 for m in mods)
        col.metric(name, f"{share:.0%}", f"{done}/{len(mods)} modules complete", delta_color="off")
        col.progress(share)

    week = current_week(start, today)
    total = roadmap.total_weeks
    if week is None:
        st.info(f"Your plan starts on **{start:%A %d %B %Y}**. Until then, skim the week-1 modules below.")
    elif week > total:
        st.success(f"You've completed all {total} weeks of the plan 🎉 Keep reviewing the modules you haven't ticked.")
    else:
        stages = " + ".join(roadmap.stages_for_week(week))
        st.markdown(f"### 📍 Week {week} of {total} · {stages}")
        st.caption(roadmap.week_focus.get(week, ""))
        for m in roadmap.modules_for_week(week):
            st.markdown(f"- **{m.id} · {m.title}** - {module_progress(m, progress):.0%} done")

    with st.expander("🗓️ Week-by-week plan", expanded=week is None):
        st.dataframe(_plan_table(roadmap, progress, start), hide_index=True)
        for stage in roadmap.stages:
            st.caption(f"**Weeks {stage['weeks'][0]}-{stage['weeks'][1]} · {stage['name']}:** {stage['detail']}")

    tab_t, tab_e = st.tabs([f"📈 Trading track ({len(trading)} modules)", f"🏦 Equity analysis track ({len(equity)} modules)"])
    with tab_t:
        for m in trading:
            _module(m, progress, path, week)
    with tab_e:
        for m in equity:
            _module(m, progress, path, week)

    with st.expander("➕ Add your own link to a module"):
        st.caption("Saved in learning/my_links.csv - you can also open that file with Excel or Notepad.")
        with st.form("add_link", clear_on_submit=True):
            module_id = st.selectbox("Module", [m.id for m in roadmap.modules],
                                     format_func=lambda i: f"{i} · {roadmap.module(i).title}")
            title = st.text_input("Title")
            url = st.text_input("Link (https://...)")
            note = st.text_input("Note (optional)")
            if st.form_submit_button("Add link"):
                try:
                    add_my_link(learning_dir, module_id, title, url, note)
                    st.success("Link added.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def _plan_table(roadmap: Roadmap, progress: Progress, start: dt.date | None) -> pd.DataFrame:
    rows = []
    for week in range(1, roadmap.total_weeks + 1):
        mods = roadmap.modules_for_week(week)
        dates = ""
        if start:
            first = start + dt.timedelta(weeks=week - 1)
            dates = f"{first:%d %b} - {first + dt.timedelta(days=6):%d %b}"
        rows.append({
            "Week": week,
            "Dates": dates,
            "Stage": " + ".join(roadmap.stages_for_week(week)),
            "Trading": ", ".join(f"{m.id} {m.title.split(':')[0]}" for m in mods if m.track == "Trading"),
            "Equity": ", ".join(f"{m.id} {m.title}" for m in mods if m.track == "Equity"),
            "Done": "✅" if mods and all(module_progress(m, progress) >= 1 for m in mods) else "",
        })
    return pd.DataFrame(rows)


def _module(m: Module, progress: Progress, path: Path, week: int | None) -> None:
    share = module_progress(m, progress)
    icon = "✅" if share >= 1 else ("🟡" if share > 0 else "⬜")
    here = " · 📍 this week" if week in m.weeks else ""
    with st.expander(f"{icon} {m.id} · {m.title} ({m.week_label}){here}"):
        st.progress(share)
        left, right = st.columns(2)
        with left:
            st.markdown("**What to learn**")
            st.markdown(m.learn)
        with right:
            st.markdown("**Why it matters for your strategy**")
            st.markdown(m.why)
        st.markdown("**Practical exercise**")
        st.markdown(m.exercise)

        st.markdown("**Resources** (tick when you've worked through one)")
        for link in m.links:
            key = f"chk_{link.key}"
            c1, c2 = st.columns([0.05, 0.95], vertical_alignment="center")
            c1.checkbox("done", value=progress.is_done(link.key), key=key, label_visibility="collapsed",
                        on_change=_save_tick, args=(path, link.key, key))
            extra = f" - {link.note}" if link.note else ""
            mine = " · *your link*" if link.mine else ""
            c2.markdown(f"[{link.title}]({link.url}) · {link.source} · *{link.kind}*{extra}{mine}")

        ex_key, done_key, note_key = f"ex_{m.id}", f"done_{m.id}", f"note_{m.id}"
        st.checkbox("I did the practical exercise", value=progress.is_done(exercise_key(m.id)), key=ex_key,
                    on_change=_save_tick, args=(path, exercise_key(m.id), ex_key))
        st.text_area("My notes for this module (saved automatically when you click outside the box)",
                     value=progress.note(m.id), key=note_key, on_change=_save_note, args=(path, m.id, note_key))
        st.checkbox("✅ Module complete", value=progress.is_done(complete_key(m.id)), key=done_key,
                    on_change=_save_tick, args=(path, complete_key(m.id), done_key))
