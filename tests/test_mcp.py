import pytest

from app.mcp.tools.currency import get_exchange_rate


def test_same_currency_conversion_is_deterministic():
    result = get_exchange_rate("USD", "USD", amount=100)

    assert result["rate"] == "1"
    assert result["converted_amount"] == "100.00"


def test_currency_codes_are_validated():
    with pytest.raises(ValueError):
        get_exchange_rate("US", "EUR")


def test_currency_date_is_validated():
    with pytest.raises(ValueError):
        get_exchange_rate("USD", "EUR", currency_date="not-a-date")


def test_amount_must_be_finite():
    with pytest.raises(ValueError):
        get_exchange_rate("USD", "EUR", amount=float("inf"))
