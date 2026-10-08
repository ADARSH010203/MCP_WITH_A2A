import os
from datetime import datetime, timezone

import pytest

from app.observability.cost import TokenUsage
from app.observability.cost_ledger import (
    CostGovernance,
    _PostgresCostLedger,
)


POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "").strip()

pytestmark = pytest.mark.integration


@pytest.fixture
def postgres_cost_ledger():
    if not POSTGRES_URL:
        pytest.skip("TEST_POSTGRES_URL is not configured")
    ledger = _PostgresCostLedger(
        POSTGRES_URL,
        "phase19-test-secret",
    )
    yield ledger
    ledger.connection.execute("DROP TABLE IF EXISTS cost_ledger")
    ledger.close()


def test_postgres_cost_ledger_persists_and_deduplicates(postgres_cost_ledger):
    governance = CostGovernance(postgres_cost_ledger)
    timestamp = datetime.now(timezone.utc)

    first = governance.record(
        task_key="postgres-cost-1",
        principal_id="tenant-a",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        estimated_cost_usd=0.12,
        status="completed",
        agents=("code", "critic"),
        recorded_at=timestamp,
    )
    duplicate = governance.record(
        task_key="postgres-cost-1",
        principal_id="tenant-a",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        estimated_cost_usd=0.12,
        status="completed",
        agents=("code", "critic"),
        recorded_at=timestamp,
    )

    assert first["recorded"] is True
    assert duplicate["recorded"] is False

    report = governance.report("tenant-a")
    assert report["daily"]["total_tokens"] == 150
    assert report["daily"]["tasks"] == 1
    assert report["daily"]["estimated_cost_usd"] == 0.12
