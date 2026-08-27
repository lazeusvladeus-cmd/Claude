import pytest
from pydantic import ValidationError

from app.models import CATEGORIES, Direction, ParsedTransaction, Transaction, category_label


def test_parsed_transaction_rejects_nonpositive_amount():
    with pytest.raises(ValidationError):
        ParsedTransaction(amount=0, currency="usd", category="Other", description="x")
    with pytest.raises(ValidationError):
        ParsedTransaction(amount=-5, currency="usd", category="Other", description="x")


def test_parsed_transaction_normalizes_currency_case():
    p = ParsedTransaction(amount=10, currency="usd", category="Other", description="x")
    assert p.currency == "USD"


def test_parsed_transaction_unknown_category_falls_back_to_other():
    p = ParsedTransaction(amount=10, currency="USD", category="Crypto Yacht Fund", description="x")
    assert p.category == "Other"


def test_parsed_transaction_rejects_bad_currency_codes():
    with pytest.raises(ValidationError):
        ParsedTransaction(amount=10, currency="US", category="Other", description="x")
    with pytest.raises(ValidationError):
        ParsedTransaction(amount=10, currency="US1", category="Other", description="x")


def test_category_label_covers_every_category():
    for cat in CATEGORIES:
        label = category_label(cat)
        assert cat in label
        assert len(label) > len(cat)  # has an emoji prefix


@pytest.mark.parametrize(
    "malicious_text",
    [
        '=HYPERLINK("http://evil.example","click")',
        "+1+1",
        "-cmd|' /C calc'!A0",
        "@SUM(1,1)",
    ],
)
def test_transaction_to_row_neutralizes_formula_injection(malicious_text):
    tx = Transaction(
        amount=10,
        currency="USD",
        category="Other",
        description=malicious_text,
        merchant=malicious_text,
        raw_text=malicious_text,
    )
    row = tx.to_row()
    header = Transaction.header_row()
    for field_name in ("description", "merchant", "raw_text"):
        value = row[header.index(field_name)]
        assert value.startswith("'"), f"{field_name} was not neutralized: {value!r}"


def test_transaction_to_row_leaves_normal_text_untouched():
    tx = Transaction(amount=10, currency="USD", category="Other", description="Coffee with Anna", raw_text="text")
    row = tx.to_row()
    header = Transaction.header_row()
    assert row[header.index("description")] == "Coffee with Anna"


def test_transaction_direction_roundtrips_from_sheet_row_string():
    tx = Transaction(amount=1, currency="USD", category="Other", description="x", direction=Direction.INCOME)
    assert tx.to_row()[Transaction.header_row().index("direction")] == "income"
