"""Cross-checking for DeepSeek output.

Rule: nothing DeepSeek produces is surfaced as a research finding or used as an ad
claim unless a *second*, independent source supports it — the OpenAI model judging
the claim against a fresh web search. DeepSeek is never its own judge.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .llm import ChatClient, LLMError
from .models import Source
from .search import WebSearch

log = logging.getLogger(__name__)


@dataclass
class Verdict:
    supported: bool
    method: str
    note: str = ""
    source_urls: list[str] = field(default_factory=list)


JUDGE_SYSTEM = (
    "You are a strict fact-checker for an advertising agency. Decide whether the CLAIM is "
    "supported by the EVIDENCE. Only answer supported=true if the evidence directly supports "
    "the claim's substance (numbers must match). Absence of evidence means supported=false. "
    'Return JSON: {"supported": bool, "note": "<one sentence>", "supporting_urls": ["..."]}'
)


class CrossChecker:
    def __init__(self, judge: Optional[ChatClient], web: Optional[WebSearch]):
        if judge is not None and judge.name == "deepseek":
            raise ValueError("DeepSeek cannot cross-check its own output")
        self.judge = judge
        self.web = web

    @property
    def available(self) -> bool:
        return self.judge is not None

    def check(self, claim: str, context: list[Source] | None = None) -> Verdict:
        if self.judge is None:
            return Verdict(False, "none", "no independent judge configured (OPENAI_API_KEY missing)")
        evidence: list[Source] = []
        fresh: list[Source] = []
        if self.web is not None:
            try:
                fresh = self.web.search(claim, n=5)
            except Exception as e:  # network/API failures just mean less evidence
                log.warning("fresh search failed during cross-check: %s", e)
        evidence = fresh + list(context or [])
        if not evidence:
            return Verdict(False, "none", "no fresh web search results to check against")
        pack = "\n".join(f"- {s.title} <{s.url}>: {s.snippet[:600]}" for s in evidence)
        try:
            out = self.judge.json(JUDGE_SYSTEM, f"CLAIM: {claim}\n\nEVIDENCE:\n{pack}")
        except LLMError as e:
            return Verdict(False, "error", f"judge failed: {e}")
        # Evidence is only ever our own search results (fresh or previously gathered), never text
        # DeepSeek wrote; the judge must point at one of those URLs for the claim to count.
        known = {s.url for s in evidence}
        urls = [u for u in out.get("supporting_urls", []) if u in known]
        supported = bool(out.get("supported")) and bool(urls)
        method = f"{self.judge.name} judge + " + (self.web.name if self.web else "cited sources")
        return Verdict(supported, method, str(out.get("note", ""))[:300], urls)
