from app.mcp.tools.currency import get_exchange_rate
import pytest


def test_currency_rate_is_deterministic():
    assert get_exchange_rate("USD", "EUR")["rates"]["EUR"] == 0.85


def test_same_currency_rate_is_one():
    assert get_exchange_rate("USD", "USD")["rates"]["USD"] == 1.0


def test_currency_codes_are_validated():
    with pytest.raises(ValueError):
        get_exchange_rate("US", "EUR")
