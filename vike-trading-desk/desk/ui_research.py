"""Tab 2 - Equity Research: SEC tear sheets, multiples, DCF + sensitivity, bank metrics, ad KPIs, notes, compare."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from desk import research_store
from desk.config import Config
from desk.edgar import SecClient, SecError, is_bank, revenue_breakdown, valid_user_agent
from desk.fundamentals import add_bank_ratios, add_ratios, annual_table, cagr, latest_instant, snapshot
from desk.market_data import stock_prices
from desk.valuation import DcfInputs, dcf, grid, implied_growth, implied_roe, justified_pb, multiples, pb_grid, tornado

GROUP_LABEL = {"quality": "Quality", "banks": "Bank", "ad_driven": "Ad-driven"}


def money(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    a = abs(v)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if a >= div:
            return f"${v / div:,.2f}{suf}"
    return f"${v:,.0f}"


def pct(v) -> str:
    return "-" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v * 100:.1f}%"


def mult(v) -> str:
    return "-" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.1f}x"


@st.cache_data(ttl=3600, show_spinner=False)
def _company(ticker: str, ua: str, cache_dir: str) -> dict:
    client = SecClient(ua, Path(cache_dir))
    cik, title = client.cik_for(ticker)
    facts = client.company_facts(cik)
    subs = client.submissions(cik)
    table = annual_table(facts)
    if table.empty:
        raise SecError(f"No annual (10-K) financial data found for {ticker}.")
    return {"cik": cik, "name": facts.get("entityName") or title, "sic_desc": subs.get("sicDescription", ""),
            "bank_sic": is_bank(subs), "table": table, "snap": snapshot(facts, table),
            "cet1": latest_instant(facts, "cet1")[0]}


@st.cache_data(ttl=900, show_spinner=False)
def _prices(ticker: str):
    return stock_prices(ticker)


@st.cache_data(ttl=86400, show_spinner=False)
def _breakdown(ticker: str, ua: str, cache_dir: str) -> pd.DataFrame:
    client = SecClient(ua, Path(cache_dir))
    cik, _ = client.cik_for(ticker)
    found = client.latest_annual_instance(cik)
    return revenue_breakdown(found[0]) if found else pd.DataFrame()


def _user_agent(cfg: Config) -> str | None:
    if valid_user_agent(cfg.research.sec_user_agent):
        return cfg.research.sec_user_agent
    path = cfg.app_dir / "data" / "sec_contact.txt"
    saved = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    if valid_user_agent(saved):
        return saved
    st.info("The SEC requires a name and email to use its free company data (sent only to sec.gov). Enter them once:")
    with st.form("sec_contact"):
        text = st.text_input("Your name and email", placeholder="Vike Petrenko vike@gmail.com")
        if st.form_submit_button("Save"):
            if valid_user_agent(text):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text.strip(), encoding="utf-8")
                st.rerun()
            else:
                st.error("Please type a name AND an email address, e.g. 'Vike Petrenko vike@gmail.com'.")
    return None


def _line(series: dict[str, pd.Series], title: str, percent: bool = False, height: int = 280) -> go.Figure:
    colors = ["#2a78d6", "#eb6834", "#1baf7a"]
    fig = go.Figure()
    for (name, s), color in zip(series.items(), colors):
        s = s.dropna()
        fig.add_trace(go.Scatter(x=[f"FY{d:%Y}" for d in s.index], y=s.values * (100 if percent else 1), name=name,
                                 mode="lines+markers", line=dict(color=color, width=2)))
    fig.update_layout(title=title, height=height, margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h"),
                      yaxis_ticksuffix="%" if percent else "")
    return fig


def _years_table(t: pd.DataFrame, rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    out = {}
    for col, label, kind in rows:
        if col not in t:
            continue
        fmt = {"money": money, "pct": pct, "x": mult, "num": lambda v: "-" if pd.isna(v) else f"{v:,.2f}",
               "shares": lambda v: "-" if pd.isna(v) else f"{v / 1e6:,.0f}M"}[kind]
        out[label] = [fmt(v) for v in t[col]]
    df = pd.DataFrame(out, index=[f"FY{d:%Y}" for d in t.index]).T
    return df.loc[:, ~df.columns.duplicated()]


def render(cfg: Config) -> None:
    ua = _user_agent(cfg)
    if not ua:
        return
    cache_dir = str(cfg.cache_dir / "sec")
    store_dir = cfg.app_dir / "data" / "research"
    options = [(t, g) for g, tickers in cfg.coverage.items() for t in tickers]
    c1, c2 = st.columns([2, 1])
    pick = c1.selectbox("Company (coverage list from config.toml)", options,
                        format_func=lambda o: f"{o[0]} · {GROUP_LABEL.get(o[1], o[1])}") if options else None
    other = c2.text_input("...or any US ticker").strip().upper()
    ticker, group = (other, "") if other else (pick if pick else ("", ""))
    if not ticker:
        st.info("Add tickers to [coverage] in config.toml.")
        return
    try:
        with st.spinner(f"Loading {ticker} from SEC EDGAR..."):
            comp = _company(ticker, ua, cache_dir)
    except SecError as exc:
        st.error(str(exc))
        return
    bank = group == "banks" or comp["bank_sic"]
    ad = group == "ad_driven"
    price, monthly, problem = _prices(ticker)
    if price is None:
        st.warning(problem or "No price from Yahoo.")
        price = st.number_input("Enter the share price manually", min_value=0.0, value=0.0, key=f"px_{ticker}") or None
    store = research_store.load(store_dir, ticker)
    st.markdown(f"### {comp['name']} ({ticker}) · {comp['sic_desc']}")
    st.caption(f"Fundamentals: SEC EDGAR XBRL (10-K / 10-Q). Price: Yahoo Finance {money(price) if price else ''}. "
               f"{'Bank metrics shown (DCF does not fit banks).' if bank else ''}")
    tabs = st.tabs(["📄 Tear sheet", "💰 Valuation", "📣 KPIs", "📝 Notes", "⚖️ Compare"])
    with tabs[0]:
        (_bank_sheet if bank else _tear_sheet)(ticker, comp, price, monthly, store, store_dir)
        if ad or st.checkbox("Load revenue by segment / product from the latest 10-K", key=f"seg_{ticker}"):
            _segments(ticker, ua, cache_dir)
    with tabs[1]:
        (_bank_value if bank else _dcf_ui)(ticker, comp, price, store, store_dir, cfg)
    with tabs[2]:
        _kpis(ticker, store, store_dir, ad)
    with tabs[3]:
        _notes(ticker, store, store_dir)
    with tabs[4]:
        _compare(cfg, ua, cache_dir, ticker)


def _tear_sheet(ticker, comp, price, monthly, store, store_dir) -> None:
    t = add_ratios(comp["table"])
    s = comp["snap"]
    m = multiples(price, s.shares, s.revenue, s.operating_income, s.net_income, s.fcf, s.eps, s.cash, s.debt)
    cols = st.columns(6)
    cols[0].metric("Market cap", money(m["market_cap"]))
    cols[1].metric("EV", money(m["ev"]))
    cols[2].metric("P/E (TTM)", mult(m["pe"]))
    cols[3].metric("EV/EBIT (TTM)", mult(m["ev_ebit"]))
    cols[4].metric("FCF yield", pct(m["fcf_yield"]))
    cols[5].metric("Revenue CAGR 5y", pct(cagr(t["revenue"], 5)))
    cols = st.columns(6)
    cols[0].metric("Revenue (TTM)", money(s.revenue))
    cols[1].metric("Operating margin", pct(s.operating_income / s.revenue if s.revenue and s.operating_income is not None else None))
    cols[2].metric("FCF (TTM)", money(s.fcf))
    cols[3].metric("ROIC (last FY)", pct(t["roic"].dropna().iloc[-1] if t["roic"].notna().any() else None))
    cols[4].metric("Net debt", money((s.debt or 0) - (s.cash or 0)))
    cols[5].metric("Shares", f"{s.shares / 1e6:,.0f}M" if s.shares else "-")
    st.caption(f"TTM = {s.period_note}.")
    st.dataframe(_years_table(t, [
        ("revenue", "Revenue", "money"), ("revenue_growth", "Revenue growth", "pct"), ("gross_margin", "Gross margin", "pct"),
        ("operating_margin", "Operating margin", "pct"), ("net_margin", "Net margin", "pct"), ("fcf", "Free cash flow", "money"),
        ("fcf_margin", "FCF margin", "pct"), ("roic", "ROIC", "pct"), ("roe", "ROE", "pct"), ("total_debt", "Total debt", "money"),
        ("cash_total", "Cash + ST investments", "money"), ("shares_diluted", "Diluted shares", "shares"),
        ("eps_diluted", "EPS (diluted)", "num"), ("sbc", "Stock-based comp", "money"), ("buybacks", "Buybacks", "money"),
        ("dividends", "Dividends", "money")]))
    a, b = st.columns(2)
    a.plotly_chart(_line({"Revenue": t["revenue"], "FCF": t["fcf"]}, "Revenue and free cash flow ($)"), key=f"c1_{ticker}")
    b.plotly_chart(_line({"Gross": t["gross_margin"], "Operating": t["operating_margin"], "FCF": t["fcf_margin"]}, "Margins", True), key=f"c2_{ticker}")
    a, b = st.columns(2)
    a.plotly_chart(_line({"ROIC": t["roic"], "ROE": t["roe"]}, "Returns on capital", True), key=f"c3_{ticker}")
    b.plotly_chart(_line({"Diluted shares": t["shares_diluted"]}, "Share count"), key=f"c4_{ticker}")
    if len(monthly):
        px_at = monthly.reindex(t.index, method="ffill") if monthly.index.is_monotonic_increasing else monthly
        hist = pd.DataFrame({"P/E": px_at / t["eps_diluted"], "FCF yield": t["fcf"] / (px_at * t["shares_diluted"])}, index=t.index)
        st.dataframe(_years_table(hist.rename(columns={"P/E": "pe", "FCF yield": "fy"}), [("pe", "P/E at FY end", "x"), ("fy", "FCF yield at FY end", "pct")]))


def _bank_sheet(ticker, comp, price, monthly, store, store_dir) -> None:
    t = add_bank_ratios(comp["table"])
    s = comp["snap"]
    last = t.iloc[-1]
    bvps = last["common_equity"] / s.shares if s.shares else None
    tbvps = last["tangible_common_equity"] / s.shares if s.shares else None
    manual = store.get("manual", {})
    cols = st.columns(5)
    cols[0].metric("P/B", mult(price / bvps if price and bvps else None))
    cols[1].metric("P/TBV", mult(price / tbvps if price and tbvps else None))
    cols[2].metric("ROE (last FY)", pct(last["roe"]))
    cols[3].metric("ROTCE (last FY)", pct(last["rotce"]))
    cols[4].metric("Efficiency ratio", pct(last["efficiency_ratio"]))
    cols = st.columns(5)
    cols[0].metric("NII / avg assets", pct(last["nii_to_avg_assets"]), help="Approximate NIM (banks report NIM on interest-earning assets).")
    cet1 = comp["cet1"] or manual.get("cet1")
    cols[1].metric("CET1 ratio", pct(cet1) if cet1 else "enter below")
    cols[2].metric("Loan growth", pct(last["loan_growth"]))
    cols[3].metric("Provision / loans", pct(last["provision_to_loans"]))
    cols[4].metric("Net charge-offs / loans", pct(last["nco_ratio"]))
    st.dataframe(_years_table(t, [
        ("bank_revenue", "Total net revenue", "money"), ("nii", "Net interest income", "money"), ("nonint_income", "Noninterest income", "money"),
        ("nonint_expense", "Noninterest expense", "money"), ("provision", "Provision for credit losses", "money"),
        ("ni_common", "Net income to common", "money"), ("loans", "Loans", "money"), ("deposits", "Deposits", "money"),
        ("common_equity", "Common equity", "money"), ("tangible_common_equity", "Tangible common equity", "money"),
        ("roe", "ROE", "pct"), ("rotce", "ROTCE", "pct"), ("efficiency_ratio", "Efficiency ratio", "pct"),
        ("nii_to_avg_assets", "NII / avg assets", "pct"), ("loan_growth", "Loan growth", "pct"), ("nco_ratio", "NCO ratio", "pct")]))
    a, b = st.columns(2)
    a.plotly_chart(_line({"ROE": t["roe"], "ROTCE": t["rotce"]}, "Returns", True), key=f"b1_{ticker}")
    b.plotly_chart(_line({"Efficiency": t["efficiency_ratio"], "NII/avg assets": t["nii_to_avg_assets"]}, "Efficiency and margin", True), key=f"b2_{ticker}")
    with st.form(f"manual_{ticker}"):
        st.caption("Reported figures not in the SEC data (from the 10-K / earnings release):")
        c1, c2 = st.columns(2)
        cet1_in = c1.number_input("CET1 ratio (%)", value=float((manual.get("cet1") or 0) * 100), step=0.1)
        nim_in = c2.number_input("Reported NIM (%)", value=float((manual.get("nim") or 0) * 100), step=0.01)
        if st.form_submit_button("Save"):
            research_store.save(store_dir, ticker, {"manual": {"cet1": cet1_in / 100 or None, "nim": nim_in / 100 or None}})
            st.success("Saved.")


def _segments(ticker, ua, cache_dir) -> None:
    try:
        df = _breakdown(ticker, ua, cache_dir)
    except SecError as exc:
        st.warning(str(exc))
        return
    if df.empty:
        st.caption("No segment / product revenue found in the latest 10-K data.")
        return
    latest = df[df["end"] == df["end"].max()]
    st.markdown(f"**Revenue by segment / product (fiscal year to {df['end'].max():%d %b %Y}, latest 10-K)**")
    st.dataframe(latest.assign(value=latest["value"].map(money))[["axis", "member", "value"]], hide_index=True)
    ads = df[df["member"].str.contains("Advertis", case=False)]
    if not ads.empty:
        st.success("Advertising revenue (from the 10-K): " + ", ".join(f"FY{r.end:%Y} {money(r.value)}" for r in ads.sort_values("end").itertuples()))


def _dcf_ui(ticker, comp, price, store, store_dir, cfg) -> None:
    t = add_ratios(comp["table"])
    s = comp["snap"]
    saved = store.get("dcf", {})
    margin0 = (s.operating_income / s.revenue) if s.revenue and s.operating_income else float(t["operating_margin"].dropna().iloc[-1])
    g5 = cagr(t["revenue"], 5) or 0.05
    st.markdown("**DCF (free cash flow to the firm).** Move the sliders; everything recalculates.")
    c = st.columns(4)
    growth = c[0].slider("Revenue growth, yrs 1-5 (%)", -10.0, 40.0, float(saved.get("growth", round(min(max(g5, 0), 0.3) * 100, 1))), 0.5, key=f"g_{ticker}") / 100
    target = c[1].slider("Target operating margin (%)", 0.0, 70.0, float(saved.get("target_margin", round(margin0 * 100, 1))), 0.5, key=f"m_{ticker}") / 100
    rate = c[2].slider("Discount rate / WACC (%)", 5.0, 15.0, float(saved.get("discount_rate", cfg.research.discount_rate)), 0.25, key=f"r_{ticker}") / 100
    tg = c[3].slider("Terminal growth (%)", 0.0, 4.0, float(saved.get("terminal_growth", cfg.research.terminal_growth)), 0.25, key=f"tg_{ticker}") / 100
    with st.expander("Advanced assumptions"):
        a = st.columns(3)
        tax = a[0].slider("Tax rate (%)", 0.0, 35.0, float(saved.get("tax_rate", round(t["tax_rate"].tail(3).median() * 100, 1))), 0.5, key=f"tx_{ticker}") / 100
        s2c = a[1].slider("Sales-to-capital", 0.5, 5.0, float(saved.get("sales_to_capital", 1.5)), 0.1, key=f"sc_{ticker}")
        yrs = a[2].slider("Years to reach target margin", 1, 10, int(saved.get("years_to_target", 5)), key=f"yt_{ticker}")
    inp = DcfInputs(revenue0=s.revenue or float(t["revenue"].dropna().iloc[-1]), growth=growth, terminal_growth=tg,
                    margin0=margin0, target_margin=target, discount_rate=rate, tax_rate=tax, sales_to_capital=s2c,
                    years_to_target=yrs, cash=s.cash or 0, debt=s.debt or 0, shares=s.shares or float(t["shares_diluted"].dropna().iloc[-1]))
    try:
        res = dcf(inp)
    except ValueError as exc:
        st.error(str(exc))
        return
    cols = st.columns(4)
    cols[0].metric("Value per share", f"${res.per_share:,.2f}",
                   f"{(res.per_share / price - 1) * 100:+.0f}% vs price" if price else None)
    cols[1].metric("Price", f"${price:,.2f}" if price else "-")
    cols[2].metric("Terminal value share", pct(res.terminal_share))
    ig = implied_growth(inp, price) if price else None
    cols[3].metric("Reverse DCF: growth priced in", pct(ig) if ig is not None else "-", help="Yrs 1-5 growth at which value = price.")
    tor = tornado(inp)
    fig = go.Figure(go.Bar(y=tor["assumption"], x=(tor["high"] - tor["low"]).abs(), base=tor[["low", "high"]].min(axis=1),
                           orientation="h", marker_color="#2a78d6",
                           text=[f"${lo:,.0f} → ${hi:,.0f}" for lo, hi in zip(tor["low"], tor["high"])], textposition="outside"))
    fig.add_vline(x=res.per_share, line_color="#52514e")
    if price:
        fig.add_vline(x=price, line_dash="dash", line_color="#eb6834", annotation_text="price")
    fig.update_layout(title="Sensitivity: value per share when each assumption moves (others fixed)", height=320,
                      margin=dict(l=10, r=10, t=40, b=10), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, key=f"tor_{ticker}")
    st.caption("Steps: growth ±5pp, margin ±5pp, discount rate ±1pp, terminal growth ±1pp, sales-to-capital ±0.5, tax ±5pp. Longest bar = matters most.")
    st.markdown("**Value per share: discount rate (rows) × terminal growth (columns)**")
    st.dataframe(grid(inp).map(lambda v: "-" if pd.isna(v) else f"${v:,.0f}"))
    with st.expander("Projection table"):
        st.dataframe(res.table.style.format({"growth": "{:.1%}", "operating_margin": "{:.1%}", "revenue": "{:,.0f}", "ebit": "{:,.0f}",
                                             "nopat": "{:,.0f}", "reinvestment": "{:,.0f}", "fcff": "{:,.0f}",
                                             "discount_factor": "{:.3f}", "pv_fcff": "{:,.0f}"}), hide_index=True)
    if st.button("💾 Save these assumptions", key=f"save_dcf_{ticker}"):
        research_store.save(store_dir, ticker, {"dcf": {"growth": growth * 100, "target_margin": target * 100, "discount_rate": rate * 100,
                                                       "terminal_growth": tg * 100, "tax_rate": tax * 100, "sales_to_capital": s2c,
                                                       "years_to_target": yrs, "value_per_share": res.per_share}})
        st.success("Saved.")


def _bank_value(ticker, comp, price, store, store_dir, cfg) -> None:
    t = add_bank_ratios(comp["table"])
    s = comp["snap"]
    st.markdown("**Justified P/B = (ROE - g) / (cost of equity - g).** A bank earning exactly its cost of equity is worth 1x book.")
    basis = st.radio("Book value basis", ["Tangible book (with ROTCE)", "Book (with ROE)"], horizontal=True, key=f"basis_{ticker}")
    tangible = basis.startswith("Tangible")
    hist = (t["rotce"] if tangible else t["roe"]).dropna().tail(3).mean()
    c = st.columns(3)
    roe = c[0].slider("ROE / ROTCE you expect (%)", 0.0, 30.0, float(round((hist if pd.notna(hist) else 0.12) * 100, 1)), 0.5, key=f"roe_{ticker}") / 100
    coe = c[1].slider("Cost of equity (%)", 6.0, 15.0, float(cfg.research.bank_cost_of_equity), 0.25, key=f"coe_{ticker}") / 100
    g = c[2].slider("Long-term growth (%)", 0.0, 6.0, 3.0, 0.25, key=f"bg_{ticker}") / 100
    book = t["tangible_common_equity" if tangible else "common_equity"].dropna().iloc[-1]
    per_share_book = book / s.shares if s.shares else None
    try:
        pb = justified_pb(roe, coe, g)
    except ValueError as exc:
        st.error(str(exc))
        return
    cols = st.columns(4)
    cols[0].metric("Justified P/B", mult(pb))
    cols[1].metric("Value per share", f"${pb * per_share_book:,.2f}" if per_share_book else "-",
                   f"{(pb * per_share_book / price - 1) * 100:+.0f}% vs price" if price and per_share_book else None)
    cur_pb = price / per_share_book if price and per_share_book else None
    cols[2].metric("Current P/B", mult(cur_pb))
    cols[3].metric("ROE priced in", pct(implied_roe(cur_pb, coe, g)) if cur_pb else "-")
    st.markdown("**Justified P/B: cost of equity (rows) × ROE (columns)**")
    st.dataframe(pb_grid(coe, g).map(lambda v: "-" if pd.isna(v) else f"{v:.2f}x"))


def _kpis(ticker, store, store_dir, ad: bool) -> None:
    if ad:
        st.markdown("Ad KPIs come from the quarterly **earnings release / slides** (not in SEC XBRL data). "
                    "For Meta: [investor.atmeta.com](https://investor.atmeta.com/). Ad revenue from the 10-K is shown on the tear sheet.")
    df = research_store.kpi_frame(store)
    edited = st.data_editor(df, num_rows="dynamic", hide_index=True, key=f"kpi_{ticker}", column_config={
        "period": st.column_config.TextColumn("period (e.g. 2026-Q2)"),
        "metric": st.column_config.SelectboxColumn("metric", options=research_store.AD_KPI_METRICS),
        "value": st.column_config.NumberColumn("value"), "source": st.column_config.TextColumn("source")})
    if st.button("💾 Save KPIs", key=f"save_kpi_{ticker}"):
        research_store.save(store_dir, ticker, {"kpis": research_store.kpi_rows(edited)})
        st.success("Saved.")
    if not df.empty:
        for metric, part in df.dropna(subset=["value"]).groupby("metric"):
            part = part.sort_values("period")
            fig = go.Figure(go.Scatter(x=part["period"], y=part["value"], mode="lines+markers", line=dict(color="#2a78d6")))
            fig.update_layout(title=metric, height=240, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, key=f"kpic_{ticker}_{metric}")


def _notes(ticker, store, store_dir) -> None:
    n = store.get("notes", {})
    with st.form(f"notes_{ticker}"):
        thesis = st.text_area("Investment thesis", n.get("thesis", ""), height=150)
        risks = st.text_area("Risks", n.get("risks", ""), height=120)
        catalysts = st.text_area("Catalysts / what to watch", n.get("catalysts", ""))
        val = st.text_area("Valuation notes", n.get("valuation", ""))
        if st.form_submit_button("💾 Save notes"):
            research_store.save(store_dir, ticker, {"notes": {"thesis": thesis, "risks": risks, "catalysts": catalysts, "valuation": val}})
            st.success("Saved.")
    if store.get("saved_at"):
        st.caption(f"Last saved {store['saved_at']}")


def _compare(cfg, ua, cache_dir, current) -> None:
    pool = list(dict.fromkeys([current] + [t for ts in cfg.coverage.values() for t in ts]))
    chosen = st.multiselect("Compare up to 3 companies", pool, default=pool[:3], max_selections=3, key="cmp")
    rows, roe, rev = {}, {}, {}
    for tk in chosen:
        try:
            comp = _company(tk, ua, cache_dir)
        except SecError as exc:
            st.warning(f"{tk}: {exc}")
            continue
        price = _prices(tk)[0]
        s = comp["snap"]
        bank = tk in cfg.coverage.get("banks", []) or comp["bank_sic"]
        t = add_bank_ratios(comp["table"]) if bank else add_ratios(comp["table"])
        m = multiples(price, s.shares, s.revenue, s.operating_income, s.net_income, s.fcf, s.eps, s.cash, s.debt)
        last = t.iloc[-1]
        rows[tk] = {
            "Type": "Bank" if bank else "Company", "Market cap": money(m["market_cap"]), "Revenue (TTM)": money(s.revenue),
            "Revenue CAGR 5y": pct(cagr(t["bank_revenue" if bank else "revenue"], 5)),
            "Operating margin": "-" if bank else pct(last.get("operating_margin")), "FCF margin": "-" if bank else pct(last.get("fcf_margin")),
            "ROIC": "-" if bank else pct(last.get("roic")), "ROE": pct(last.get("roe")), "ROTCE": pct(last.get("rotce")) if bank else "-",
            "Efficiency ratio": pct(last.get("efficiency_ratio")) if bank else "-", "P/E": mult(m["pe"]),
            "EV/EBIT": "-" if bank else mult(m["ev_ebit"]), "FCF yield": "-" if bank else pct(m["fcf_yield"]),
        }
        roe[tk] = t["roe"]
        r = t["bank_revenue" if bank else "revenue"].dropna()
        if len(r):
            rev[tk] = r / r.iloc[0] * 100
    if rows:
        st.dataframe(pd.DataFrame(rows))
        a, b = st.columns(2)
        a.plotly_chart(_line(rev, "Revenue, indexed (first year = 100)"), key="cmp_rev")
        b.plotly_chart(_line(roe, "Return on equity", True), key="cmp_roe")
