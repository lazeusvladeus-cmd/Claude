import datetime as dt

from desk import journal

DAY = dt.date(2026, 10, 15)


def test_save_merges_and_keeps_review(tmp_path):
    journal.save_entry(tmp_path, DAY, {"checklist": {"market_state": "Balance"}}, files={"sheet.pdf": b"%PDF-1.4"})
    journal.save_entry(tmp_path, DAY, {"review": {"grade": "B", "followed_plan": "Yes", "mistakes": ["Chased / FOMO"]}})
    journal.save_entry(tmp_path, DAY, {"checklist": {"market_state": "Imbalance up (trending higher)"}})
    entry = journal.load_entry(tmp_path, DAY)
    assert entry["review"]["grade"] == "B"
    assert entry["checklist"]["market_state"].startswith("Imbalance")
    assert entry["date"] == "2026-10-15"
    assert (tmp_path / "2026-10-15" / "sheet.pdf").read_bytes() == b"%PDF-1.4"
    assert journal.list_entries(tmp_path) == [DAY]


def test_cyrillic_notes_round_trip(tmp_path):
    journal.save_entry(tmp_path, DAY, {"checklist": {"htf_context": "Баланс біля VAH"}})
    assert journal.load_entry(tmp_path, DAY)["checklist"]["htf_context"] == "Баланс біля VAH"


def test_screenshots_never_overwrite(tmp_path):
    a = journal.save_screenshot(tmp_path, DAY, "ATAS chart (1).PNG", b"one")
    b = journal.save_screenshot(tmp_path, DAY, "ATAS chart (1).PNG", b"two")
    assert a != b and a.read_bytes() == b"one" and b.read_bytes() == b"two"
    assert [p.name for p in journal.list_screenshots(tmp_path, DAY)] == ["ATAS_chart_1.png", "ATAS_chart_1_2.png"]


def test_damaged_file_is_kept_aside(tmp_path):
    folder = tmp_path / "2026-10-15"
    folder.mkdir()
    (folder / "prep.json").write_text("{not json", encoding="utf-8")
    assert "_unreadable" in journal.load_entry(tmp_path, DAY)
    journal.save_entry(tmp_path, DAY, {"review": {"grade": "A"}})
    assert journal.load_entry(tmp_path, DAY)["review"]["grade"] == "A"
    assert list(folder.glob("prep.unreadable-*.json"))


def test_stats(tmp_path):
    for i, (grade, followed, mistakes) in enumerate([("A", "Yes", []), ("C", "No", ["Chased / FOMO"]), ("B", "Yes", ["Chased / FOMO"])]):
        journal.save_entry(tmp_path, DAY - dt.timedelta(days=i), {"review": {"grade": grade, "followed_plan": followed, "mistakes": mistakes}})
    s = journal.stats(tmp_path)
    assert s["days_saved"] == 3 and s["days_reviewed"] == 3
    assert round(s["plan_followed_pct"]) == 67
    assert s["average_grade"] == "B"
    assert s["top_mistake"] == ("Chased / FOMO", 2)
