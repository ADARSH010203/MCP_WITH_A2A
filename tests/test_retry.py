import pytest

from app.a2a.client import A2AClient
from app.a2a.models import A2AClientHTTPError
from app.routing.retry import RetryPolicy


def test_retry_policy_uses_exponential_delay_with_bounded_jitter():
    policy = RetryPolicy(
        max_retries=3,
        base_delay_seconds=1.0,
        max_delay_seconds=5.0,
        jitter_ratio=0.25,
        random_uniform=lambda low, high: high,
    )

    assert policy.delay(0) == pytest.approx(1.25)
    assert policy.delay(1) == pytest.approx(2.5)
    assert policy.delay(3) == 5.0


def test_retry_policy_respects_retry_after_without_exceeding_cap():
    policy = RetryPolicy(
        max_retries=2,
        base_delay_seconds=1.0,
        max_delay_seconds=4.0,
        jitter_ratio=0,
    )

    assert policy.delay(0, retry_after_seconds=3.0) == 3.0
    assert policy.delay(1, retry_after_seconds=10.0) == 4.0


def test_retry_policy_rejects_invalid_configuration():
    with pytest.raises(ValueError, match="max_retries"):
        RetryPolicy(
            max_retries=-1,
            base_delay_seconds=1,
            max_delay_seconds=4,
        )


def test_http_error_preserves_retry_after_metadata():
    error = A2AClientHTTPError(
        429,
        "rate limited",
        retry_after_seconds=2.5,
    )

    assert error.status_code == 429
    assert error.retry_after_seconds == 2.5


def test_retry_after_parser_accepts_seconds_and_http_dates():
    assert A2AClient._retry_after_seconds("3") == 3.0
    assert A2AClient._retry_after_seconds("not-a-date") is None
