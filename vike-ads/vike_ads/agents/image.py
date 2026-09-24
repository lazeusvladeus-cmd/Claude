"""Image Generation Agent — part 4 only.

Renders the illustrative asset for an already-agreed variant. It never calls a copy
model: the prompt is built deterministically from the stored image spec, so asking
for "just the image" can't produce new copy. It never composites a finished ad.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ..brand import Brand
from ..guardrails import ConsentRegistry, assert_identity_safe, enforce_identity
from ..images.backends import ImageRouter, RefImage
from ..images.prompts import build_prompt, expected_text
from ..images.qa import ImageQA
from ..models import AdVariant, GeneratedImage, VisualFormat
from ..store import Store

log = logging.getLogger(__name__)

EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


class ImageAgent:
    def __init__(self, brand: Brand, router: ImageRouter, store: Store, consents: ConsentRegistry, *,
                 references_dir: Optional[Path] = None, qa: Optional[ImageQA] = None, max_attempts: int = 2):
        self.brand, self.router, self.store, self.consents = brand, router, store, consents
        self.references_dir, self.qa, self.max_attempts = references_dir, qa, max_attempts

    def references(self, fmt: VisualFormat, limit: int = 3) -> list[RefImage]:
        if not self.references_dir:
            return []
        d = self.references_dir / fmt.value
        files = sorted(p for p in d.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}) \
            if d.is_dir() else []
        return [RefImage.from_path(p) for p in files[:limit]]

    def render(self, variant: AdVariant, *, photoreal_name: Optional[str] = None,
               prefer_backend: Optional[str] = None) -> GeneratedImage:
        """Render part 4 for `variant`. May raise guardrails.NeedsConfirmation."""
        spec = enforce_identity(variant.image_spec, self.consents, requested_photoreal_name=photoreal_name)
        assert_identity_safe(spec, self.consents)
        base_prompt = build_prompt(spec, self.brand)
        refs = self.references(spec.format)
        expected = expected_text(spec)

        prompt, result, issues, passed = base_prompt, None, [], None
        for attempt in range(1, self.max_attempts + 1):
            result = self.router.generate(prompt, spec.aspect_ratio or "4:3", refs, prefer=prefer_backend)
            if self.qa is None:
                break
            passed, issues = self.qa.check(result.data, result.mime, spec, expected)
            if passed is not False:
                break
            log.info("image QA failed (attempt %d): %s", attempt, issues)
            prompt = base_prompt + "\n\nA previous attempt had these problems — avoid them:\n- " + "\n- ".join(issues)

        path = self.store.image_path(variant.id, EXT.get(result.mime, "png"))
        path.write_bytes(result.data)
        image = GeneratedImage(path=str(path), backend=result.backend, model=result.model, prompt=prompt,
                               qa_passed=passed, qa_issues=issues)
        variant.image_spec = spec  # persist the guardrail-sanitised spec
        variant.image = image
        return image
