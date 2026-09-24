"""Research sources: web search (Google CSE, or OpenAI web_search fallback),
the Meta Ad Library API, and plain page fetching for grounding excerpts."""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Optional, Protocol
from urllib.parse import quote_plus

import httpx

from .llm import LLMError, OpenAIClient
from .models import Source

log = logging.getLogger(__name__)


class WebSearch(Protocol):
    name: str

    def search(self, query: str, n: int = 5) -> list[Source]: ...


class GoogleCSESearch:
    name = "google_cse"

    def __init__(self, api_key: str, cx: str, http: Optional[httpx.Client] = None):
        self.api_key, self.cx = api_key, cx
        self.http = http or httpx.Client()

    def search(self, query: str, n: int = 5) -> list[Source]:
        r = self.http.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": self.api_key, "cx": self.cx, "q": query, "num": min(n, 10), "dateRestrict": "m12"},
            timeout=30,
        )
        r.raise_for_status()
        return [
            Source(id="", title=it.get("title", ""), url=it.get("link", ""), snippet=it.get("snippet", ""))
            for it in r.json().get("items", [])[:n]
        ]


class OpenAIWebSearch:
    name = "openai_web_search"

    def __init__(self, client: OpenAIClient):
        self.client = client

    def search(self, query: str, n: int = 5) -> list[Source]:
        text, citations = self.client.web_search(
            f"Search the web for recent (last 12 months) sources on: {query}. "
            "Summarise what each source says, citing every source you use."
        )
        out = []
        for c in citations[:n]:
            out.append(Source(id="", title=c.get("title", ""), url=c["url"], snippet=c.get("snippet") or text[:400]))
        return out


class MetaAdLibrary:
    """Meta Ad Library API (graph.facebook.com/ads_archive).

    Commercial ads are only returned for EU-reached ads (DSA transparency), so the
    default countries are EU markets. The API's snapshot URLs embed the access token,
    so we store the public Ad Library permalink instead.
    """

    GRAPH = "https://graph.facebook.com/v21.0/ads_archive"

    def __init__(self, token: str, countries: list[str], http: Optional[httpx.Client] = None):
        self.token, self.countries = token, countries
        self.http = http or httpx.Client()

    def search(self, terms: str, n: int = 8) -> list[Source]:
        r = self.http.get(
            self.GRAPH,
            params={
                "access_token": self.token,
                "search_terms": terms,
                "ad_reached_countries": json.dumps(self.countries),
                "ad_active_status": "ACTIVE",
                "ad_type": "ALL",
                "fields": "id,page_name,ad_creative_bodies,ad_creative_link_titles,ad_delivery_start_time",
                "limit": n,
            },
            timeout=30,
        )
        r.raise_for_status()
        out = []
        for ad in r.json().get("data", [])[:n]:
            body = " | ".join((ad.get("ad_creative_bodies") or [])[:1] + (ad.get("ad_creative_link_titles") or [])[:1])
            out.append(Source(
                id="", kind="meta_ad_library",
                title=f"Meta Ad Library: {ad.get('page_name', 'unknown page')} (running since {ad.get('ad_delivery_start_time', '?')})",
                url=f"https://www.facebook.com/ads/library/?id={ad['id']}",
                snippet=body[:500],
            ))
        return out

    @staticmethod
    def manual_link(terms: str, country: str = "ALL") -> Source:
        url = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
               f"&country={country}&q={quote_plus(terms)}&search_type=keyword_unordered&media_type=image")
        return Source(id="", kind="meta_ad_library", title=f"Browse Meta Ad Library: \"{terms}\"", url=url)


_TAG_RE = re.compile(r"<[^>]+>")
_DROP_RE = re.compile(r"<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", re.S | re.I)


def fetch_excerpt(url: str, http: Optional[httpx.Client] = None, limit: int = 2500) -> str:
    """Fetch a page and return a plain-text excerpt ('' on any failure)."""
    try:
        r = (http or httpx.Client()).get(url, timeout=20, follow_redirects=True,
                                         headers={"User-Agent": "Mozilla/5.0 (VikeAdsResearch)"})
        if r.status_code >= 400 or "html" not in r.headers.get("content-type", ""):
            return ""
        text = html.unescape(_TAG_RE.sub(" ", _DROP_RE.sub(" ", r.text)))
        return re.sub(r"\s+", " ", text).strip()[:limit]
    except (httpx.HTTPError, LLMError) as e:
        log.debug("fetch failed for %s: %s", url, e)
        return ""
