"""Vike Trading Desk. Start it with start.bat (Windows), or: streamlit run app.py"""
from pathlib import Path

import streamlit as st

from desk import ui_learning, ui_prep, ui_research
from desk.config import ConfigError, ensure_user_config, load_config

APP_DIR = Path(__file__).resolve().parent

st.set_page_config(page_title="Vike Trading Desk", page_icon="📈", layout="wide")

try:
    cfg = load_config(ensure_user_config(APP_DIR))
except ConfigError as exc:
    st.error(f"**Your settings file needs a fix.** {exc}")
    st.info("Open config.toml with Notepad, fix the line mentioned above, save, then press R in this browser tab.")
    st.stop()

st.title("📈 Vike Trading Desk")
tab_prep, tab_research, tab_learn = st.tabs(["📋 Pre-Session Prep", "📊 Equity Research", "🎓 Learning Roadmap"])

with tab_prep:
    ui_prep.render(cfg)

with tab_research:
    ui_research.render(cfg)

with tab_learn:
    ui_learning.render(cfg)
