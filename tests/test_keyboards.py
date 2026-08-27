from app.keyboards import category_picker_kb, confirm_transaction_kb, main_menu_kb
from app.models import CATEGORIES


def test_category_picker_marks_current_selection():
    kb = category_picker_kb("abc1234567", current_category="Groceries")
    all_text = [btn.text for row in kb.inline_keyboard for btn in row]
    groceries_btn = next(t for t in all_text if "Groceries" in t)
    others = [t for t in all_text if "Groceries" not in t and t != "« Back"]
    assert groceries_btn.startswith("✓")
    assert not any(t.startswith("✓") for t in others)


def test_category_picker_has_a_button_per_category_plus_back():
    kb = category_picker_kb("abc1234567")
    all_text = [btn.text for row in kb.inline_keyboard for btn in row]
    assert len(all_text) == len(CATEGORIES) + 1  # + Back button
    assert "« Back" in all_text


def test_callback_data_always_fits_telegram_64_byte_limit():
    pending_id = "a" * 10  # our pending IDs are 10 hex chars
    kb = category_picker_kb(pending_id, current_category="Savings & Investments")
    for row in kb.inline_keyboard:
        for btn in row:
            assert btn.callback_data is not None
            assert len(btn.callback_data.encode("utf-8")) <= 64, btn.callback_data

    for kb2 in (confirm_transaction_kb(pending_id),):
        for row in kb2.inline_keyboard:
            for btn in row:
                assert len(btn.callback_data.encode("utf-8")) <= 64, btn.callback_data


def test_main_menu_kb_is_resizable_and_persistent():
    kb = main_menu_kb()
    assert kb.resize_keyboard is True
    assert kb.is_persistent is True
    button_count = sum(len(row) for row in kb.keyboard)
    assert button_count == 5
