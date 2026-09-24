"""Markdown rendering. A concept variant renders as exactly four parts — no more, no less."""

from __future__ import annotations

import os
from pathlib import Path

from .models import AdVariant, Concept, ResearchReport


def _rel(path: str) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:
        return path


def part4(v: AdVariant) -> str:
    lines = ["**4. Generated image**", f"Format: {v.image_spec.format.label}"]
    if v.image:
        lines.append(f"File: {_rel(v.image.path)}")
    else:
        lines.append(f"Not rendered yet — run: vike-ads image {v.id}")
    return "\n".join(lines)


def variant_md(c: Concept, v: AdVariant) -> str:
    t = v.on_image_text
    m = v.meta
    on_image = t.headline + (f"\n{t.subheadline}" if t.subheadline else "")
    meta = [f"Primary text:\n{m.primary_text}", f"Headline: {m.headline}"]
    if m.description:
        meta.append(f"Description: {m.description}")
    meta.append(f"Call to action: {m.cta}")
    return "\n\n".join([
        f"### {v.id} · {c.name} — variant {v.label}",
        "**1. The idea**\n" + v.idea,
        "**2. On-image text**\n```text\n" + on_image + "\n```",
        "**3. Meta Ads Manager fields**\n```text\n" + "\n\n".join(meta) + "\n```",
        part4(v),
    ])


def concept_md(c: Concept) -> str:
    return "\n\n---\n\n".join(variant_md(c, v) for v in c.variants)


def image_only_md(c: Concept, v: AdVariant) -> str:
    return f"### {v.id} · {c.name} — variant {v.label}\n\n" + part4(v)


def report_md(r: ResearchReport) -> str:
    out = [f"## Research: {r.topic}", f"_{r.id} · {r.created_at:%Y-%m-%d %H:%M} UTC_"]
    if not r.findings:
        out.append("No verified findings.")
    for i, f in enumerate(r.findings, 1):
        cites = ", ".join(
            f"[{s.title or s.url}]({s.url})" for s in (r.source(x) for x in f.source_ids) if s)
        fmts = ", ".join(x.label for x in f.formats)
        out.append(
            f"**{i}. {f.trend}**" + (f"  _(informs: {fmts})_" if fmts else "") + f"\n{f.summary}"
            + (f"\n- Evidence: {f.evidence}" if f.evidence else "")
            + f"\n- Sources: {cites}\n- Verification: {f.verification} — {', '.join(f.providers)}"
        )
    if r.unverified_leads:
        out.append("### Unverified leads (DeepSeek-only — NOT verified, not used for ideas)")
        out += [f"- {f.trend}: {f.summary} _({f.verification_note})_" for f in r.unverified_leads]
    if r.manual_links:
        out.append("### Check by hand in the Meta Ad Library")
        out += [f"- [{s.title}]({s.url})" for s in r.manual_links]
    if r.notes:
        out.append("### Run notes")
        out += [f"- {n}" for n in r.notes]
    return "\n\n".join(out)


def concept_list_md(concepts: list[Concept]) -> str:
    if not concepts:
        return "No concepts yet. Try: vike-ads idea \"...\""
    rows = []
    for c in concepts:
        for v in c.variants:
            img = "rendered" if v.image and Path(v.image.path).exists() else "no image"
            rows.append(f"- {v.id} · {c.name} · {v.image_spec.format.label} · {img}")
    return "\n".join(rows)
