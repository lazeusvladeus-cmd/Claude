"""SEC EDGAR client: free company fundamentals (XBRL "company facts") and filings.

The SEC requires every program to send a User-Agent with a name and email address, and
to stay under 10 requests per second. Everything downloaded is cached in data/cache/sec,
so normally the app asks the SEC only once a day per company.
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

import pandas as pd

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"

BANK_SIC = {"6021", "6022", "6029", "6035", "6036", "6111", "6712"}  # commercial banks, savings institutions, bank holding cos.
REVENUE_TAGS = {
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
}


class SecError(Exception):
    """A problem talking to the SEC, phrased so the user knows what to do."""


def _default_get(url: str, headers: dict):
    import requests

    return requests.get(url, headers=headers, timeout=30)


def valid_user_agent(text: str) -> bool:
    text = (text or "").strip()
    return bool(re.search(r"\S+@\S+\.\w+", text)) and len(text.split()) >= 2 and "example.com" not in text


class SecClient:
    def __init__(self, user_agent: str, cache_dir: Path, http_get: Callable = _default_get, pause: float = 0.15):
        if not valid_user_agent(user_agent):
            raise SecError(
                'The SEC requires your name and email to use its free data (for example "Vike Petrenko vike@gmail.com"). '
                "Enter it in the box above."
            )
        self.user_agent = user_agent.strip()
        self.cache_dir = Path(cache_dir)
        self.http_get = http_get
        self.pause = pause
        self._last_call = 0.0

    # ------------------------------------------------------------ low level
    def _fetch(self, url: str, cache_name: str, max_age_hours: float) -> bytes:
        path = self.cache_dir / cache_name
        if path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600:
            return path.read_bytes()
        wait = self.pause - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()
        try:
            response = self.http_get(url, {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"})
        except Exception as exc:
            if path.exists():
                return path.read_bytes()
            raise SecError(f"Couldn't reach the SEC ({type(exc).__name__}). Check your internet connection.") from None
        status = getattr(response, "status_code", 0)
        if status == 200:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
            return response.content
        if path.exists():
            return path.read_bytes()
        if status == 403:
            raise SecError("The SEC refused the request (403). Make sure your name and email are filled in correctly.")
        if status == 404:
            raise SecError(f"Not found at the SEC: {url}")
        raise SecError(f"The SEC answered with an error (HTTP {status}). Try again in a minute.")

    def _json(self, url: str, cache_name: str, max_age_hours: float) -> dict:
        try:
            return json.loads(self._fetch(url, cache_name, max_age_hours))
        except ValueError:
            raise SecError("The SEC sent something that isn't valid data. Try again later.") from None

    # ------------------------------------------------------------ public
    def cik_for(self, ticker: str) -> tuple[int, str]:
        data = self._json(TICKERS_URL, "company_tickers.json", 24 * 7)
        wanted = ticker.strip().upper().replace(".", "-")
        for row in data.values():
            if str(row.get("ticker", "")).upper() == wanted:
                return int(row["cik_str"]), str(row.get("title", ticker))
        raise SecError(f"{ticker} isn't in the SEC's list of companies (only US-listed companies that file with the SEC).")

    def company_facts(self, cik: int) -> dict:
        return self._json(FACTS_URL.format(cik=cik), f"facts_{cik}.json", 24)

    def submissions(self, cik: int) -> dict:
        return self._json(SUBMISSIONS_URL.format(cik=cik), f"submissions_{cik}.json", 24)

    def latest_annual_instance(self, cik: int) -> tuple[bytes, str] | None:
        """The XBRL data file of the latest 10-K (for segment / product revenue). None if not found."""
        recent = self.submissions(cik).get("filings", {}).get("recent", {})
        for form, acc, doc in zip(recent.get("form", []), recent.get("accessionNumber", []), recent.get("primaryDocument", [])):
            if form != "10-K" or not doc.endswith(".htm"):
                continue
            acc_nodash = acc.replace("-", "")
            name = doc[:-4] + "_htm.xml"
            url = ARCHIVE_URL.format(cik=cik, acc=acc_nodash, name=name)
            try:
                return self._fetch(url, f"instance_{cik}_{acc_nodash}.xml", 24 * 90), acc
            except SecError:
                return None
        return None


def is_bank(submissions: dict) -> bool:
    return str(submissions.get("sic", "")) in BANK_SIC


# ---------------------------------------------------------------- 10-K revenue breakdown


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _member_label(member: str) -> str:
    name = member.split(":")[-1]
    name = re.sub(r"Member$", "", name)
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)


def revenue_breakdown(instance: bytes) -> pd.DataFrame:
    """Annual revenue split by one dimension (segment, product/service, geography) from a 10-K XBRL file."""
    columns = ["axis", "member", "start", "end", "value"]
    try:
        root = ET.fromstring(instance)
    except ET.ParseError:
        return pd.DataFrame(columns=columns)
    contexts: dict[str, tuple[str, str, str, str]] = {}
    for ctx in root.iter():
        if _local(ctx.tag) != "context":
            continue
        members = [m for m in ctx.iter() if _local(m.tag) == "explicitMember"]
        if len(members) != 1:
            continue
        start = end = None
        for el in ctx.iter():
            if _local(el.tag) == "startDate":
                start = (el.text or "").strip()
            elif _local(el.tag) == "endDate":
                end = (el.text or "").strip()
        if not start or not end:
            continue
        try:
            days = (pd.Timestamp(end) - pd.Timestamp(start)).days
        except ValueError:
            continue
        if not 330 <= days <= 380:
            continue
        axis = re.sub(r"Axis$", "", members[0].get("dimension", "").split(":")[-1])
        contexts[ctx.get("id")] = (axis, _member_label((members[0].text or "").strip()), start, end)

    rows, seen = [], set()
    for el in root.iter():
        if _local(el.tag) not in REVENUE_TAGS or el.get("contextRef") not in contexts:
            continue
        axis, member, start, end = contexts[el.get("contextRef")]
        key = (axis, member, start, end)
        if key in seen:
            continue
        try:
            value = float((el.text or "").strip())
        except ValueError:
            continue
        seen.add(key)
        rows.append({"axis": axis, "member": member, "start": pd.Timestamp(start), "end": pd.Timestamp(end), "value": value})
    return pd.DataFrame(rows, columns=columns)
