"""Identity guardrail — hard-coded, not user-overridable.

Never generate a testimonial, review, or DM screenshot attributed to a named,
photo-realistic person unless the user has explicitly confirmed that the name is a
real client who consented to a generated (non-literal) likeness.

  * Default identity: "[Client Name]" + silhouette avatar, which the user fills in.
  * A model-suggested real-looking name is replaced with the placeholder.
  * A photo-realistic avatar is only allowed for a name recorded in the consent
    registry. If a user asks for one without that record, we raise
    NeedsConfirmation (ask first) instead of generating.

There is deliberately no setting, env var, or flag that disables these checks.
The only path to a photoreal named likeness is an explicit per-name consent record.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import PLACEHOLDER_NAME, ImageSpec, Identity


class NeedsConfirmation(Exception):
    """The system must ask the user before continuing."""

    def __init__(self, question: str, name: str):
        super().__init__(question)
        self.question = question
        self.name = name


class ConsentRegistry:
    """Per-name record that a real client consented to a generated likeness."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def _key(name: str) -> str:
        return re.sub(r"\s+", " ", name.strip().lower())

    def get(self, name: str) -> Optional[dict]:
        return self._load().get(self._key(name))

    def is_confirmed(self, name: str) -> bool:
        rec = self.get(name)
        return bool(rec and rec.get("real_client") and rec.get("consented_to_generated_likeness"))

    def confirm(self, name: str, confirmed_by: str = "user", note: str = "") -> dict:
        if is_placeholder(name):
            raise ValueError("cannot record consent for a placeholder name")
        data = self._load()
        rec = {
            "name": name.strip(),
            "real_client": True,
            "consented_to_generated_likeness": True,
            "confirmed_by": confirmed_by,
            "note": note,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }
        data[self._key(name)] = rec
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return rec

    def all(self) -> list[dict]:
        return list(self._load().values())


def is_placeholder(name: str | None) -> bool:
    if not name or not name.strip():
        return True
    n = name.strip()
    return (n.startswith("[") and n.endswith("]")) or n.lower() in {"client", "customer", "your client"}


def consent_question(name: str) -> str:
    return (
        f'Is "{name}" a real client who has explicitly consented to appearing in an ad as a '
        "generated (non-literal) photo-realistic likeness? Answer yes only if you have that consent."
    )


def enforce_identity(spec: ImageSpec, consents: ConsentRegistry, *,
                     requested_photoreal_name: Optional[str] = None) -> ImageSpec:
    """Return a copy of `spec` whose identity satisfies the guardrail.

    `requested_photoreal_name` is set only when the *user* explicitly asks for a
    photo-realistic named person. Model output can never trigger photoreal.
    """
    spec = spec.model_copy(deep=True)
    ident: Optional[Identity] = spec.identity()

    if ident is None:  # dashboard: no person depicted
        if requested_photoreal_name:
            raise ValueError("the dashboard format does not depict a person")
        return spec

    if requested_photoreal_name:
        name = requested_photoreal_name.strip()
        if is_placeholder(name):
            raise ValueError("a photo-realistic likeness needs a specific, consented client name")
        if not consents.is_confirmed(name):
            raise NeedsConfirmation(consent_question(name), name)
        ident.display_name = name
        ident.avatar = "photoreal"
        ident.consent_ref = consents.get(name)["confirmed_at"]
        return spec

    # No explicit, consented request: default to a placeholder identity.
    name_ok = is_placeholder(ident.display_name) or consents.is_confirmed(ident.display_name)
    if not name_ok:
        ident.display_name = PLACEHOLDER_NAME
    if ident.avatar == "photoreal":
        if is_placeholder(ident.display_name) or not consents.is_confirmed(ident.display_name):
            ident.avatar = "silhouette"
        else:
            # A consented name carried over from a previous, explicitly confirmed render.
            ident.consent_ref = consents.get(ident.display_name)["confirmed_at"]
    if ident.avatar != "photoreal":
        ident.consent_ref = None
    return spec


def assert_identity_safe(spec: ImageSpec, consents: ConsentRegistry) -> None:
    """Last-line check right before a prompt is sent to an image backend."""
    ident = spec.identity()
    if ident is None:
        return
    if ident.avatar == "photoreal" and not (
        not is_placeholder(ident.display_name) and consents.is_confirmed(ident.display_name)
    ):
        raise PermissionError("guardrail: photo-realistic avatar without recorded consent")
    if not is_placeholder(ident.display_name) and not consents.is_confirmed(ident.display_name):
        raise PermissionError("guardrail: named identity without recorded consent")
