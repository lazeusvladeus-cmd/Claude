"""Deterministic image-prompt builder.

The prompt is built only from the stored, agreed image spec — no LLM call, so the
image agent can never invent new copy. Every prompt carries the same hard negative
block: the output is an isolated illustrative asset, never a composited ad.
"""

from __future__ import annotations

from ..brand import Brand
from ..models import DashboardSpec, DMSpec, Identity, ImageSpec, ReviewSpec, VisualFormat


def _avatar(ident: Identity) -> str:
    if ident.avatar == "photoreal":
        return ("a photo-realistic headshot avatar: a generated, non-literal likeness for a consented client — "
                "do not attempt to reproduce any specific real person's face")
    if ident.avatar == "illustrated":
        return "a simple flat illustrated avatar, clearly non-photographic, not resembling any real person"
    return "a plain neutral grey default-avatar silhouette icon (head and shoulders), no facial features"


def _negatives(brand: Brand, allowed_text_note: str) -> str:
    bg = brand.colors["light_background"]
    return (
        "\n\nSTRICT RULES — this is an isolated illustrative asset, NOT a finished ad:\n"
        "- Do NOT add any headline, caption, tagline, slogan or marketing copy anywhere in the image.\n"
        "- Do NOT add any call-to-action button, pill button, arrow button or 'Learn more' style element.\n"
        "- Do NOT add logos, watermarks, brand marks or review-platform branding.\n"
        f"- Background outside the mockup: flat solid {bg}. No gradient, no pattern, no bokeh, no props, "
        "no hands, no desk, no device frame.\n"
        f"- {allowed_text_note} Every word must be spelled exactly as given, crisp and legible. "
        "No lorem ipsum, no pseudo-text, no garbled or extra characters.\n"
        "- Clean, realistic UI rendering; straight edges; no distortion."
    )


def _dashboard(d: DashboardSpec, brand: Brand) -> str:
    cols = " | ".join(m.label for m in d.metrics)
    vals = " | ".join(m.value for m in d.metrics)
    hi = next(m for m in d.metrics if m.label == d.highlight)
    note = (f' Next to the circle, a short hand-written note in the same colour reads "{d.annotation}".'
            if d.annotation else "")
    return (
        "A realistic, high-fidelity screenshot-style crop of the Meta Ads Manager campaigns table "
        "(desktop web UI, light theme, neutral greys, the standard sans-serif UI font). "
        "Show the column header row and exactly ONE data row beneath it — no other rows, no sidebar, "
        "no browser chrome, no top navigation.\n"
        f'Campaign name cell: "{d.campaign_label}", with a small blue on/off toggle switched on at its left.\n'
        f"Column headers, left to right: {cols}\n"
        f"Values in the single data row, same order: {vals}\n"
        f'Draw one hand-drawn-style marker circle in {brand.colors["primary_accent"]} around the '
        f'"{hi.label}" value "{hi.value}", as if someone annotated the screenshot.{note}'
        + _negatives(brand, "The only text allowed is the column headers, the campaign name, the row values"
                            + (" and the short annotation" if d.annotation else "") + " listed above.")
    )


def _review(r: ReviewSpec, brand: Brand) -> str:
    c = brand.colors
    empty = 5 - r.stars
    return (
        "A single review card, flat front-on view, centred: a white rounded speech-bubble card "
        f"(16px corner radius, 1px hairline border {c['hairline_border']}) with a small speech-bubble tail "
        "at the bottom-left edge, soft subtle shadow.\n"
        f"Top row inside the card: a circular avatar showing {_avatar(r.identity)}; beside it the name "
        f'"{r.identity.display_name}" in bold {c["ink"]} text.\n'
        f"Below: a row of 5 stars — exactly {r.stars} filled in {c['primary_accent']}"
        + (f" and {empty} empty outline stars" if empty else "") + ".\n"
        f'Below the stars, the review quote in {c["ink"]}, clean sans-serif, left-aligned: "{r.quote}"\n'
        "No platform logo, no verified badge, no date, no like/share icons."
        + _negatives(brand, "The only text allowed is the name and the quote given above.")
    )


def _dm(d: DMSpec, brand: Brand) -> str:
    lines = []
    for i, m in enumerate(d.messages, 1):
        side = ("incoming — light grey bubble, left-aligned" if m.sender == "them"
                else "outgoing — blue iMessage bubble with white text, right-aligned")
        lines.append(f'  {i}. ({side}) "{m.text}"')
    last_me = any(m.sender == "me" for m in d.messages[-1:])
    return (
        "A realistic iPhone iOS Messages app screenshot, light mode, portrait, full-bleed screen only "
        "(no phone hardware frame).\n"
        'Status bar at the very top: time "9:41" on the left, signal/Wi-Fi/battery icons on the right.\n'
        f"Conversation header: a back chevron on the left, a small circular avatar centred showing "
        f'{_avatar(d.identity)}, with the contact name "{d.identity.display_name}" in small text under it.\n'
        f'A small centred grey timestamp above the first message: "{d.timestamp_label}".\n'
        "Message bubbles, top to bottom, in this exact order:\n" + "\n".join(lines) + "\n"
        + ('Under the last outgoing bubble, small grey text: "Delivered".\n' if last_me else "")
        + 'Bottom: the standard iMessage input bar with the placeholder "iMessage" and the app/camera icons.'
        + _negatives(brand, "The only text allowed is the status-bar time, contact name, timestamp, the "
                            "message texts above, 'Delivered' (if shown) and the 'iMessage' placeholder.")
    )


def build_prompt(spec: ImageSpec, brand: Brand) -> str:
    if spec.format is VisualFormat.DASHBOARD and spec.dashboard:
        return _dashboard(spec.dashboard, brand)
    if spec.format is VisualFormat.REVIEW_CARD and spec.review:
        return _review(spec.review, brand)
    if spec.format is VisualFormat.DM_SCREENSHOT and spec.dm:
        return _dm(spec.dm, brand)
    raise ValueError(f"image spec for {spec.format.value} is missing its content block")


def expected_text(spec: ImageSpec) -> list[str]:
    """Strings the QA step must find, spelled correctly, in the rendered image."""
    if spec.dashboard:
        d = spec.dashboard
        out = [d.campaign_label] + [m.label for m in d.metrics] + [m.value for m in d.metrics]
        return out + ([d.annotation] if d.annotation else [])
    if spec.review:
        return [spec.review.identity.display_name, spec.review.quote]
    if spec.dm:
        return [spec.dm.identity.display_name] + [m.text for m in spec.dm.messages] + ["iMessage"]
    return []
