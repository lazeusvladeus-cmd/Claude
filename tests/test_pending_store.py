from app.models import Direction, ParsedTransaction
from app import pending_store


def _parsed(**overrides):
    defaults = dict(amount=10, currency="USD", category="Other", description="coffee")
    defaults.update(overrides)
    return ParsedTransaction(**defaults)


def test_put_and_get_roundtrip():
    pid = pending_store.put(_parsed(), raw_text="10 usd coffee", source="text", user_id=1)
    entry = pending_store.get(pid, user_id=1)
    assert entry is not None
    assert entry.parsed.amount == 10


def test_get_denies_wrong_user():
    pid = pending_store.put(_parsed(), raw_text="x", source="text", user_id=1)
    assert pending_store.get(pid, user_id=999) is None


def test_pop_removes_entry():
    pid = pending_store.put(_parsed(), raw_text="x", source="text", user_id=1)
    entry = pending_store.pop(pid, user_id=1)
    assert entry is not None
    assert pending_store.get(pid, user_id=1) is None  # gone after pop


def test_update_category_mutates_in_place():
    pid = pending_store.put(_parsed(category="Other"), raw_text="x", source="text", user_id=1)
    entry = pending_store.update_category(pid, user_id=1, category="Groceries")
    assert entry.parsed.category == "Groceries"
    assert pending_store.get(pid, user_id=1).parsed.category == "Groceries"


def test_flip_direction_toggles():
    pid = pending_store.put(_parsed(), raw_text="x", source="text", user_id=1)
    entry = pending_store.flip_direction(pid, user_id=1)
    assert entry.parsed.direction == Direction.INCOME
    entry = pending_store.flip_direction(pid, user_id=1)
    assert entry.parsed.direction == Direction.EXPENSE


def test_unknown_pending_id_returns_none():
    assert pending_store.get("does-not-exist", user_id=1) is None
