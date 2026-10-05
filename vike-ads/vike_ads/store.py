"""File-based storage: research reports, concepts, generated images (under data/)."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import AdVariant, Concept, ResearchReport

_WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = {"the", "a", "an", "for", "of", "and", "to", "ad", "ads", "image", "concept", "idea",
             "with", "my", "our", "that", "this", "one", "just", "please", "generate", "make"}
RECENT_WORDS = {"it", "that", "latest", "last", "previous", "this", "recent", "same"}


def new_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(2)}"


def _tokens(s: str) -> set[str]:
    return {w for w in _WORD.findall(s.lower()) if w not in STOPWORDS and len(w) > 1}


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        for sub in ("research", "concepts", "images"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    @property
    def consent_file(self) -> Path:
        return self.root / "consents.json"

    @property
    def images_dir(self) -> Path:
        return self.root / "images"

    # ---- research
    def save_report(self, r: ResearchReport) -> Path:
        path = self.root / "research" / f"{r.id}.json"
        path.write_text(r.model_dump_json(indent=2), encoding="utf-8")
        return path

    def list_reports(self) -> list[ResearchReport]:
        reports = [ResearchReport.model_validate_json(p.read_text(encoding="utf-8"))
                   for p in (self.root / "research").glob("*.json")]
        return sorted(reports, key=lambda r: r.created_at, reverse=True)

    def get_report(self, rid: str) -> Optional[ResearchReport]:
        p = self.root / "research" / f"{rid}.json"
        return ResearchReport.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None

    def latest_report(self) -> Optional[ResearchReport]:
        reports = self.list_reports()
        return reports[0] if reports else None

    # ---- concepts
    def save_concept(self, c: Concept) -> Path:
        path = self.root / "concepts" / f"{c.id}.json"
        path.write_text(c.model_dump_json(indent=2), encoding="utf-8")
        return path

    def get_concept(self, cid: str) -> Optional[Concept]:
        p = self.root / "concepts" / f"{cid.lower()}.json"
        return Concept.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None

    def list_concepts(self) -> list[Concept]:
        cs = [Concept.model_validate_json(p.read_text(encoding="utf-8"))
              for p in (self.root / "concepts").glob("*.json")]
        return sorted(cs, key=lambda c: c.created_at, reverse=True)

    def find_variants(self, ref: str) -> tuple[list[tuple[Concept, AdVariant]], list[tuple[Concept, AdVariant]]]:
        """Resolve a user reference to stored variants.

        Returns (matches, candidates): `matches` is the confident resolution (may be
        several variants of one concept); if empty, `candidates` lists the closest
        alternatives so the caller can ask instead of inventing a new concept.
        """
        ref = ref.strip().strip('"\'')
        concepts = self.list_concepts()
        if not concepts:
            return [], []

        # 1. Exact IDs (variant id "c-...-B" or concept id "c-...")
        for c in concepts:
            for v in c.variants:
                if v.id.lower() == ref.lower():
                    return [(c, v)], []
            if c.id.lower() == ref.lower():
                return [(c, v) for v in c.variants], []
        m = re.search(r"\b(c-\d{8}-[0-9a-f]{4})(?:-([a-z]))?\b", ref.lower())
        if m:
            c = self.get_concept(m.group(1))
            if c:
                if m.group(2):
                    v = c.variant(f"{c.id}-{m.group(2).upper()}")
                    return ([(c, v)], []) if v else ([], [(c, x) for x in c.variants])
                return [(c, v) for v in c.variants], []

        # Optional "variant B" qualifier
        vm = re.search(r"\bvariant\s+([a-z])\b", ref.lower())
        wanted_label = vm.group(1).upper() if vm else None

        def pick(c: Concept) -> list[tuple[Concept, AdVariant]]:
            vs = [v for v in c.variants if not wanted_label or v.label == wanted_label]
            return [(c, v) for v in vs]

        # 2. "the last one", "it", "" -> most recent concept
        toks = _tokens(re.sub(r"\bvariant\s+[a-z]\b", " ", ref.lower()))
        if not toks or toks <= RECENT_WORDS:
            return pick(concepts[0]), []

        # 3. Fuzzy token overlap against name/request/ideas
        scored = []
        for c in concepts:
            hay = _tokens(" ".join([c.name, c.request] + [v.idea for v in c.variants]))
            name_hits = len(toks & _tokens(c.name + " " + c.request))
            score = (len(toks & hay) + name_hits) / (len(toks) + 1)
            scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        runner = scored[1][0] if len(scored) > 1 else 0.0
        if best_score >= 0.5 and best_score >= runner * 1.3 + 1e-9:
            return pick(best), []
        cands = [(c, c.variants[0]) for s, c in scored[:5] if s > 0 and c.variants]
        return [], cands

    # ---- images
    def image_path(self, variant_id: str, ext: str) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        return self.images_dir / f"{variant_id}-{stamp}.{ext}"
