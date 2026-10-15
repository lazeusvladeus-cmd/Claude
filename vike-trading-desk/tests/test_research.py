import pandas as pd
import pytest

from desk.edgar import revenue_breakdown, valid_user_agent
from desk.fundamentals import add_bank_ratios, add_ratios, annual_table, snapshot
from desk.valuation import DcfInputs, dcf, implied_growth, justified_pb, tornado


def fact(start, end, val, form="10-K", filed=None):
    d = {"end": end, "val": val, "form": form, "filed": filed or end}
    if start:
        d["start"] = start
    return d


def facts_for(tags):
    return {"entityName": "TEST", "facts": {"us-gaap": {t: {"units": {u: v}} for t, (u, v) in tags.items()}}}


def test_annual_table_ttm_and_ratios():
    years = range(2021, 2026)
    tags = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": ("USD", [fact(f"{y-1}-07-01", f"{y}-06-30", 100.0 * (1.1 ** (y - 2021))) for y in years]
                                                              + [fact("2025-07-01", "2025-09-30", 30.0, "10-Q", "2025-10-30"),
                                                                 fact("2024-07-01", "2024-09-30", 25.0, "10-Q", "2025-10-30")]),
        "OperatingIncomeLoss": ("USD", [fact(f"{y-1}-07-01", f"{y}-06-30", 40.0) for y in years]),
        "NetIncomeLoss": ("USD", [fact(f"{y-1}-07-01", f"{y}-06-30", 30.0) for y in years]),
        "NetCashProvidedByUsedInOperatingActivities": ("USD", [fact(f"{y-1}-07-01", f"{y}-06-30", 45.0) for y in years]),
        "PaymentsToAcquirePropertyPlantAndEquipment": ("USD", [fact(f"{y-1}-07-01", f"{y}-06-30", 10.0) for y in years]),
        "StockholdersEquity": ("USD", [fact(None, f"{y}-06-30", 200.0) for y in years]),
        "LongTermDebt": ("USD", [fact(None, f"{y}-06-30", 50.0) for y in years]),
        "CashAndCashEquivalentsAtCarryingValue": ("USD", [fact(None, f"{y}-06-30", 30.0) for y in years]),
    }
    facts = facts_for(tags)
    t = add_ratios(annual_table(facts))
    assert len(t) == 5 and t["revenue"].iloc[0] == 100.0
    assert t["fcf"].iloc[-1] == 35.0
    assert t["operating_margin"].iloc[0] == pytest.approx(0.4)
    assert t["roic"].iloc[-1] == pytest.approx(40 * 0.79 / 220)
    snap = snapshot(facts, annual_table(facts))
    assert snap.revenue == pytest.approx(100 * 1.1 ** 4 + 30 - 25)  # TTM = FY + YTD - prior YTD
    assert snap.debt == 50.0 and snap.cash == 30.0


def test_bank_ratios():
    t = pd.DataFrame({"revenue": [100.0, 110.0], "nii": [60.0, 65.0], "nonint_income": [40.0, 45.0], "nonint_expense": [55.0, 60.0],
                      "provision": [5.0, 6.0], "net_income": [30.0, 33.0], "ni_common": [28.0, 31.0], "loans": [1000.0, 1100.0],
                      "deposits": [1500.0, 1600.0], "equity": [300.0, 320.0], "preferred": [20.0, 20.0], "goodwill": [50.0, 50.0],
                      "intangibles": [10.0, 10.0], "assets": [2500.0, 2600.0], "net_charge_offs": [4.0, 5.0]},
                     index=pd.to_datetime(["2024-12-31", "2025-12-31"]))
    b = add_bank_ratios(t)
    assert b["efficiency_ratio"].iloc[-1] == pytest.approx(60 / 110)
    assert b["rotce"].iloc[-1] == pytest.approx(31 / ((220 + 240) / 2))
    assert b["loan_growth"].iloc[-1] == pytest.approx(0.1)


def test_dcf_and_sensitivity():
    inp = DcfInputs(revenue0=100, growth=0.0, terminal_growth=0.0, margin0=0.2, target_margin=0.2, discount_rate=0.1,
                    tax_rate=0.0, sales_to_capital=1.0, cash=10, debt=0, shares=1)
    res = dcf(inp)
    assert res.per_share == pytest.approx(20 / 0.1 + 10)  # zero growth = perpetuity of 20
    t = tornado(inp)
    assert set(t["assumption"]) >= {"Discount rate (WACC)", "Revenue growth (yrs 1-5)"}
    g = implied_growth(DcfInputs(100, 0.05, 0.02, 0.25, 0.25, 0.09, shares=1), price=300)
    assert g is not None
    assert justified_pb(0.15, 0.10, 0.03) == pytest.approx(12 / 7)
    with pytest.raises(ValueError):
        dcf(DcfInputs(100, 0.05, 0.10, 0.2, 0.2, 0.08))


def test_segment_breakdown_and_user_agent():
    xml = b"""<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:us-gaap="http://fasb.org/us-gaap/2025">
    <context id="c1"><entity><identifier>1</identifier><segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">us-gaap:AdvertisingMember</xbrldi:explicitMember></segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period></context>
    <us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax contextRef="c1" unitRef="usd">150000000000</us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax>
    </xbrl>"""
    df = revenue_breakdown(xml)
    assert df.iloc[0]["member"] == "Advertising" and df.iloc[0]["value"] == 150e9
    assert valid_user_agent("Vike Petrenko vike@gmail.com") and not valid_user_agent("vike")
