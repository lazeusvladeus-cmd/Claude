"""Тести шару роботи з БД (src/db.py)."""

from __future__ import annotations

import pytest

from src.db import (
    add_manual_data,
    count_all_leads,
    get_lead,
    get_leads_by_status,
    get_leads_by_statuses,
    get_status_counts,
    init_db,
    mark_needs_manual_screenshot,
    mark_sent,
    save_analysis,
    save_draft,
    save_enrichment,
    save_presentation,
    save_reply,
    update_status,
    upsert_lead,
)


def _lead_data(**overrides):
    data = {
        "place_id": "p1",
        "name": "Тест",
        "address": "адреса",
        "phone": "+380000000",
        "website": None,
        "social_links": "[]",
        "rating": 4.5,
        "reviews_count": 10,
        "category": "кав'ярні",
        "location": "Львів",
    }
    data.update(overrides)
    return data


class TestUpsertLead:
    def test_creates_new_lead(self, db_path) -> None:
        lead_id, created = upsert_lead(db_path, _lead_data())
        assert created is True
        lead = get_lead(db_path, lead_id)
        assert lead.name == "Тест"
        assert lead.status == "new"

    def test_dedup_on_same_place_id(self, db_path) -> None:
        id1, created1 = upsert_lead(db_path, _lead_data(place_id="dup-1"))
        id2, created2 = upsert_lead(db_path, _lead_data(place_id="dup-1", name="Інша назва"))
        assert created1 is True
        assert created2 is False
        assert id1 == id2
        assert count_all_leads(db_path) == 1


class TestStatusTransitions:
    def test_full_lifecycle(self, db_path) -> None:
        lead_id, _ = upsert_lead(db_path, _lead_data())
        assert get_lead(db_path, lead_id).status == "new"

        save_enrichment(db_path, lead_id, {"source": "website"})
        assert get_lead(db_path, lead_id).status == "enriched"

        save_analysis(db_path, lead_id, ["Слабке місце 1"])
        lead = get_lead(db_path, lead_id)
        assert lead.status == "analyzed"
        assert lead.weaknesses == ["Слабке місце 1"]

        save_draft(db_path, lead_id, draft_id="d1", thread_id="t1", subject="S", body="B")
        lead = get_lead(db_path, lead_id)
        assert lead.status == "drafted"
        assert lead.draft_id == "d1"

        mark_sent(db_path, lead_id, "2026-01-01T00:00:00+00:00")
        assert get_lead(db_path, lead_id).status == "sent"

        save_reply(db_path, lead_id, "Дякую, цікаво!")
        lead = get_lead(db_path, lead_id)
        assert lead.status == "replied"
        assert lead.reply_text == "Дякую, цікаво!"

        save_presentation(db_path, lead_id, presentation_path="/tmp/p.pptx", reply_draft_id="rd1")
        lead = get_lead(db_path, lead_id)
        assert lead.status == "presented"
        assert lead.presentation_path == "/tmp/p.pptx"

    def test_needs_manual_screenshot_flow(self, db_path) -> None:
        lead_id, _ = upsert_lead(db_path, _lead_data(place_id="p2"))
        mark_needs_manual_screenshot(db_path, lead_id)
        assert get_lead(db_path, lead_id).status == "needs_manual_screenshot"

        add_manual_data(db_path, lead_id, "Текст зі скріншоту Instagram")
        lead = get_lead(db_path, lead_id)
        assert lead.status == "enriched"
        assert lead.manual_screenshot_text == "Текст зі скріншоту Instagram"
        assert lead.enrichment["source"] == "manual_screenshot"

    def test_add_manual_data_on_missing_lead_raises(self, db_path) -> None:
        with pytest.raises(ValueError):
            add_manual_data(db_path, 9999, "текст")

    def test_update_status_rejects_unknown_status(self, db_path) -> None:
        lead_id, _ = upsert_lead(db_path, _lead_data(place_id="p3"))
        with pytest.raises(ValueError):
            update_status(db_path, lead_id, "not_a_real_status")


class TestQueries:
    def test_get_leads_by_status(self, db_path) -> None:
        upsert_lead(db_path, _lead_data(place_id="a"))
        id_b, _ = upsert_lead(db_path, _lead_data(place_id="b"))
        save_enrichment(db_path, id_b, {})

        new_leads = get_leads_by_status(db_path, "new")
        enriched_leads = get_leads_by_status(db_path, "enriched")
        assert len(new_leads) == 1
        assert len(enriched_leads) == 1

    def test_get_leads_by_statuses(self, db_path) -> None:
        id_a, _ = upsert_lead(db_path, _lead_data(place_id="a"))
        id_b, _ = upsert_lead(db_path, _lead_data(place_id="b"))
        save_enrichment(db_path, id_b, {})

        results = get_leads_by_statuses(db_path, ("new", "enriched"))
        assert {lead.id for lead in results} == {id_a, id_b}

    def test_get_status_counts_includes_zero_statuses(self, db_path) -> None:
        upsert_lead(db_path, _lead_data(place_id="a"))
        counts = get_status_counts(db_path)
        assert counts["new"] == 1
        assert counts["presented"] == 0

    def test_get_lead_returns_none_for_missing_id(self, db_path) -> None:
        assert get_lead(db_path, 12345) is None

    def test_count_all_leads_on_empty_db(self, tmp_path) -> None:
        path = str(tmp_path / "empty.db")
        init_db(path)
        assert count_all_leads(path) == 0

    def test_init_db_is_idempotent(self, db_path) -> None:
        upsert_lead(db_path, _lead_data(place_id="a"))
        init_db(db_path)  # повторний виклик не повинен стирати дані
        assert count_all_leads(db_path) == 1
