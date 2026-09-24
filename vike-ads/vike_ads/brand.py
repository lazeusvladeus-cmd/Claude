"""Shared brand context loaded from config/brand.json and referenced by every agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Brand:
    raw: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "Brand":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @property
    def name(self) -> str:
        return self.raw["agency"]["name"]

    @property
    def colors(self) -> dict[str, str]:
        return self.raw["colors"]

    @property
    def offer_facts(self) -> list[str]:
        return list(self.raw["agency"].get("offer_facts", []))

    @property
    def proof_points(self) -> list[str]:
        return list(self.raw["agency"].get("proof_points", []))

    @property
    def real_client_names(self) -> list[str]:
        return list(self.raw["agency"].get("real_client_names", []))

    def facts(self) -> list[str]:
        """Claims the copy may make without further verification (the agency's own facts)."""
        return self.offer_facts + self.proof_points

    def prompt_block(self) -> str:
        a = self.raw["agency"]
        facts = "\n".join(f"  [F{i}] {f}" for i, f in enumerate(self.facts()))
        c = self.colors
        t = self.raw["typography"]
        comp = self.raw["components"]
        return (
            f"AGENCY: {a['name']} — {a['what_we_do']}. Markets: {', '.join(a.get('markets', []))}.\n"
            f"VERIFIED AGENCY FACTS (the only agency claims you may use; cite as F<n>):\n{facts}\n"
            f"BRAND PALETTE: primary {c['primary_accent']}, secondary {c['secondary_accent']}, "
            f"ink {c['ink']}, muted {c['muted_body']}, light bg {c['light_background']}, "
            f"hairline {c['hairline_border']}, badge bg {c['badge_background']}.\n"
            f"TYPOGRAPHY: headline {t['headline']}; labels {t['label']}.\n"
            f"COMPONENTS: buttons {comp['buttons']}; cards {comp['cards']}."
        )
