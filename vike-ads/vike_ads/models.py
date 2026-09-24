"""Data models. `AdVariant` is the 4-part ad concept contract:

  1. idea            — one paragraph (concept + hook mechanism + specific audience)
  2. on_image_text   — plain headline/subheadline the user places in Adobe Express
  3. meta            — Meta Ads Manager fields (Primary text, Headline, Description, CTA)
  4. image_spec/image — the illustrative asset only (never a composited ad)

Everything else on the model (audience, hook_mechanism, claims, origin) is internal
bookkeeping used for validation and is never rendered as an extra "part".
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

PLACEHOLDER_NAME = "[Client Name]"

# Call-to-action buttons offered in Meta Ads Manager (static image ads).
META_CTAS = [
    "Apply Now", "Book Now", "Call Now", "Contact Us", "Download", "Get Access",
    "Get Directions", "Get Offer", "Get Quote", "Get Updates", "Learn More",
    "Order Now", "Request Time", "See Menu", "Send Message", "Send WhatsApp Message",
    "Shop Now", "Sign Up", "Subscribe", "Watch More",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VisualFormat(str, Enum):
    DASHBOARD = "dashboard"
    REVIEW_CARD = "review_card"
    DM_SCREENSHOT = "dm_screenshot"

    @property
    def label(self) -> str:
        return {
            "dashboard": "Dashboard / Ads Manager screenshot",
            "review_card": "Review card",
            "dm_screenshot": "DM / iMessage screenshot",
        }[self.value]


DEFAULT_ASPECT = {
    VisualFormat.DASHBOARD: "4:3",
    VisualFormat.REVIEW_CARD: "4:3",
    VisualFormat.DM_SCREENSHOT: "3:4",
}


# ---------------------------------------------------------------- research

class Source(BaseModel):
    id: str
    title: str = ""
    url: str = ""
    kind: Literal["web", "meta_ad_library", "page"] = "web"
    snippet: str = ""
    retrieved_at: datetime = Field(default_factory=utcnow)


class Finding(BaseModel):
    trend: str
    summary: str
    evidence: str = ""
    formats: list[VisualFormat] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    # sourced: grounded in fetched sources by a non-DeepSeek model
    # cross_checked: DeepSeek output confirmed by a second source (OpenAI + fresh search)
    # unverified: never surfaced as a finding, never fed into ideation
    verification: Literal["sourced", "cross_checked", "unverified"] = "sourced"
    verification_note: str = ""

    @property
    def usable(self) -> bool:
        return self.verification in ("sourced", "cross_checked")


class ResearchReport(BaseModel):
    id: str
    topic: str
    created_at: datetime = Field(default_factory=utcnow)
    findings: list[Finding] = Field(default_factory=list)
    unverified_leads: list[Finding] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    manual_links: list[Source] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def source(self, sid: str) -> Optional[Source]:
        return next((s for s in self.sources if s.id == sid), None)


# ---------------------------------------------------------------- concept parts

class Audience(BaseModel):
    demographics: str
    interests: list[str]
    funnel_stage: Literal["cold / TOFU", "warm / MOFU", "hot / BOFU"]
    description: str


class OnImageText(BaseModel):
    headline: str
    subheadline: Optional[str] = None


class MetaFields(BaseModel):
    primary_text: str
    headline: str
    description: Optional[str] = None
    cta: str


class Identity(BaseModel):
    display_name: str = PLACEHOLDER_NAME
    avatar: Literal["silhouette", "illustrated", "photoreal"] = "silhouette"
    consent_ref: Optional[str] = None  # set only by the guardrail from the consent registry


class Metric(BaseModel):
    label: str
    value: str


class DashboardSpec(BaseModel):
    campaign_label: str
    metrics: list[Metric]
    highlight: str  # label of the metric that gets circled
    annotation: str = ""  # optional short hand-written note next to the circle


class ReviewSpec(BaseModel):
    stars: int = Field(ge=1, le=5)
    quote: str
    identity: Identity = Field(default_factory=Identity)


class Message(BaseModel):
    sender: Literal["them", "me"]
    text: str


class DMSpec(BaseModel):
    identity: Identity = Field(default_factory=Identity)
    messages: list[Message]
    timestamp_label: str = "Today 9:41 AM"


class ImageSpec(BaseModel):
    format: VisualFormat
    aspect_ratio: str = ""
    dashboard: Optional[DashboardSpec] = None
    review: Optional[ReviewSpec] = None
    dm: Optional[DMSpec] = None
    illustrative_numbers: bool = False

    def identity(self) -> Optional[Identity]:
        if self.review:
            return self.review.identity
        if self.dm:
            return self.dm.identity
        return None


class GeneratedImage(BaseModel):
    path: str
    backend: str
    model: str
    prompt: str
    created_at: datetime = Field(default_factory=utcnow)
    qa_passed: Optional[bool] = None
    qa_issues: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    text: str
    support: str = "none"  # "F<n>" (agency fact), "finding:<n>", or "none"
    verified: bool = False
    note: str = ""


class AdVariant(BaseModel):
    id: str
    label: str  # "A", "B", ...
    origin: str = "openai"  # model provider that wrote the copy
    # Part 1
    idea: str
    hook_mechanism: str
    audience: Audience
    # Part 2
    on_image_text: OnImageText
    # Part 3
    meta: MetaFields
    # Part 4
    image_spec: ImageSpec
    image: Optional[GeneratedImage] = None
    # bookkeeping
    claims: list[Claim] = Field(default_factory=list)


class Concept(BaseModel):
    id: str
    name: str
    request: str
    created_at: datetime = Field(default_factory=utcnow)
    research_id: Optional[str] = None
    variants: list[AdVariant] = Field(default_factory=list)

    def variant(self, vid: str) -> Optional[AdVariant]:
        return next((v for v in self.variants if v.id.lower() == vid.lower()), None)
