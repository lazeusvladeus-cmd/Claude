"""Research Agent — current ad creative trends, with sources.

Pipeline:
  1. Build queries (topic x tracked trend themes).
  2. Gather sources: web search (Google CSE or OpenAI web_search), Meta Ad Library API,
     plus manual Ad Library browse links. Optionally fetch page excerpts.
  3. OpenAI synthesises findings that must cite source IDs from the evidence pack.
  4. DeepSeek (optional) synthesises independently; every DeepSeek finding is
     cross-checked (OpenAI judge + fresh web search). Failures land in
     `unverified_leads`, are labelled as such, and never feed ideation.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Optional

from ..brand import Brand
from ..llm import ChatClient, LLMError
from ..models import Finding, ResearchReport, Source, VisualFormat
from ..search import MetaAdLibrary, WebSearch
from ..store import new_id
from ..verification import CrossChecker

log = logging.getLogger(__name__)

TREND_THEMES: dict[str, dict] = {
    "one_star_review": {
        "label": "1-star / negative-review ad format",
        "queries": ["1-star review ad format Meta ads trend", "negative review ads creative performance"],
        "ad_library_terms": "worst review",
    },
    "fake_dm": {
        "label": "Fake DM / iMessage screenshot ads",
        "queries": ["iMessage screenshot ad creative trend", "text message DM style static ads Meta"],
        "ad_library_terms": "text message",
    },
    "dashboard": {
        "label": "Dashboard / before-after results screenshots",
        "queries": ["Ads Manager screenshot ad creative results proof", "before after dashboard screenshot ads agency"],
        "ad_library_terms": "ads manager results",
    },
    "anti_ad": {
        "label": "Anti-ad / pattern-interrupt formats",
        "queries": ["anti-ad creative pattern interrupt Meta ads", "ugly ads outperform polished ads"],
        "ad_library_terms": "this is an ad",
    },
    "authenticity": {
        "label": "Authenticity-over-polish shift",
        "queries": ["lo-fi authentic ad creative outperforming polished 2026", "Meta Andromeda creative diversity authenticity"],
        "ad_library_terms": "honest",
    },
}

SYNTH_SYSTEM = (
    "You are the research analyst for a Meta/Google ads agency. From the EVIDENCE PACK only, extract "
    "current ad-creative trend findings. Rules: every finding must cite the IDs of the sources that "
    "support it (e.g. S3); never invent sources, numbers or quotes; if the evidence is thin, say so in "
    "the summary; prefer specific, actionable observations (what the creative looks like, why it works, "
    "who it works for). Map each finding to the visual formats it informs: dashboard, review_card, "
    'dm_screenshot (or none). Return JSON: {"findings": [{"trend": "...", "summary": "2-4 sentences", '
    '"evidence": "the concrete observation/data point", "formats": ["review_card"], "source_ids": ["S1"]}]}'
)


class ResearchAgent:
    def __init__(self, brand: Brand, *, openai: Optional[ChatClient], deepseek: Optional[ChatClient],
                 web: Optional[WebSearch], ad_library: Optional[MetaAdLibrary], checker: CrossChecker,
                 fetcher: Optional[Callable[[str], str]] = None, countries: list[str] | None = None):
        self.brand, self.openai, self.deepseek = brand, openai, deepseek
        self.web, self.ad_library, self.checker, self.fetcher = web, ad_library, checker, fetcher
        self.countries = countries or ["IE", "NL"]

    # ------------------------------------------------------------------ gather
    def _queries(self, topic: str, themes: list[str]) -> list[str]:
        year = datetime.now(timezone.utc).year
        qs = []
        for t in themes:
            for q in TREND_THEMES[t]["queries"]:
                qs.append(f"{q} {year}" + (f" {topic}" if topic else ""))
        if topic:
            qs.insert(0, f"{topic} ad creative trends {year}")
        return qs

    def gather(self, topic: str, themes: list[str], per_query: int = 4) -> tuple[list[Source], list[Source], list[str]]:
        notes: list[str] = []
        sources: list[Source] = []
        if self.web is None:
            notes.append("No web search configured (set GOOGLE_CSE_* or OPENAI_API_KEY).")
        else:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda q: self._safe_search(q, per_query, notes), self._queries(topic, themes)))
            for batch in results:
                sources.extend(batch)
        if self.ad_library is not None:
            for t in themes:
                terms = TREND_THEMES[t]["ad_library_terms"]
                try:
                    sources.extend(self.ad_library.search(terms, n=5))
                except Exception as e:
                    notes.append(f"Meta Ad Library API query '{terms}' failed: {e}")
        manual = [MetaAdLibrary.manual_link(TREND_THEMES[t]["ad_library_terms"], c)
                  for t in themes for c in self.countries[:1]]

        # de-duplicate by URL, assign stable IDs
        uniq: dict[str, Source] = {}
        for s in sources:
            if s.url and s.url not in uniq:
                uniq[s.url] = s
        out = list(uniq.values())[:40]
        if self.fetcher:
            with ThreadPoolExecutor(max_workers=6) as pool:
                excerpts = list(pool.map(lambda s: self.fetcher(s.url) if s.kind == "web" else "", out[:15]))
            for s, ex in zip(out, excerpts):
                if ex:
                    s.snippet = (s.snippet + " … " + ex)[:2500]
        for i, s in enumerate(out, 1):
            s.id = f"S{i}"
        for i, s in enumerate(manual, 1):
            s.id = f"M{i}"
        return out, manual, notes

    def _safe_search(self, q: str, n: int, notes: list[str]) -> list[Source]:
        try:
            return self.web.search(q, n)
        except Exception as e:
            notes.append(f"search failed for '{q}': {e}")
            return []

    # ------------------------------------------------------------------ synthesise
    @staticmethod
    def _pack(sources: list[Source]) -> str:
        return "\n\n".join(f"[{s.id}] ({s.kind}) {s.title}\nURL: {s.url}\n{s.snippet[:1500]}" for s in sources)

    def _synthesise(self, client: ChatClient, topic: str, themes: list[str], sources: list[Source]) -> list[Finding]:
        labels = "; ".join(TREND_THEMES[t]["label"] for t in themes)
        user = (f"TOPIC: {topic or 'current ad creative trends for a Meta/Google ads agency'}\n"
                f"THEMES TO COVER: {labels}\n\nEVIDENCE PACK:\n{self._pack(sources)}")
        data = client.json(SYNTH_SYSTEM, user)
        valid_ids = {s.id for s in sources}
        findings = []
        for f in data.get("findings", []):
            ids = [i for i in f.get("source_ids", []) if i in valid_ids]
            if not ids or not f.get("trend") or not f.get("summary"):
                continue  # no sourceless findings, ever
            fmts = [VisualFormat(x) for x in f.get("formats", []) if x in {v.value for v in VisualFormat}]
            findings.append(Finding(trend=f["trend"], summary=f["summary"], evidence=f.get("evidence", ""),
                                    formats=fmts, source_ids=ids, providers=[client.name]))
        return findings

    def run(self, topic: str = "", themes: list[str] | None = None) -> ResearchReport:
        themes = themes or list(TREND_THEMES)
        unknown = [t for t in themes if t not in TREND_THEMES]
        if unknown:
            raise ValueError(f"unknown themes {unknown}; choose from {list(TREND_THEMES)}")
        report = ResearchReport(id=new_id("r"), topic=topic or "Ad creative trends")
        sources, manual, notes = self.gather(topic, themes)
        report.sources, report.manual_links, report.notes = sources, manual, notes
        if not sources:
            report.notes.append("No sources gathered — nothing to synthesise.")
            return report

        if self.openai is not None:
            try:
                for f in self._synthesise(self.openai, topic, themes, sources):
                    f.verification, f.verification_note = "sourced", "grounded in cited sources"
                    report.findings.append(f)
            except LLMError as e:
                report.notes.append(f"OpenAI synthesis failed: {e}")

        if self.deepseek is not None:
            try:
                ds_findings = self._synthesise(self.deepseek, topic, themes, sources)
            except LLMError as e:
                report.notes.append(f"DeepSeek synthesis failed: {e}")
                ds_findings = []
            for f in ds_findings:
                cited = [s for s in sources if s.id in f.source_ids]
                verdict = self.checker.check(f"{f.trend}: {f.summary} {f.evidence}".strip(), cited)
                if verdict.supported:
                    f.verification = "cross_checked"
                    f.providers = ["deepseek", f"verified by {verdict.method}"]
                    f.verification_note = verdict.note
                    report.findings.append(f)
                else:
                    f.verification = "unverified"
                    f.verification_note = f"DeepSeek-only, not confirmed by a second source ({verdict.note})"
                    report.unverified_leads.append(f)
        if self.openai is None and self.deepseek is None:
            report.notes.append("No reasoning model configured — sources only, no findings.")
        return report
