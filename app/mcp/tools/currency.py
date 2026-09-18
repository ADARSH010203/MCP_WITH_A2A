"""Currency exchange-rate tool used by the MCP server."""

from typing import Any


def get_exchange_rate(
    currency_from: str = "USD",
    currency_to: str = "EUR",
    currency_date: str = "latest",
) -> dict[str, Any]:
    """Return a deterministic demo exchange rate.

    The project intentionally uses a placeholder rate instead of a live
    financial data provider, so results are reproducible during demos.
    """
    base = currency_from.strip().upper()
    target = currency_to.strip().upper()
    date = currency_date.strip() or "latest"

    if len(base) != 3 or len(target) != 3:
        raise ValueError("currency_from and currency_to must be 3-letter currency codes")

    rate = 1.0 if base == target else 0.85

    return {
        "amount": 1,
        "base": base,
        "date": date,
        "rates": {target: rate},
    }
