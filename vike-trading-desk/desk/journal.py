"""Daily journal: each session gets its own folder with the sheet, your plan and your review.

journal/
  2026-10-15/
    prep.json        levels, gap, context, events, your checklist and your review
    sheet.pdf        prep sheet, one page per instrument
    sheet_NQ.png
    sheet_ES.png
    screenshots/     ATAS screenshots you attach when reviewing
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from collections import Counter
from pathlib import Path

ENTRY_FILE = "prep.json"
GRADE_POINTS = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}


def entry_dir(root: Path, day: dt.date) -> Path:
    return Path(root) / day.isoformat()


def load_entry(root: Path, day: dt.date) -> dict:
    path = entry_dir(root, day) / ENTRY_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"_unreadable": str(path)}


def save_entry(root: Path, day: dt.date, updates: dict, files: dict[str, bytes] | None = None) -> Path:
    """Merge `updates` into the day's prep.json (keeps earlier keys, e.g. the review) and write files."""
    folder = entry_dir(root, day)
    folder.mkdir(parents=True, exist_ok=True)
    data = load_entry(root, day)
    if "_unreadable" in data:  # keep a damaged file instead of silently replacing it
        broken = folder / ENTRY_FILE
        broken.replace(folder / f"prep.unreadable-{dt.datetime.now():%Y%m%d-%H%M%S}.json")
        data = {}
    data.update(updates)
    data["date"] = day.isoformat()
    _write_atomic(folder / ENTRY_FILE, json.dumps(data, indent=2, ensure_ascii=False, default=str).encode("utf-8"))
    for name, content in (files or {}).items():
        _write_atomic(folder / name, content)
    return folder


def _write_atomic(path: Path, content: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(content)
    os.replace(tmp, path)


def list_entries(root: Path) -> list[dt.date]:
    root = Path(root)
    if not root.exists():
        return []
    days = []
    for child in root.iterdir():
        if child.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", child.name) and (child / ENTRY_FILE).exists():
            try:
                days.append(dt.date.fromisoformat(child.name))
            except ValueError:
                continue
    return sorted(days, reverse=True)


def save_screenshot(root: Path, day: dt.date, filename: str, content: bytes) -> Path:
    folder = entry_dir(root, day) / "screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    stem, suffix = os.path.splitext(filename)
    stem = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("_") or "screenshot"
    suffix = suffix.lower() if suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"} else ".png"
    path = folder / f"{stem}{suffix}"
    n = 2
    while path.exists():
        path = folder / f"{stem}_{n}{suffix}"
        n += 1
    path.write_bytes(content)
    return path


def list_screenshots(root: Path, day: dt.date) -> list[Path]:
    folder = entry_dir(root, day) / "screenshots"
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"})


def stats(root: Path) -> dict:
    """Simple numbers for the review habit: how many days, plan discipline, grades, common mistakes."""
    days = list_entries(root)
    reviews = [r for r in (load_entry(root, d).get("review") for d in days) if r]
    followed = [r.get("followed_plan") for r in reviews if r.get("followed_plan")]
    grades = [GRADE_POINTS[r["grade"]] for r in reviews if r.get("grade") in GRADE_POINTS]
    mistakes = Counter(m for r in reviews for m in r.get("mistakes", []) if m != "None today")
    return {
        "days_saved": len(days),
        "days_reviewed": len(reviews),
        "plan_followed_pct": (100 * sum(f == "Yes" for f in followed) / len(followed)) if followed else None,
        "average_grade": _grade_letter(sum(grades) / len(grades)) if grades else None,
        "top_mistake": mistakes.most_common(1)[0] if mistakes else None,
    }


def _grade_letter(points: float) -> str:
    return min(GRADE_POINTS, key=lambda g: abs(GRADE_POINTS[g] - points))
