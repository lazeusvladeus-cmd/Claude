"""Turn SEC "company facts" (XBRL) into clean annual tables, TTM figures and ratios.

Companies use different XBRL tags for the same thing and change them over time, so every
metric has a list of fallback tags. Annual values come from 10-K filings (latest filing wins,
so restatements are respected); TTM = last fiscal year + this year-to-date - last year-to-date.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT"}
QUARTER_FORMS = {"10-Q", "10-Q/A"}

TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "income_tax": ["IncomeTaxExpenseBenefit"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "dividends": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "eps_diluted": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    # balance sheet (instants)
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "short_investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "lt_debt_total": ["LongTermDebt"],
    "lt_debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "lt_debt_current": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "short_debt": ["ShortTermBorrowings", "CommercialPaper", "DebtCurrent"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "assets": ["Assets"],
    "shares_outstanding": ["CommonStockSharesOutstanding"],
    # banks
    "nii": ["InterestIncomeExpenseNet", "InterestIncomeExpenseAfterProvisionForLoanLoss"],
    "nonint_income": ["NoninterestIncome"],
    "nonint_expense": ["NoninterestExpense"],
    "provision": ["ProvisionForLoanLeaseAndOtherLosses", "ProvisionForLoanAndLeaseLosses", "ProvisionForCreditLosses",
                  "FinancingReceivableCreditLossExpenseReversal", "CreditLossExpenseReversal"],
    "ni_common": ["NetIncomeLossAvailableToCommonStockholdersBasic"],
    "loans": ["LoansAndLeasesReceivableNetReportedAmount", "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss",
              "LoansAndLeasesReceivableNetOfDeferredIncome", "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss"],
    "deposits": ["Deposits"],
    "preferred": ["PreferredStockValue", "PreferredStockValueOutstanding"],
    "goodwill": ["Goodwill"],
    "intangibles": ["IntangibleAssetsNetExcludingGoodwill", "OtherIntangibleAssetsNet", "FiniteLivedIntangibleAssetsNet"],
    "net_charge_offs": ["FinancingReceivableAllowanceForCreditLossesWriteOffsNet", "AllowanceForLoanAndLeaseLossesWriteOffsNet"],
    "cet1": ["CommonEquityTierOneCapitalRatio"],
}
INSTANT = {"cash", "short_investments", "lt_debt_total", "lt_debt_noncurrent", "lt_debt_current", "short_debt", "equity",
           "assets", "shares_outstanding", "loans", "deposits", "preferred", "goodwill", "intangibles", "cet1"}
UNITS = {"eps_diluted": "USD/shares", "shares_diluted": "shares", "shares_outstanding": "shares", "cet1": "pure"}
TAKE_MAX = {"revenue"}  # several revenue tags can exist; the total is the largest


def _entries(facts: dict, tag: str, unit: str) -> list[dict]:
    for taxonomy in ("us-gaap", "dei", "ifrs-full"):
        node = facts.get("facts", {}).get(taxonomy, {}).get(tag)
        if node:
            return node.get("units", {}).get(unit, [])
    return []


def _frame(entries: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(entries)
    if df.empty:
        return df
    for col in ("start", "end", "filed"):
        if col in df:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    if "start" not in df:
        df["start"] = pd.NaT
    df["days"] = (df["end"] - df["start"]).dt.days
    return df


def _annual_one(facts: dict, tag: str, unit: str, instant: bool) -> pd.Series:
    df = _frame(_entries(facts, tag, unit))
    if df.empty:
        return pd.Series(dtype=float)
    df = df[df["form"].isin(ANNUAL_FORMS)]
    df = df[df["start"].isna()] if instant else df[df["days"].between(330, 380)]
    if df.empty:
        return pd.Series(dtype=float)
    df = df.sort_values("filed").drop_duplicates("end", keep="last")
    return df.set_index("end")["val"].astype(float).sort_index()


def annual_series(facts: dict, metric: str) -> pd.Series:
    """One value per fiscal-year end for `metric`, combining its fallback tags."""
    unit = UNITS.get(metric, "USD")
    instant = metric in INSTANT
    parts = [s for s in (_annual_one(facts, t, unit, instant) for t in TAGS[metric]) if not s.empty]
    if not parts:
        return pd.Series(dtype=float, name=metric)
    if metric in TAKE_MAX:
        out = pd.concat(parts, axis=1).max(axis=1)
    else:
        out = parts[0]
        for extra in parts[1:]:
            out = out.combine_first(extra)
    return out.sort_index().rename(metric)


def _align(series: pd.Series, year_ends: pd.DatetimeIndex, tolerance_days: int = 10) -> pd.Series:
    """Match balance-sheet dates to the fiscal-year ends of the income statement."""
    out = pd.Series(np.nan, index=year_ends, dtype=float)
    for end in year_ends:
        close = series[(series.index >= end - pd.Timedelta(days=tolerance_days)) & (series.index <= end + pd.Timedelta(days=tolerance_days))]
        if not close.empty:
            out[end] = close.iloc[-1]
    return out


def annual_table(facts: dict, years: int = 10) -> pd.DataFrame:
    """Last `years` fiscal years, one row each, raw values in dollars / shares."""
    anchors = [annual_series(facts, m) for m in ("revenue", "net_income", "nii")]
    anchors = [a for a in anchors if not a.empty]
    if not anchors:
        return pd.DataFrame()
    year_ends = pd.DatetimeIndex(sorted(set().union(*[a.index for a in anchors])))[-years:]
    table = pd.DataFrame(index=year_ends)
    for metric in TAGS:
        s = annual_series(facts, metric)
        if s.empty:
            table[metric] = np.nan
        else:
            table[metric] = _align(s, year_ends) if metric in INSTANT else s.reindex(year_ends)
    table.index.name = "fiscal_year_end"
    return table


def add_ratios(t: pd.DataFrame) -> pd.DataFrame:
    """Margins, FCF, ROIC, debt and growth for an industrial / tech company."""
    t = t.copy()
    rev = t["revenue"]
    gross = t["gross_profit"].fillna(rev - t["cost_of_revenue"])
    t["gross_profit"] = gross
    t["fcf"] = t["ocf"] - t["capex"].fillna(0)
    lt_debt = t["lt_debt_total"].fillna(t["lt_debt_noncurrent"].fillna(0) + t["lt_debt_current"].fillna(0))
    t["total_debt"] = lt_debt + t["short_debt"].fillna(0)
    t["cash_total"] = t["cash"].fillna(0) + t["short_investments"].fillna(0)
    t["net_debt"] = t["total_debt"] - t["cash_total"]
    t["revenue_growth"] = rev.pct_change(fill_method=None)
    t["gross_margin"] = gross / rev
    t["operating_margin"] = t["operating_income"] / rev
    t["net_margin"] = t["net_income"] / rev
    t["fcf_margin"] = t["fcf"] / rev
    tax_rate = (t["income_tax"] / t["pretax_income"]).where(t["pretax_income"] > 0)
    t["tax_rate"] = tax_rate.clip(0, 0.40).fillna(0.21)
    t["nopat"] = t["operating_income"] * (1 - t["tax_rate"])
    invested = (t["equity"] + t["total_debt"] - t["cash_total"]).where(lambda s: s > 0)
    avg_invested = (invested + invested.shift(1)) / 2
    t["invested_capital"] = invested
    t["roic"] = t["nopat"] / avg_invested.fillna(invested)
    avg_equity = (t["equity"] + t["equity"].shift(1)) / 2
    t["roe"] = t["net_income"] / avg_equity.fillna(t["equity"]).where(lambda s: s > 0)
    return t


def add_bank_ratios(t: pd.DataFrame) -> pd.DataFrame:
    """Bank metrics: DCF doesn't fit banks, so we look at returns on equity, costs, credit and capital."""
    t = t.copy()
    t["bank_revenue"] = t["revenue"].fillna(t["nii"] + t["nonint_income"])
    common_equity = t["equity"] - t["preferred"].fillna(0)
    tce = common_equity - t["goodwill"].fillna(0) - t["intangibles"].fillna(0)
    t["common_equity"] = common_equity
    t["tangible_common_equity"] = tce
    ni_common = t["ni_common"].fillna(t["net_income"])
    t["ni_common"] = ni_common

    def avg(s: pd.Series) -> pd.Series:
        return ((s + s.shift(1)) / 2).fillna(s)

    t["roe"] = ni_common / avg(common_equity)
    t["rotce"] = ni_common / avg(tce)
    t["efficiency_ratio"] = t["nonint_expense"] / t["bank_revenue"]
    t["nii_to_avg_assets"] = t["nii"] / avg(t["assets"])
    t["loan_growth"] = t["loans"].pct_change(fill_method=None)
    t["deposit_growth"] = t["deposits"].pct_change(fill_method=None)
    t["provision_to_loans"] = t["provision"] / avg(t["loans"])
    t["nco_ratio"] = t["net_charge_offs"] / avg(t["loans"])
    t["revenue_growth"] = t["bank_revenue"].pct_change(fill_method=None)
    return t


# ---------------------------------------------------------------- TTM and latest values


def _quarterly_ytd(facts: dict, tag: str, unit: str) -> pd.DataFrame:
    df = _frame(_entries(facts, tag, unit))
    if df.empty:
        return df
    df = df[df["form"].isin(QUARTER_FORMS | ANNUAL_FORMS) & df["start"].notna()]
    return df.sort_values("filed").drop_duplicates(["start", "end"], keep="last")


def ttm_value(facts: dict, metric: str, annual: pd.Series) -> tuple[float | None, str]:
    """Trailing twelve months for a flow metric. Falls back to the last fiscal year."""
    if annual.dropna().empty:
        return None, ""
    fy_end = annual.dropna().index[-1]
    fy_value = float(annual.dropna().iloc[-1])
    unit = UNITS.get(metric, "USD")
    for tag in TAGS[metric]:
        df = _quarterly_ytd(facts, tag, unit)
        if df.empty:
            continue
        ytd = df[(df["start"] - fy_end).dt.days.between(0, 10) & (df["end"] > fy_end) & (df["days"] < 330)]
        if ytd.empty:
            continue
        cur = ytd.sort_values("end").iloc[-1]
        prior_end = cur["end"] - pd.DateOffset(years=1)
        prior = df[((df["end"] - prior_end).dt.days.abs() <= 10) & ((df["days"] - cur["days"]).abs() <= 10)]
        if prior.empty:
            continue
        value = fy_value + float(cur["val"]) - float(prior.iloc[-1]["val"])
        return value, f"TTM to {cur['end']:%d %b %Y}"
    return fy_value, f"fiscal year to {fy_end:%d %b %Y}"


def latest_instant(facts: dict, metric: str) -> tuple[float | None, pd.Timestamp | None]:
    unit = UNITS.get(metric, "USD")
    best = None
    for tag in TAGS[metric]:
        df = _frame(_entries(facts, tag, unit))
        if df.empty:
            continue
        df = df[df["start"].isna() & df["form"].isin(QUARTER_FORMS | ANNUAL_FORMS)]
        if df.empty:
            continue
        row = df.sort_values(["end", "filed"]).iloc[-1]
        if best is None or row["end"] > best[1]:
            best = (float(row["val"]), row["end"])
    return best if best else (None, None)


def shares_outstanding(facts: dict) -> tuple[float | None, pd.Timestamp | None]:
    """Latest share count from the filing cover page (dei), else the balance sheet."""
    df = _frame(_entries(facts, "EntityCommonStockSharesOutstanding", "shares"))
    if not df.empty:
        row = df.sort_values(["end", "filed"]).iloc[-1]
        cover = (float(row["val"]), row["end"])
    else:
        cover = (None, None)
    balance = latest_instant(facts, "shares_outstanding")
    if cover[0] and (balance[1] is None or cover[1] >= balance[1]):
        return cover
    return balance if balance[0] else cover


@dataclass
class Snapshot:
    """The 'now' numbers used for multiples: TTM flows + latest balance sheet."""

    revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    fcf: float | None = None
    eps: float | None = None
    cash: float | None = None
    debt: float | None = None
    shares: float | None = None
    equity: float | None = None
    period_note: str = ""
    extra: dict = field(default_factory=dict)


def snapshot(facts: dict, table: pd.DataFrame) -> Snapshot:
    snap = Snapshot()
    snap.revenue, note = ttm_value(facts, "revenue", table["revenue"])
    snap.operating_income, _ = ttm_value(facts, "operating_income", table["operating_income"])
    snap.net_income, _ = ttm_value(facts, "net_income", table["net_income"])
    ocf, _ = ttm_value(facts, "ocf", table["ocf"])
    capex, _ = ttm_value(facts, "capex", table["capex"])
    snap.fcf = ocf - (capex or 0) if ocf is not None else None
    snap.eps, _ = ttm_value(facts, "eps_diluted", table["eps_diluted"])
    snap.period_note = note
    cash = sum(v for v in (latest_instant(facts, "cash")[0], latest_instant(facts, "short_investments")[0]) if v)
    lt_total = latest_instant(facts, "lt_debt_total")[0]
    lt = lt_total if lt_total is not None else sum(
        v for v in (latest_instant(facts, "lt_debt_noncurrent")[0], latest_instant(facts, "lt_debt_current")[0]) if v)
    snap.cash = cash
    snap.debt = (lt or 0) + (latest_instant(facts, "short_debt")[0] or 0)
    snap.equity = latest_instant(facts, "equity")[0]
    snap.shares, _ = shares_outstanding(facts)
    return snap


def cagr(series: pd.Series, years: int) -> float | None:
    s = series.dropna()
    if len(s) <= years or s.iloc[-1 - years] <= 0 or s.iloc[-1] <= 0:
        return None
    return (s.iloc[-1] / s.iloc[-1 - years]) ** (1 / years) - 1
