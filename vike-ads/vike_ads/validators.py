"""Checks that every ad variant honours the 4-part output contract.

Returns human-readable problems; the ideation agent feeds them back to the model
for one repair round and drops variants that still fail.
"""

from __future__ import annotations

import re

from .models import META_CTAS, AdVariant, VisualFormat

# Meta's recommended lengths (text beyond these gets truncated in most placements).
PRIMARY_TEXT_SOFT = 125
PRIMARY_TEXT_MAX = 500
META_HEADLINE_MAX = 40
META_DESCRIPTION_MAX = 30
ON_IMAGE_HEADLINE_MAX = 70
ON_IMAGE_SUB_MAX = 110

DESIGN_WORDS = re.compile(
    r"(#[0-9a-fA-F]{3,6}\b|\b\d+\s?px\b|\b(font|in bold|in italics?|underlined|kerning|"
    r"archivo|plex mono|gradient|overlay|aligned|centered|top[- ]left|bottom[- ]right|"
    r"place (this|it)|design note|typeface|weight 800|text colou?r)\b|[\[(](headline|subheadline|"
    r"subhead|cta)[\])]|^(headline|subheadline|subhead)\s*:)",
    re.I,
)
GENERIC_AUDIENCE = re.compile(
    r"^\s*(small\s+)?(business(es)?|business owners|smbs?|smes?|entrepreneurs|everyone|anyone|marketers)\s*\.?\s*$",
    re.I,
)
PLATFORM_BRANDS = re.compile(r"\b(google|yelp|trustpilot|tripadvisor|facebook reviews?|g2|capterra|clutch)\b", re.I)
MARKDOWN = re.compile(r"(\*\*|__|^#+\s|`)", re.M)


def is_all_caps(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters)


def clean_plain(s: str | None) -> str | None:
    """Normalise copy into paste-ready plain text (strip wrapping quotes/markdown)."""
    if s is None:
        return None
    s = s.strip().strip('"“”').strip()
    s = re.sub(r"(\*\*|__|`)", "", s)
    return s or None


def validate_variant(v: AdVariant) -> list[str]:
    p: list[str] = []

    # Part 1 — one paragraph, hook + specific audience
    if "\n\n" in v.idea.strip() or len(v.idea) < 200:
        p.append("idea must be ONE substantial paragraph (no blank lines, 200+ chars)")
    if len(v.idea) > 1400:
        p.append("idea paragraph is too long (max ~1400 chars)")
    if not v.hook_mechanism.strip():
        p.append("hook_mechanism is required")
    a = v.audience
    if GENERIC_AUDIENCE.match(a.description) or GENERIC_AUDIENCE.match(a.demographics):
        p.append("audience is generic — name demographics, interests and funnel stage specifically")
    if len(a.interests) < 2:
        p.append("audience.interests needs at least 2 specific interests/behaviours")
    if len(a.demographics) < 15:
        p.append("audience.demographics is too vague")

    # Part 2 — plain, paste-ready on-image text
    t = v.on_image_text
    for label, val, limit in (("on_image_text.headline", t.headline, ON_IMAGE_HEADLINE_MAX),
                              ("on_image_text.subheadline", t.subheadline, ON_IMAGE_SUB_MAX)):
        if val is None:
            continue
        if DESIGN_WORDS.search(val) or MARKDOWN.search(val):
            p.append(f"{label} contains design instructions/markup — plain copy only")
        if is_all_caps(val):
            p.append(f"{label} is all-caps — brand headlines are sentence case")
        if len(val) > limit:
            p.append(f"{label} is {len(val)} chars (max {limit})")
    if not t.headline.strip():
        p.append("on_image_text.headline is empty")

    # Part 3 — Meta Ads Manager fields
    m = v.meta
    if not m.primary_text.strip():
        p.append("meta.primary_text is empty")
    if len(m.primary_text) > PRIMARY_TEXT_MAX:
        p.append(f"meta.primary_text is {len(m.primary_text)} chars (keep under {PRIMARY_TEXT_MAX}; "
                 f"first {PRIMARY_TEXT_SOFT} must carry the hook)")
    if len(m.headline) > META_HEADLINE_MAX:
        p.append(f"meta.headline is {len(m.headline)} chars (max {META_HEADLINE_MAX})")
    if m.description and len(m.description) > META_DESCRIPTION_MAX:
        p.append(f"meta.description is {len(m.description)} chars (max {META_DESCRIPTION_MAX})")
    if m.cta not in META_CTAS:
        p.append(f"meta.cta '{m.cta}' is not a Meta CTA button; choose from: {', '.join(META_CTAS)}")

    # Part 4 — image spec matches exactly one established format
    s = v.image_spec
    present = [k for k in ("dashboard", "review", "dm") if getattr(s, k) is not None]
    expected = {VisualFormat.DASHBOARD: "dashboard", VisualFormat.REVIEW_CARD: "review",
                VisualFormat.DM_SCREENSHOT: "dm"}[s.format]
    if present != [expected]:
        p.append(f"image_spec must contain only the '{expected}' block for format {s.format.value}")
    if s.dashboard:
        d = s.dashboard
        if not 3 <= len(d.metrics) <= 6:
            p.append("dashboard needs 3-6 metrics in its single data row")
        if d.highlight not in [x.label for x in d.metrics]:
            p.append("dashboard.highlight must equal one of the metric labels")
        if len(d.annotation) > 40:
            p.append("dashboard.annotation must be a short note (max 40 chars)")
    if s.review:
        if len(s.review.quote) > 240:
            p.append("review.quote too long for a card (max 240 chars)")
        if PLATFORM_BRANDS.search(s.review.quote):
            p.append("review card must not reference review platforms (no fake platform branding)")
    if s.dm:
        if not 1 <= len(s.dm.messages) <= 5:
            p.append("dm needs 1-5 messages")
        if any(len(msg.text) > 180 for msg in s.dm.messages):
            p.append("dm message bubbles must be under 180 chars each")

    # Copy must not repeat the design-free rule violations inside Meta fields either
    if MARKDOWN.search(m.primary_text) or MARKDOWN.search(m.headline):
        p.append("meta fields must be plain text (no markdown)")
    return p
