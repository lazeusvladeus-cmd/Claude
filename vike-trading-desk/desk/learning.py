"""Learning roadmap data: modules (roadmap.toml), links (links.csv + my_links.csv), progress (JSON).

- learning/roadmap.toml   module texts and the week-by-week plan (you can edit it)
- learning/links.csv      resource links I checked (they loaded and matched their title)
- learning/my_links.csv   links YOU add (in the app or with Excel / Notepad)
- data/learning_progress.json   your checkboxes, notes and start date (never overwritten by updates)
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

LINK_COLUMNS = ["module", "title", "url", "kind", "source", "note"]


class RoadmapError(Exception):
    """A problem in roadmap.toml or a links file, phrased so the user knows what to fix."""


@dataclass
class Link:
    module: str
    title: str
    url: str
    kind: str = ""
    source: str = ""
    note: str = ""
    mine: bool = False

    @property
    def key(self) -> str:
        return f"link|{self.module}|{self.url}"


@dataclass
class Module:
    id: str
    track: str
    title: str
    weeks: list[int]
    learn: str
    why: str
    exercise: str
    links: list[Link] = field(default_factory=list)

    @property
    def week_label(self) -> str:
        if not self.weeks:
            return ""
        if len(self.weeks) == 1:
            return f"week {self.weeks[0]}"
        return f"weeks {min(self.weeks)}-{max(self.weeks)}"


@dataclass
class Roadmap:
    title: str
    stages: list[dict]
    week_focus: dict[int, str]
    modules: list[Module]
    problems: list[str] = field(default_factory=list)

    def module(self, module_id: str) -> Module | None:
        return next((m for m in self.modules if m.id == module_id), None)

    def track(self, name: str) -> list[Module]:
        return [m for m in self.modules if m.track.lower() == name.lower()]

    def modules_for_week(self, week: int) -> list[Module]:
        return [m for m in self.modules if week in m.weeks]

    def stages_for_week(self, week: int) -> list[str]:
        return [s["name"] for s in self.stages if s["weeks"][0] <= week <= s["weeks"][1]]

    @property
    def total_weeks(self) -> int:
        weeks = [w for m in self.modules for w in m.weeks] + list(self.week_focus)
        return max(weeks) if weeks else 12


def load_links(path: Path, mine: bool = False) -> tuple[list[Link], list[str]]:
    path = Path(path)
    if not path.exists():
        return [], []
    links, problems = [], []
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            for n, row in enumerate(csv.DictReader(f), start=2):
                url = (row.get("url") or "").strip()
                module = (row.get("module") or "").strip().upper()
                if not url and not module:
                    continue
                if not url.lower().startswith(("http://", "https://")):
                    problems.append(f"{path.name} line {n}: the url must start with https:// ({url!r}).")
                    continue
                links.append(
                    Link(
                        module=module,
                        title=(row.get("title") or url).strip(),
                        url=url,
                        kind=(row.get("kind") or "").strip(),
                        source=(row.get("source") or "").strip(),
                        note=(row.get("note") or "").strip(),
                        mine=mine,
                    )
                )
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        problems.append(f"Couldn't read {path.name}: {exc}")
    return links, problems


def load_roadmap(learning_dir: Path) -> Roadmap:
    learning_dir = Path(learning_dir)
    path = learning_dir / "roadmap.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise RoadmapError(f"The roadmap file is missing: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise RoadmapError(f"roadmap.toml has a typo: {exc}. Check the \"\"\" quotes around the texts.") from None

    plan = data.get("plan", {})
    stages = []
    for stage in plan.get("stages", []):
        weeks = stage.get("weeks", [1, 1])
        stages.append({"name": stage.get("name", ""), "detail": stage.get("detail", ""), "weeks": (int(weeks[0]), int(weeks[-1]))})
    week_focus = {int(w["week"]): str(w.get("focus", "")) for w in data.get("weeks", []) if "week" in w}

    modules = []
    for raw in data.get("modules", []):
        if "id" not in raw:
            continue
        modules.append(
            Module(
                id=str(raw["id"]).strip().upper(),
                track=str(raw.get("track", "Trading")),
                title=str(raw.get("title", raw["id"])),
                weeks=[int(w) for w in raw.get("weeks", [])],
                learn=str(raw.get("learn", "")).strip(),
                why=str(raw.get("why", "")).strip(),
                exercise=str(raw.get("exercise", "")).strip(),
            )
        )

    problems: list[str] = []
    checked, p1 = load_links(learning_dir / "links.csv")
    mine, p2 = load_links(learning_dir / "my_links.csv", mine=True)
    problems += p1 + p2
    by_id = {m.id: m for m in modules}
    for link in checked + mine:
        if link.module in by_id:
            by_id[link.module].links.append(link)
        else:
            problems.append(f"Link {link.title!r} points to an unknown module {link.module!r}.")
    return Roadmap(plan.get("title", "Learning roadmap"), stages, week_focus, modules, problems)


def add_my_link(learning_dir: Path, module: str, title: str, url: str, note: str = "") -> Link:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("The link must start with https:// (copy it from your browser's address bar).")
    path = Path(learning_dir) / "my_links.csv"
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LINK_COLUMNS)
        if new_file:
            writer.writeheader()
        link = Link(module.upper(), title.strip() or url, url, "My link", "added by me", note.strip(), mine=True)
        writer.writerow({c: getattr(link, c) for c in LINK_COLUMNS})
    return link


class Progress:
    """Your checkboxes, notes and plan start date, saved as JSON after every change."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = {"start_date": None, "done": {}, "notes": {}}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except (OSError, ValueError):
                self.path.replace(self.path.with_name(f"learning_progress.unreadable-{dt.datetime.now():%Y%m%d-%H%M%S}.json"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def is_done(self, key: str) -> bool:
        return bool(self.data["done"].get(key))

    def set_done(self, key: str, value: bool) -> None:
        if value:
            self.data["done"][key] = dt.date.today().isoformat()
        else:
            self.data["done"].pop(key, None)
        self.save()

    def note(self, module_id: str) -> str:
        return self.data["notes"].get(module_id, "")

    def set_note(self, module_id: str, text: str) -> None:
        self.data["notes"][module_id] = text
        self.save()

    @property
    def start_date(self) -> dt.date | None:
        value = self.data.get("start_date")
        try:
            return dt.date.fromisoformat(value) if value else None
        except ValueError:
            return None

    def set_start_date(self, day: dt.date) -> None:
        self.data["start_date"] = day.isoformat()
        self.save()


def exercise_key(module_id: str) -> str:
    return f"exercise|{module_id}"


def complete_key(module_id: str) -> str:
    return f"module|{module_id}"


def module_progress(module: Module, progress: Progress) -> float:
    """Share of the module's items ticked: each link, the exercise, and 'module complete'."""
    if progress.is_done(complete_key(module.id)):
        return 1.0
    items = [link.key for link in module.links] + [exercise_key(module.id)]
    return sum(progress.is_done(k) for k in items) / (len(items) + 1)


def current_week(start: dt.date | None, today: dt.date) -> int | None:
    """Week 1 starts on the start date; None before it starts."""
    if start is None or today < start:
        return None
    return (today - start).days // 7 + 1


def next_monday(today: dt.date) -> dt.date:
    return today + dt.timedelta(days=(7 - today.weekday()) % 7 or 7) if today.weekday() else today
