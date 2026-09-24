"""Ideation Agent — research findings + brand context -> 4-part ad concepts with variants.

Quality gates applied to every variant, in order:
  1. schema parse (pydantic)          -> exact 4-part structure
  2. identity guardrail               -> placeholder names / silhouette avatars
  3. format validators                -> plain on-image text, Meta field limits, valid CTA, one format
  4. claim verification               -> DeepSeek-written copy and unsupported claims are cross-checked
Failures get one repair round (OpenAI); variants that still fail are dropped, never surfaced.
"""

from __future__ import annotations

import json
import logging
import string
from typing import Any, Optional

from pydantic import ValidationError

from ..brand import Brand
from ..guardrails import ConsentRegistry, enforce_identity
from ..llm import ChatClient, LLMError
from ..models import (DEFAULT_ASPECT, META_CTAS, AdVariant, Claim, Concept, Finding, ImageSpec,
                      ResearchReport, Source, VisualFormat, PLACEHOLDER_NAME)
from ..store import new_id
from ..validators import clean_plain, validate_variant
from ..verification import CrossChecker

log = logging.getLogger(__name__)

VARIANT_SCHEMA = """{
  "idea": "ONE paragraph (3-6 sentences): the concept, the hook mechanism by name, and the exact audience it is built for (demographics + interests + funnel stage).",
  "hook_mechanism": "e.g. contrarian statement | pattern-interrupt | named/quantified friction | curiosity gap | social proof reversal",
  "audience": {
    "demographics": "age range, role, business type/size, geography — specific",
    "interests": ["Meta-targetable interests or behaviours", "..."],
    "funnel_stage": "cold / TOFU" | "warm / MOFU" | "hot / BOFU",
    "description": "one line naming who this is for, e.g. 'Owners of 1-3 location dental clinics in Lviv already boosting posts'"
  },
  "on_image_text": {"headline": "plain text", "subheadline": "plain text or null"},
  "meta": {
    "primary_text": "the Primary Text field — hook in the first 125 characters, plain text, line breaks allowed",
    "headline": "the Headline field, max 40 characters",
    "description": "the Description field, max 30 characters, or null if not used",
    "cta": "one of the Meta CTA buttons listed"
  },
  "image_spec": {
    "format": "dashboard" | "review_card" | "dm_screenshot",
    "illustrative_numbers": true/false,
    // include EXACTLY ONE of the following blocks, matching the format:
    "dashboard": {"campaign_label": "...", "metrics": [{"label": "Results", "value": "..."}, ...3-6 items], "highlight": "<one metric label>", "annotation": "short note or empty"},
    "review": {"stars": 1-5, "quote": "...", "identity": {"display_name": "[Client Name]", "avatar": "silhouette" | "illustrated"}},
    "dm": {"identity": {"display_name": "[Client Name]", "avatar": "silhouette" | "illustrated"}, "messages": [{"sender": "them" | "me", "text": "..."}], "timestamp_label": "Today 9:41 AM"}
  },
  "claims": [{"text": "every factual/quantified assertion made anywhere in the copy or image content", "support": "F<n> | finding:<n> | none"}]
}"""

SYSTEM = f"""You are the senior creative strategist at a Meta/Google ads agency. You write static
image ad concepts for the agency's own acquisition ads (or a named client when the request says so).

Every variant has EXACTLY four parts, and they are kept strictly separate:
 1. The idea — one paragraph.
 2. On-image text — the exact headline/subheadline the designer pastes over the image in Adobe Express.
    Plain copy only: no quotes around it, no design notes, no fonts/colours/positions, no labels.
    Sentence case, never all caps.
 3. Meta Ads Manager fields — Primary text, Headline (<=40 chars), Description (<=30 chars, optional),
    CTA button, which must be one of: {", ".join(META_CTAS)}.
 4. The image — ONLY the illustrative asset, in one of three formats:
    - dashboard: a Meta Ads Manager table crop with ONE data row and one circled stat
    - review_card: a rounded speech-bubble card with star rating, avatar and quote (no platform branding)
    - dm_screenshot: an iOS Messages screenshot with 1-5 bubbles
    The image never contains the headline, a CTA button or a background gradient — those are added
    by the designer. The image content (stat, quote, messages) must support the hook, not repeat the headline.

Hard rules:
 - Audience must be specific (demographics, interests, funnel stage). Never just "small business owners".
 - People in review cards / DMs are ALWAYS display_name "{PLACEHOLDER_NAME}" with a silhouette or
   illustrated avatar. Never a real or realistic personal name, never a photo-realistic face.
 - Do not name real clients. Agency results may only come from the VERIFIED AGENCY FACTS (cite F<n>).
 - Trend claims may only come from the VERIFIED FINDINGS (cite finding:<n>). Invent no statistics.
   List every factual assertion in "claims" with its support; use "none" only if you truly have none
   (such claims will be fact-checked and removed if unsupported).
 - Dashboard numbers that are not an agency fact must set illustrative_numbers=true.
 - Variants of one concept must test genuinely different hooks (and ideally different formats).
 - Headlines use sentence case, no all-caps, no emoji in on-image text.

Variant JSON schema:
{VARIANT_SCHEMA}
"""

REPAIR_SYSTEM = (
    "You fix ad concept JSON. Correct ONLY the listed problems and keep everything else identical. "
    "Remove or rephrase any unverified factual claim rather than adding new ones. Return the full "
    'variant as JSON: {"variant": {...}}. Schema:\n' + VARIANT_SCHEMA
)

EXTRACT_SYSTEM = (
    "List every factual or quantified assertion (statistics, results, timeframes, prices, claims about "
    "trends or platforms) contained in this ad copy and image content. Opinions and questions are not "
    'claims. Return JSON: {"claims": ["..."]}'
)


class IdeationAgent:
    def __init__(self, brand: Brand, *, openai: Optional[ChatClient], deepseek: Optional[ChatClient],
                 checker: CrossChecker, consents: ConsentRegistry):
        self.brand, self.openai, self.deepseek = brand, openai, deepseek
        self.checker, self.consents = checker, consents

    # ------------------------------------------------------------------ prompts
    @staticmethod
    def _findings_block(research: Optional[ResearchReport]) -> tuple[str, list[Finding]]:
        if not research:
            return "VERIFIED FINDINGS: none available (run research first for trend-informed concepts).", []
        usable = [f for f in research.findings if f.usable]  # unverified leads are never used
        lines = [f"  [finding:{i}] {f.trend} — {f.summary} (formats: {', '.join(x.value for x in f.formats) or 'n/a'})"
                 for i, f in enumerate(usable)]
        return "VERIFIED FINDINGS (from research " + research.id + "):\n" + "\n".join(lines), usable

    def _user_prompt(self, request: str, n_concepts: int, n_variants: int, formats: list[VisualFormat] | None,
                     research: Optional[ResearchReport]) -> str:
        fblock, _ = self._findings_block(research)
        fmt = (f"Use only these image formats: {', '.join(f.value for f in formats)}." if formats
               else "Spread variants across the three image formats where it fits the hook.")
        return (f"{self.brand.prompt_block()}\n\n{fblock}\n\nREQUEST: {request}\n\n"
                f"Produce {n_concepts} concept(s), each with {n_variants} variant(s). {fmt}\n"
                'Return JSON: {"concepts": [{"name": "short concept name", "variants": [<variant>, ...]}]}')

    # ------------------------------------------------------------------ parsing & checks
    def _parse(self, raw: dict[str, Any], vid: str, label: str, origin: str) -> tuple[Optional[AdVariant], list[str]]:
        raw = dict(raw)
        spec = dict(raw.get("image_spec") or {})
        fmt = spec.get("format")
        # keep only the block matching the declared format (models sometimes emit empty siblings)
        keep = {"dashboard": "dashboard", "review_card": "review", "dm_screenshot": "dm"}.get(fmt)
        for k in ("dashboard", "review", "dm"):
            if k != keep and not spec.get(k):
                spec.pop(k, None)
        if fmt in {v.value for v in VisualFormat} and not spec.get("aspect_ratio"):
            spec["aspect_ratio"] = DEFAULT_ASPECT[VisualFormat(fmt)]
        raw["image_spec"] = spec
        for part in ("on_image_text", "meta"):
            if isinstance(raw.get(part), dict):
                raw[part] = {k: clean_plain(v) if isinstance(v, str) else v for k, v in raw[part].items()}
        claims = [c if isinstance(c, dict) else {"text": str(c)} for c in raw.get("claims", [])]
        try:
            v = AdVariant(id=vid, label=label, origin=origin, idea=str(raw.get("idea", "")).strip(),
                          hook_mechanism=raw.get("hook_mechanism", ""), audience=raw.get("audience"),
                          on_image_text=raw.get("on_image_text"), meta=raw.get("meta"),
                          image_spec=ImageSpec.model_validate(spec),
                          claims=[Claim(text=c.get("text", ""), support=str(c.get("support", "none")))
                                  for c in claims if c.get("text")])
        except ValidationError as e:
            return None, [f"schema: {err['loc']}: {err['msg']}" for err in e.errors()][:12]
        v.image_spec = enforce_identity(v.image_spec, self.consents)
        return v, validate_variant(v)

    def _extract_claims(self, v: AdVariant) -> list[Claim]:
        """Independent claim extraction (don't trust a DeepSeek variant's self-reported claims)."""
        if self.openai is None:
            return v.claims
        content = {"idea": v.idea, "on_image_text": v.on_image_text.model_dump(), "meta": v.meta.model_dump(),
                   "image": v.image_spec.model_dump(mode="json", exclude_none=True)}
        try:
            out = self.openai.json(EXTRACT_SYSTEM, json.dumps(content, ensure_ascii=False))
        except LLMError:
            return v.claims
        declared = {c.text: c for c in v.claims}
        return [declared.get(t, Claim(text=t)) for t in out.get("claims", []) if isinstance(t, str)]

    def _support_source(self, claim: Claim, findings: list[Finding], research: Optional[ResearchReport]) -> list[Source]:
        s = claim.support.strip()
        facts = self.brand.facts()
        if s.upper().startswith("F") and s[1:].isdigit() and int(s[1:]) < len(facts):
            return [Source(id=s, title="Agency fact (brand.json)", url=f"brand:{s}", snippet=facts[int(s[1:])])]
        if s.startswith("finding:") and s[8:].isdigit() and int(s[8:]) < len(findings):
            f = findings[int(s[8:])]
            srcs = [research.source(i) for i in f.source_ids] if research else []
            return [Source(id=s, title=f.trend, url=f"finding:{s[8:]}", snippet=f"{f.summary} {f.evidence}")] + \
                   [x for x in srcs if x]
        return []

    def _check_claims(self, v: AdVariant, findings: list[Finding], research: Optional[ResearchReport]) -> list[str]:
        problems = []
        if v.origin == "deepseek":
            v.claims = self._extract_claims(v)
        for c in v.claims:
            support = self._support_source(c, findings, research)
            if v.origin != "deepseek" and support:
                c.verified, c.note = True, f"supported by {c.support}"
                continue
            verdict = self.checker.check(c.text, support)
            c.verified, c.note = verdict.supported, f"{verdict.method}: {verdict.note}"
            if not verdict.supported:
                problems.append(f"unverified claim: \"{c.text}\" — remove it or rephrase without the factual assertion")
        return problems

    def _repair(self, raw: dict, problems: list[str]) -> Optional[dict]:
        if self.openai is None:
            return None
        try:
            out = self.openai.json(REPAIR_SYSTEM, f"{self.brand.prompt_block()}\n\nPROBLEMS:\n- " + "\n- ".join(problems)
                                   + "\n\nVARIANT:\n" + json.dumps(raw, ensure_ascii=False))
        except LLMError as e:
            log.warning("repair failed: %s", e)
            return None
        return out.get("variant") or out

    def _finalise(self, raw: dict, vid: str, label: str, origin: str, findings: list[Finding],
                  research: Optional[ResearchReport]) -> Optional[AdVariant]:
        for attempt in range(2):
            v, problems = self._parse(raw, vid, label, origin)
            if v is not None and not problems:
                problems = self._check_claims(v, findings, research)
                if not problems:
                    return v
            log.info("variant %s attempt %d problems: %s", vid, attempt + 1, problems)
            if attempt == 0:
                fixed = self._repair(raw, problems)
                if not fixed:
                    break
                raw = fixed
        log.warning("dropping variant %s: could not satisfy format/verification rules", vid)
        return None

    # ------------------------------------------------------------------ public
    def _challenger(self, request: str, concept_name: str, existing: list[dict], formats, research) -> Optional[dict]:
        """One extra DeepSeek-written variant per concept (cross-checked like everything DeepSeek makes)."""
        if self.deepseek is None:
            return None
        user = (self._user_prompt(request, 1, 1, formats, research)
                + f"\n\nWrite ONE additional variant for the concept \"{concept_name}\" using a hook mechanism "
                  f"different from these existing variants: {[e.get('hook_mechanism') for e in existing]}.")
        try:
            out = self.deepseek.json(SYSTEM, user)
            return out["concepts"][0]["variants"][0]
        except (LLMError, KeyError, IndexError, TypeError) as e:
            log.warning("DeepSeek challenger variant failed: %s", e)
            return None

    def run(self, request: str, *, n_concepts: int = 1, n_variants: int = 3,
            formats: list[VisualFormat] | None = None, research: Optional[ResearchReport] = None) -> list[Concept]:
        if self.openai is None:
            raise RuntimeError("Ideation needs OPENAI_API_KEY (DeepSeek output alone can never be surfaced unverified).")
        _, findings = self._findings_block(research)
        data = self.openai.json(SYSTEM, self._user_prompt(request, n_concepts, n_variants, formats, research))
        concepts: list[Concept] = []
        for c in (data.get("concepts") or [])[:n_concepts]:
            concept = Concept(id=new_id("c"), name=str(c.get("name", "Untitled concept"))[:80], request=request,
                              research_id=research.id if research else None)
            raws = [(r, "openai") for r in (c.get("variants") or [])[:n_variants]]
            challenger = self._challenger(request, concept.name, [r for r, _ in raws], formats, research)
            if challenger:
                raws.append((challenger, "deepseek"))
            labels = iter(string.ascii_uppercase)
            for raw, origin in raws:
                label = next(labels)
                v = self._finalise(raw, f"{concept.id}-{label}", label, origin, findings, research)
                if v is not None:
                    if formats and v.image_spec.format not in formats:
                        log.warning("dropping %s: format %s not requested", v.id, v.image_spec.format.value)
                        continue
                    concept.variants.append(v)
            # re-letter surviving variants so labels stay contiguous (A, B, C…)
            for v, label in zip(concept.variants, string.ascii_uppercase):
                v.label, v.id = label, f"{concept.id}-{label}"
            if concept.variants:
                concepts.append(concept)
        if not concepts:
            raise RuntimeError("No variant passed the format and verification checks — try rephrasing the request.")
        return concepts
