"""Vision QA: check a rendered asset against the format rules before accepting it."""

from __future__ import annotations

import base64
import logging

from ..llm import ChatClient, LLMError
from ..models import ImageSpec

log = logging.getLogger(__name__)

QA_SYSTEM = (
    "You are a meticulous QA reviewer for ad image assets. Inspect the image and report problems. "
    'Return JSON: {"pass": bool, "issues": ["short issue", ...]}. Fail the image if ANY of these hold: '
    "(1) it contains a headline, tagline or marketing caption that is not part of the UI content; "
    "(2) it contains a call-to-action button; (3) the background has a decorative gradient or pattern; "
    "(4) any expected text is misspelled, garbled, duplicated or missing; (5) there is pseudo-text or "
    "unreadable filler text; (6) there are review-platform logos or other brand marks; "
    "(7) {face_rule}; (8) it does not look like the requested format: {format}."
)


class ImageQA:
    def __init__(self, client: ChatClient):
        self.client = client

    def check(self, image: bytes, mime: str, spec: ImageSpec,
              expected: list[str]) -> tuple[bool | None, list[str]]:
        """Returns (passed, issues); passed is None when QA could not run."""
        ident = spec.identity()
        face_rule = ("a photo-realistic human face is shown" if not ident or ident.avatar != "photoreal"
                     else "the avatar is not a plausible generic headshot")
        system = QA_SYSTEM.replace("{face_rule}", face_rule).replace("{format}", spec.format.label)
        text = "Expected text (must appear, spelled exactly):\n" + "\n".join(f"- {t}" for t in expected)
        content = [
            {"type": "text", "text": text},
            {"type": "image_url",
             "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode()}"}},
        ]
        try:
            out = self.client.json(system, content)
        except LLMError as e:
            log.warning("image QA unavailable: %s", e)
            return None, [f"QA skipped: {e}"]
        issues = [str(i) for i in out.get("issues", [])][:10]
        return bool(out.get("pass")), issues
