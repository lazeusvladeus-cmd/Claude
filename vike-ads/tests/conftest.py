from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vike_ads.agents.ideation import IdeationAgent  # noqa: E402
from vike_ads.agents.image import ImageAgent  # noqa: E402
from vike_ads.agents.research import ResearchAgent  # noqa: E402
from vike_ads.brand import Brand  # noqa: E402
from vike_ads.config import Settings  # noqa: E402
from vike_ads.guardrails import ConsentRegistry  # noqa: E402
from vike_ads.images.backends import ImageResult, ImageRouter  # noqa: E402
from vike_ads.models import Source  # noqa: E402
from vike_ads.orchestrator import Orchestrator  # noqa: E402
from vike_ads.store import Store  # noqa: E402
from vike_ads.verification import CrossChecker  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def good_variant(fmt: str = "review_card", **over) -> dict:
    v = {
        "idea": ("A contrarian 1-star review card that turns the most common complaint about agencies into "
                 "the pitch: the reviewer is angry that Vike 'made them cancel their boost button habit'. "
                 "The hook is a pattern-interrupt — a negative review that is secretly a compliment — built for "
                 "owners of 1-3 location dental clinics in Lviv aged 30-50 who already boost Instagram posts "
                 "and are problem-aware but have never hired an agency (cold / TOFU)."),
        "hook_mechanism": "pattern-interrupt: negative review that reads as praise",
        "audience": {"demographics": "Dental clinic owners, 30-50, Lviv, 1-3 locations",
                     "interests": ["Instagram boosted posts", "Dental practice management"],
                     "funnel_stage": "cold / TOFU",
                     "description": "Lviv dental clinic owners who boost posts themselves"},
        "on_image_text": {"headline": "Our worst review is our best pitch", "subheadline": "Month-to-month from $200"},
        "meta": {"primary_text": "One star. Apparently we ruined boosting posts for this clinic owner.\n\nNo contracts.",
                 "headline": "Plans from $200/month", "description": "No contracts", "cta": "Learn More"},
        "image_spec": {"format": fmt},
        "claims": [{"text": "Plans start at $200/month", "support": "F0"}],
    }
    if fmt == "review_card":
        v["image_spec"]["review"] = {"stars": 1, "quote": "They made me stop boosting posts. Now I just get bookings.",
                                     "identity": {"display_name": "[Client Name]", "avatar": "silhouette"}}
    elif fmt == "dashboard":
        v["image_spec"]["illustrative_numbers"] = True
        v["image_spec"]["dashboard"] = {"campaign_label": "Clinic leads — Lviv",
                                        "metrics": [{"label": "Results", "value": "38 leads"},
                                                    {"label": "Cost per result", "value": "$4.10"},
                                                    {"label": "Amount spent", "value": "$156.00"}],
                                        "highlight": "Cost per result", "annotation": "this one"}
    else:
        v["image_spec"]["dm"] = {"identity": {"display_name": "[Client Name]", "avatar": "silhouette"},
                                 "messages": [{"sender": "them", "text": "ok who set up our ads?? phone won't stop"},
                                              {"sender": "me", "text": "that would be us"}]}
    v.update(over)
    return v


class FakeChat:
    """Scripted chat client. `handlers` maps a substring of the system prompt to a response
    (dict, or callable(system, user) -> dict)."""

    def __init__(self, name: str, handlers: dict):
        self.name, self.handlers, self.calls = name, handlers, []

    def json(self, system, user):
        self.calls.append((system, user))
        for key, resp in self.handlers.items():
            if key in system:
                return copy.deepcopy(resp(system, user) if callable(resp) else resp)
        raise AssertionError(f"{self.name}: unexpected prompt: {system[:80]}")


class FakeWeb:
    name = "fake_web"

    def __init__(self, results=None):
        self.results = results if results is not None else [
            Source(id="", title="Trend article", url="https://example.com/trend", snippet="1-star review ads are up"),
        ]
        self.queries = []

    def search(self, query, n=5):
        self.queries.append(query)
        return [s.model_copy() for s in self.results[:n]]


class FakeBackend:
    def __init__(self, name, ok=True):
        self.name, self.ok, self.prompts = name, ok, []

    def available(self):
        return True

    def generate(self, prompt, aspect_ratio, refs):
        from vike_ads.images.backends import ImageGenerationError
        self.prompts.append(prompt)
        if not self.ok:
            raise ImageGenerationError(f"{self.name} down")
        return ImageResult(PNG, "image/png", self.name, f"{self.name}-model")


@pytest.fixture
def brand():
    return Brand.load(ROOT / "config" / "brand.json")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data")


@pytest.fixture
def consents(store):
    return ConsentRegistry(store.consent_file)


def make_orch(brand, store, consents, *, openai=None, deepseek=None, web=None, backends=None, qa=None):
    checker = CrossChecker(openai, web)
    research = ResearchAgent(brand, openai=openai, deepseek=deepseek, web=web, ad_library=None, checker=checker)
    ideation = IdeationAgent(brand, openai=openai, deepseek=deepseek, checker=checker, consents=consents)
    router = ImageRouter(backends if backends is not None else [FakeBackend("nano-banana")])
    image = ImageAgent(brand, router, store, consents, qa=qa)
    return Orchestrator(Settings(data_dir=store.root), brand, store, research, ideation, image, consents)
