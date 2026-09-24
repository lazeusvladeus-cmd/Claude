"""Orchestrator — routes a request to the right agent.

  "research X"                -> Research Agent
  "give me an ad idea for X"  -> Ideation Agent (+ Image Agent) — full 4-part output
  "generate the image for X"  -> Image Agent only — part 4 alone, reusing the stored concept
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx

from .agents.ideation import IdeationAgent
from .agents.image import ImageAgent
from .agents.research import ResearchAgent
from .brand import Brand
from .config import Settings
from .guardrails import ConsentRegistry, NeedsConfirmation
from .images.backends import FalBackend, ImageGenerationError, ImageRouter, NanoBananaBackend
from .images.qa import ImageQA
from .llm import ChatClient, LLMError, OpenAIClient
from .models import Concept, ResearchReport, VisualFormat
from .render import concept_md, image_only_md, report_md
from .search import GoogleCSESearch, MetaAdLibrary, OpenAIWebSearch, fetch_excerpt
from .store import Store
from .verification import CrossChecker

log = logging.getLogger(__name__)


class Intent(str, Enum):
    RESEARCH = "research"
    IDEA = "idea"
    IMAGE = "image"
    UNKNOWN = "unknown"


IMAGE_RE = re.compile(
    r"^\s*(?:please\s+|can you\s+|now\s+)*(?:just\s+|only\s+)?"
    r"(?:generate|create|make|render|re-?render|regenerate|redo|produce|draw)\s+(?:me\s+)?(?:just\s+|only\s+)?"
    r"(?:the\s+|an?\s+|its\s+)?(?:images?|visuals?|pictures?|assets?|part\s*4)\b"
    r"(?:\s+(?:only|for|of|from))*\s*(?P<subject>.*)$", re.I)
RESEARCH_RE = re.compile(
    r"^\s*(?:please\s+)?(?:research|look\s+into|investigate|what(?:'s| is| are)\s+(?:trending|working)|"
    r"find\s+(?:current\s+)?trends?)\b(?:\s+(?:on|about|into|for))?\s*(?P<subject>.*)$", re.I)
IDEA_RE = re.compile(
    r"(?:\bad\s+(?:ideas?|concepts?|creatives?)\b|\bideas?\s+for\b|\bconcepts?\s+for\b|"
    r"\b(?:write|draft|come up with|brainstorm|give me)\b.*\b(?:ads?|ideas?|concepts?)\b)", re.I)


def classify(text: str) -> tuple[Intent, str]:
    m = IMAGE_RE.match(text)
    if m:
        return Intent.IMAGE, m.group("subject").strip(" .?!:")
    m = RESEARCH_RE.match(text)
    if m:
        return Intent.RESEARCH, m.group("subject").strip(" .?!:")
    if IDEA_RE.search(text):
        subj = re.sub(r"^\s*(?:please\s+)?(?:give me|write|draft|come up with|brainstorm)\s+", "", text, flags=re.I)
        return Intent.IDEA, subj.strip(" .?!:")
    return Intent.UNKNOWN, text.strip()


@dataclass
class Result:
    kind: str  # research | concepts | image | question | error
    markdown: str
    report: Optional[ResearchReport] = None
    concepts: list[Concept] = field(default_factory=list)
    question: Optional[str] = None
    pending_name: Optional[str] = None
    notes: list[str] = field(default_factory=list)


class Orchestrator:
    def __init__(self, settings: Settings, brand: Brand, store: Store, research: ResearchAgent,
                 ideation: IdeationAgent, image: ImageAgent, consents: ConsentRegistry,
                 classifier: Optional[ChatClient] = None):
        self.settings, self.brand, self.store = settings, brand, store
        self.research_agent, self.ideation_agent, self.image_agent = research, ideation, image
        self.consents, self.classifier = consents, classifier

    # ------------------------------------------------------------------ routing
    def route(self, text: str) -> tuple[Intent, str]:
        intent, subject = classify(text)
        if intent is Intent.UNKNOWN and self.classifier is not None:
            try:
                out = self.classifier.json(
                    "Classify the user's request for an ad-creative system into one intent: "
                    "'research' (find trends/sources), 'idea' (write new ad concepts), "
                    "'image' (render the image for an existing concept). "
                    'Return JSON {"intent": "...", "subject": "the topic/concept reference"}', text)
                intent = Intent(out.get("intent", "unknown"))
                subject = out.get("subject") or text
            except (LLMError, ValueError):
                pass
        return intent, subject

    def handle(self, text: str, **opts) -> Result:
        intent, subject = self.route(text)
        if intent is Intent.RESEARCH:
            return self.research(subject)
        if intent is Intent.IDEA:
            return self.idea(subject or text, **{k: v for k, v in opts.items() if k in
                                                  {"n_concepts", "n_variants", "formats", "render_images"}})
        if intent is Intent.IMAGE:
            return self.image(subject, **{k: v for k, v in opts.items() if k in {"photoreal_name", "backend"}})
        return Result("question", "I can: **research** trends (\"research fake DM ads\"), write an **ad idea** "
                                  "(\"give me an ad idea for dental clinics in Lviv\"), or **generate the image** "
                                  "for an existing concept (\"generate the image for c-20260924-ab12-B\"). "
                                  "Which one did you mean?", question="clarify intent")

    # ------------------------------------------------------------------ actions
    def research(self, topic: str = "", themes: list[str] | None = None) -> Result:
        report = self.research_agent.run(topic, themes)
        self.store.save_report(report)
        return Result("research", report_md(report), report=report)

    def idea(self, request: str, *, n_concepts: int = 1, n_variants: int = 3,
             formats: list[VisualFormat] | None = None, render_images: bool = True) -> Result:
        research = self.store.latest_report()
        concepts = self.ideation_agent.run(request, n_concepts=n_concepts, n_variants=n_variants,
                                           formats=formats, research=research)
        notes = []
        if research is None:
            notes.append("No research report yet — concepts use brand context only. Run `vike-ads research` for trend input.")
        for c in concepts:
            self.store.save_concept(c)  # save copy first: parts 1-3 are never lost to an image failure
            if render_images:
                for v in c.variants:
                    try:
                        self.image_agent.render(v)
                    except (ImageGenerationError, httpx.HTTPError) as e:
                        notes.append(f"{v.id}: image not rendered ({e}). Retry with: vike-ads image {v.id}")
                self.store.save_concept(c)
            notes += [f"{v.id}: dashboard numbers are illustrative — swap in real account data before running."
                      for v in c.variants if v.image_spec.illustrative_numbers]
            notes += [f"{v.id}: image QA flagged: {'; '.join(v.image.qa_issues)}"
                      for v in c.variants if v.image and v.image.qa_passed is False]
        return Result("concepts", "\n\n---\n\n".join(concept_md(c) for c in concepts), concepts=concepts, notes=notes)

    def image(self, ref: str, *, photoreal_name: Optional[str] = None, backend: Optional[str] = None) -> Result:
        matches, candidates = self.store.find_variants(ref)
        if not matches:
            if candidates:
                opts = "\n".join(f"- {v.id} · {c.name}" for c, v in candidates)
                return Result("question", f"Which agreed concept did you mean? I won't invent a new one:\n{opts}",
                              question="which concept")
            return Result("error", f"No agreed concept matches \"{ref}\". Create one first with an ad-idea request — "
                                   "the image step only renders concepts that already exist.")
        out, notes = [], []
        for c, v in matches:
            try:
                self.image_agent.render(v, photoreal_name=photoreal_name, prefer_backend=backend)
            except NeedsConfirmation as q:
                return Result("question", q.question, question=q.question, pending_name=q.name)
            except (ImageGenerationError, httpx.HTTPError) as e:
                return Result("error", f"{v.id}: image generation failed — {e}")
            self.store.save_concept(c)
            if v.image and v.image.qa_passed is False:
                notes.append(f"{v.id}: image QA flagged: {'; '.join(v.image.qa_issues)}")
            out.append(image_only_md(c, v))
        return Result("image", "\n\n---\n\n".join(out), concepts=[m[0] for m in matches[:1]], notes=notes)


def build(settings: Optional[Settings] = None) -> Orchestrator:
    s = settings or Settings.from_env()
    brand = Brand.load(s.brand_file)
    store = Store(s.data_dir)
    consents = ConsentRegistry(store.consent_file)
    http = httpx.Client()

    openai = OpenAIClient("openai", s.openai_api_key, s.openai_base_url, s.openai_model, http) \
        if s.openai_api_key else None
    deepseek = ChatClient("deepseek", s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model, http) \
        if (s.deepseek_api_key and s.use_deepseek) else None
    if s.google_cse_api_key and s.google_cse_id:
        web = GoogleCSESearch(s.google_cse_api_key, s.google_cse_id, http)
    elif openai is not None:
        web = OpenAIWebSearch(openai)
    else:
        web = None
    ad_library = MetaAdLibrary(s.meta_ad_library_token, s.meta_ad_library_countries, http) \
        if s.meta_ad_library_token else None
    checker = CrossChecker(openai, web)

    research = ResearchAgent(brand, openai=openai, deepseek=deepseek, web=web, ad_library=ad_library,
                             checker=checker, fetcher=(lambda u: fetch_excerpt(u, http)) if s.fetch_pages else None,
                             countries=s.meta_ad_library_countries)
    ideation = IdeationAgent(brand, openai=openai, deepseek=deepseek, checker=checker, consents=consents)
    router = ImageRouter([
        NanoBananaBackend(s.gemini_api_key, s.gemini_image_model, mode=s.google_image_backend,
                          vertex_project=s.vertex_project, vertex_location=s.vertex_location, http=http),
        FalBackend(s.fal_key, s.fal_model, http),
    ])
    qa = ImageQA(openai) if (openai is not None and s.image_qa) else None
    image = ImageAgent(brand, router, store, consents, references_dir=s.references_dir, qa=qa,
                       max_attempts=s.image_max_attempts)
    return Orchestrator(s, brand, store, research, ideation, image, consents, classifier=openai)
