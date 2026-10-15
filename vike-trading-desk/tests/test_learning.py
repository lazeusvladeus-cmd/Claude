import datetime as dt
from pathlib import Path

from desk.learning import Progress, add_my_link, current_week, exercise_key, load_roadmap, module_progress, next_monday

LEARNING = Path(__file__).resolve().parents[1] / "learning"


def test_shipped_roadmap_is_complete():
    roadmap = load_roadmap(LEARNING)
    assert roadmap.problems == []
    assert [m.id for m in roadmap.track("Trading")] == [f"T{i}" for i in range(1, 13)]
    assert [m.id for m in roadmap.track("Equity")] == [f"E{i}" for i in range(1, 6)]
    for m in roadmap.modules:
        assert m.learn and m.why and m.exercise and m.weeks, m.id
        assert 2 <= len(m.links) <= 4, (m.id, len(m.links))
        assert all(link.url.startswith("https://") for link in m.links)
    assert all(roadmap.modules_for_week(w) for w in range(1, 13))
    assert roadmap.total_weeks == 12
    assert roadmap.stages_for_week(9) == ["Manual backtest in ATAS", "Coded backtest"]
    assert any("aleks" in link.url.lower() for link in roadmap.module("T6").links)


def test_progress_and_my_links(tmp_path):
    for name in ("roadmap.toml", "links.csv"):
        (tmp_path / name).write_bytes((LEARNING / name).read_bytes())
    add_my_link(tmp_path, "T4", "My footprint video", "https://example.org/video", "great")
    roadmap = load_roadmap(tmp_path)
    t4 = roadmap.module("T4")
    assert t4.links[-1].mine and t4.links[-1].title == "My footprint video"

    progress = Progress(tmp_path / "progress.json")
    assert module_progress(t4, progress) == 0
    progress.set_done(t4.links[0].key, True)
    progress.set_done(exercise_key("T4"), True)
    progress.set_note("T4", "Absorption at VAH works best with negative gamma")
    again = Progress(tmp_path / "progress.json")
    assert again.is_done(t4.links[0].key) and again.note("T4").startswith("Absorption")
    assert 0 < module_progress(t4, again) < 1


def test_bad_link_rejected(tmp_path):
    try:
        add_my_link(tmp_path, "T1", "x", "www.no-scheme.com")
    except ValueError as exc:
        assert "https://" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_week_numbers():
    start = dt.date(2026, 10, 19)
    assert current_week(start, dt.date(2026, 10, 18)) is None
    assert current_week(start, dt.date(2026, 10, 19)) == 1
    assert current_week(start, dt.date(2026, 10, 26)) == 2
    assert next_monday(dt.date(2026, 10, 15)) == dt.date(2026, 10, 19)
    assert next_monday(dt.date(2026, 10, 19)) == dt.date(2026, 10, 19)
