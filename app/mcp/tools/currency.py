"""MCP currency tool backed by a daily reference-rate API."""

from datetime import date as Date
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from app.config.settings import settings


def _validate_currency_code(value: str, field_name: str) -> str:
    code = value.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError(f"{field_name} must be a 3-letter ISO currency code")
    return code


def _validate_date(value: str) -> str:
    requested = value.strip()
    if not requested or requested.casefold() == "latest":
        return "latest"

    try:
        Date.fromisoformat(requested)
    except ValueError as exc:
        raise ValueError("currency_date must be 'latest' or YYYY-MM-DD") from exc

    return requested


def _validate_amount(value: float) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("amount must be a valid number") from exc

    if not amount.is_finite():
        raise ValueError("amount must be finite")

    return amount


def get_exchange_rate(
    currency_from: str = "USD",
    currency_to: str = "EUR",
    amount: float = 1,
    currency_date: str = "latest",
) -> dict[str, Any]:
    """Fetch a daily reference rate and convert the requested amount."""

    base = _validate_currency_code(currency_from, "currency_from")
    target = _validate_currency_code(currency_to, "currency_to")
    requested_date = _validate_date(currency_date)
    converted_input = _validate_amount(amount)

    if base == target:
        rate = Decimal("1")
        effective_date = requested_date
    else:
        endpoint = f"{settings.currency_api_url.rstrip('/')}/rate/{base.lower()}/{target.lower()}"
        params = {} if requested_date == "latest" else {"date": requested_date}

        try:
            response = requests.get(
                endpoint,
                params=params,
                timeout=settings.currency_api_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise RuntimeError("Currency rate provider is unavailable") from exc
        except ValueError as exc:
            raise RuntimeError("Currency rate provider returned invalid JSON") from exc

        try:
            rate = Decimal(str(payload["rate"]))
            effective_date = str(payload["date"])
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise RuntimeError("Currency rate provider returned an invalid response") from exc

        if not rate.is_finite():
            raise RuntimeError("Currency rate provider returned a non-finite rate")

    converted_amount = converted_input * rate

    return {
        "amount": str(converted_input),
        "base": base,
        "quote": target,
        "rate": str(rate),
        "converted_amount": str(converted_amount.quantize(Decimal("0.01"))),
        "date": effective_date,
        "source": settings.currency_api_url,
    }
