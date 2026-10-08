from datetime import datetime, timezone

from app.observability.cost import TokenUsage
from app.observability.cost_ledger import (
    CostGovernance,
    CostLedgerEntry,
    _SQLiteCostLedger,
)


def test_sqlite_cost_ledger_records_idempotently_and_aggregates_by_principal(tmp_path):
    ledger = _SQLiteCostLedger(
        str(tmp_path / "cost.db"),
        "namespace-secret",
    )
    governance = CostGovernance(
        ledger,
        daily_token_limit=1000,
        monthly_token_limit=2000,
        daily_cost_limit_usd=1.0,
        monthly_cost_limit_usd=2.0,
    )
    recorded_at = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)

    first = governance.record(
        task_key="task-1",
        principal_id="tenant-a",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        estimated_cost_usd=0.25,
        status="completed",
        agents=("code", "critic"),
        recorded_at=recorded_at,
    )
    duplicate = governance.record(
        task_key="task-1",
        principal_id="tenant-a",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        estimated_cost_usd=0.25,
        status="completed",
        agents=("code", "critic"),
        recorded_at=recorded_at,
    )
    second_principal = governance.record(
        task_key="task-2",
        principal_id="tenant-b",
        usage=TokenUsage(input_tokens=20, output_tokens=10),
        estimated_cost_usd=0.05,
        status="completed",
        agents=("email",),
        recorded_at=recorded_at,
    )

    assert first["recorded"] is True
    assert duplicate["recorded"] is False
    assert second_principal["recorded"] is True

    report = governance.report("tenant-a")
    assert report["daily"]["total_tokens"] == 150
    assert report["daily"]["tasks"] == 1
    assert report["daily"]["estimated_cost_usd"] == 0.25
    assert report["monthly"] == report["daily"]
    assert report["budget"]["within_budget"] is True

    other_report = governance.report("tenant-b")
    assert other_report["daily"]["total_tokens"] == 30
    assert other_report["daily"]["tasks"] == 1

    ledger.close()


def test_cost_budget_report_flags_daily_and_monthly_overage(tmp_path):
    ledger = _SQLiteCostLedger(
        str(tmp_path / "cost.db"),
        "namespace-secret",
    )
    governance = CostGovernance(
        ledger,
        daily_token_limit=100,
        monthly_token_limit=1000,
        daily_cost_limit_usd=0.1,
        monthly_cost_limit_usd=1.0,
    )

    result = governance.record(
        task_key="task-over",
        principal_id="tenant-a",
        usage=TokenUsage(input_tokens=90, output_tokens=30),
        estimated_cost_usd=0.20,
        status="completed",
        agents=("code",),
    )

    assert result["budget"]["within_budget"] is False
    assert result["daily"]["total_tokens"] == 120
    assert result["daily"]["estimated_cost_usd"] == 0.2
    ledger.close()


def test_cost_ledger_does_not_store_raw_principal_identifier(tmp_path):
    ledger = _SQLiteCostLedger(
        str(tmp_path / "cost.db"),
        "namespace-secret",
    )
    entry = CostLedgerEntry(
        task_key="secret-task-id",
        principal_id="very-sensitive-principal",
        input_tokens=1,
        output_tokens=2,
        estimated_cost_usd=0.01,
        status="completed",
        agents=("code",),
        recorded_at=datetime.now(timezone.utc),
    )

    ledger.record(entry)
    row = ledger.connection.execute(
        "SELECT task_key, principal_key FROM cost_ledger"
    ).fetchone()

    assert row[0] == "secret-task-id"
    assert "very-sensitive-principal" not in row[1]
    ledger.close()
