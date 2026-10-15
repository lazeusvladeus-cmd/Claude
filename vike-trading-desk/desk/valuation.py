"""Valuation: multiples, a simple DCF (Damodaran-style FCFF), sensitivity, reverse DCF, and justified P/B for banks."""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd


def multiples(price: float | None, shares: float | None, revenue: float | None, ebit: float | None,
              net_income: float | None, fcf: float | None, eps: float | None, cash: float | None,
              debt: float | None) -> dict:
    out = {"market_cap": None, "ev": None, "pe": None, "ev_ebit": None, "fcf_yield": None, "ev_sales": None}
    if not price or not shares:
        return out
    mcap = price * shares
    ev = mcap + (debt or 0) - (cash or 0)
    out["market_cap"], out["ev"] = mcap, ev
    if eps and eps > 0:
        out["pe"] = price / eps
    elif net_income and net_income > 0:
        out["pe"] = mcap / net_income
    if ebit and ebit > 0:
        out["ev_ebit"] = ev / ebit
    if fcf is not None:
        out["fcf_yield"] = fcf / mcap
    if revenue and revenue > 0:
        out["ev_sales"] = ev / revenue
    return out


@dataclass(frozen=True)
class DcfInputs:
    revenue0: float  # last 12 months revenue
    growth: float  # yearly revenue growth for years 1-5 (0.10 = 10%)
    terminal_growth: float  # growth forever after year 10
    margin0: float  # current operating (EBIT) margin
    target_margin: float  # operating margin reached in `years_to_target` years
    discount_rate: float  # cost of capital (WACC)
    tax_rate: float = 0.21
    sales_to_capital: float = 1.5  # revenue added per $1 reinvested
    years_to_target: int = 5
    cash: float = 0.0
    debt: float = 0.0
    shares: float = 1.0
    years: int = 10


@dataclass
class DcfResult:
    table: pd.DataFrame
    pv_cash_flows: float
    terminal_value: float
    pv_terminal: float
    firm_value: float
    equity_value: float
    per_share: float
    terminal_share: float  # share of value coming from the terminal value


def dcf(inp: DcfInputs) -> DcfResult:
    if inp.discount_rate <= inp.terminal_growth:
        raise ValueError("The discount rate must be higher than the terminal growth rate.")
    years = np.arange(1, inp.years + 1)
    growth = np.where(years <= 5, inp.growth,
                      inp.growth + (inp.terminal_growth - inp.growth) * (years - 5) / max(inp.years - 5, 1))
    revenue = inp.revenue0 * np.cumprod(1 + growth)
    steps = np.minimum(years / max(inp.years_to_target, 1), 1.0)
    margin = inp.margin0 + (inp.target_margin - inp.margin0) * steps
    ebit = revenue * margin
    nopat = ebit * (1 - inp.tax_rate)
    prev_rev = np.concatenate([[inp.revenue0], revenue[:-1]])
    reinvestment = (revenue - prev_rev) / inp.sales_to_capital
    fcff = nopat - reinvestment
    discount = (1 + inp.discount_rate) ** -years
    pv = fcff * discount

    # Terminal year: grow at terminal rate; reinvest g / r of NOPAT (return on new capital = cost of capital)
    nopat_next = revenue[-1] * (1 + inp.terminal_growth) * margin[-1] * (1 - inp.tax_rate)
    fcff_next = nopat_next * (1 - inp.terminal_growth / inp.discount_rate)
    tv = fcff_next / (inp.discount_rate - inp.terminal_growth)
    pv_tv = tv * discount[-1]
    firm = pv.sum() + pv_tv
    equity = firm + inp.cash - inp.debt
    table = pd.DataFrame({
        "year": years, "growth": growth, "revenue": revenue, "operating_margin": margin, "ebit": ebit,
        "nopat": nopat, "reinvestment": reinvestment, "fcff": fcff, "discount_factor": discount, "pv_fcff": pv,
    })
    return DcfResult(table, float(pv.sum()), float(tv), float(pv_tv), float(firm), float(equity),
                     float(equity / inp.shares), float(pv_tv / firm) if firm else float("nan"))


SENSITIVITY = [
    ("growth", "Revenue growth (yrs 1-5)", 0.05),
    ("target_margin", "Target operating margin", 0.05),
    ("discount_rate", "Discount rate (WACC)", 0.01),
    ("terminal_growth", "Terminal growth", 0.01),
    ("sales_to_capital", "Sales-to-capital", 0.5),
    ("tax_rate", "Tax rate", 0.05),
]


def tornado(inp: DcfInputs) -> pd.DataFrame:
    """Value per share when each assumption moves down / up by a fixed step, others unchanged."""
    base = dcf(inp).per_share
    rows = []
    for name, label, step in SENSITIVITY:
        values = []
        for sign in (-1, 1):
            changed = replace(inp, **{name: getattr(inp, name) + sign * step})
            try:
                values.append(dcf(changed).per_share if changed.sales_to_capital > 0 else np.nan)
            except ValueError:
                values.append(np.nan)
        rows.append({"assumption": label, "step": step, "low": values[0], "high": values[1],
                     "range": abs(values[1] - values[0]), "base": base})
    return pd.DataFrame(rows).sort_values("range", ascending=False).reset_index(drop=True)


def grid(inp: DcfInputs, discount_steps=(-0.02, -0.01, 0, 0.01, 0.02), growth_steps=(-0.01, -0.005, 0, 0.005, 0.01)) -> pd.DataFrame:
    """Value per share for discount rate (rows) × terminal growth (columns)."""
    data = {}
    for g in growth_steps:
        col = {}
        for d in discount_steps:
            changed = replace(inp, discount_rate=inp.discount_rate + d, terminal_growth=inp.terminal_growth + g)
            try:
                col[f"{changed.discount_rate:.1%}"] = dcf(changed).per_share
            except ValueError:
                col[f"{changed.discount_rate:.1%}"] = np.nan
        data[f"g {inp.terminal_growth + g:.1%}"] = col
    return pd.DataFrame(data)


def implied_growth(inp: DcfInputs, price: float, low: float = -0.30, high: float = 0.80) -> float | None:
    """Reverse DCF: the yrs 1-5 growth rate at which the DCF value equals today's price."""
    def gap(g: float) -> float:
        return dcf(replace(inp, growth=g)).per_share - price

    try:
        f_low, f_high = gap(low), gap(high)
    except ValueError:
        return None
    if f_low * f_high > 0:
        return None
    for _ in range(80):
        mid = (low + high) / 2
        f_mid = gap(mid)
        if abs(f_mid) < 1e-6:
            break
        if f_low * f_mid <= 0:
            high = mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2


# ---------------------------------------------------------------- banks


def justified_pb(roe: float, cost_of_equity: float, growth: float) -> float:
    """Gordon-growth P/B: (ROE - g) / (r - g). A bank earning exactly its cost of equity is worth 1x book."""
    if cost_of_equity <= growth:
        raise ValueError("The cost of equity must be higher than the growth rate.")
    return (roe - growth) / (cost_of_equity - growth)


def implied_roe(pb: float, cost_of_equity: float, growth: float) -> float:
    """The ROE the market is pricing in at today's P/B."""
    return growth + pb * (cost_of_equity - growth)


def pb_grid(cost_of_equity: float, growth: float, roes=(0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20),
            costs=(-0.02, -0.01, 0, 0.01, 0.02)) -> pd.DataFrame:
    data = {}
    for r in roes:
        data[f"ROE {r:.0%}"] = {f"{cost_of_equity + c:.1%}": (justified_pb(r, cost_of_equity + c, growth)
                                                            if cost_of_equity + c > growth else np.nan) for c in costs}
    return pd.DataFrame(data)
