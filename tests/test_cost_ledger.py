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
    recorded_at = datetime.now(timezone.utc).replace(microsecond=0)

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


def test_budget_reservation_blocks_concurrent_overcommit(tmp_path):
    from datetime import timedelta

    ledger = _SQLiteCostLedger(
        str(tmp_path / "cost.db"),
        "namespace-secret",
    )
    now = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
    governance = CostGovernance(
        ledger,
        daily_token_limit=100,
        monthly_token_limit=100,
    )

    first = governance.admit(
        principal_id="tenant-a",
        reservation_key="reservation-1",
        reserved_tokens=80,
        reserved_cost_usd=0.0,
        now=now,
        expires_at=now + timedelta(minutes=5),
    )
    second = governance.admit(
        principal_id="tenant-a",
        reservation_key="reservation-2",
        reserved_tokens=30,
        reserved_cost_usd=0.0,
        now=now,
        expires_at=now + timedelta(minutes=5),
    )

    assert first is True
    assert second is False

    governance.release("reservation-1")
    third = governance.admit(
        principal_id="tenant-a",
        reservation_key="reservation-3",
        reserved_tokens=30,
        reserved_cost_usd=0.0,
        now=now,
        expires_at=now + timedelta(minutes=5),
    )
    assert third is True
    governance.release("reservation-3")
    ledger.close()


def test_expired_budget_reservation_is_reclaimed(tmp_path):
    from datetime import timedelta

    ledger = _SQLiteCostLedger(
        str(tmp_path / "cost.db"),
        "namespace-secret",
    )
    now = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
    governance = CostGovernance(
        ledger,
        daily_token_limit=100,
    )

    assert governance.admit(
        principal_id="tenant-a",
        reservation_key="expired",
        reserved_tokens=90,
        reserved_cost_usd=0.0,
        now=now,
        expires_at=now + timedelta(seconds=30),
    )

    reclaimed = governance.admit(
        principal_id="tenant-a",
        reservation_key="new",
        reserved_tokens=90,
        reserved_cost_usd=0.0,
        now=now + timedelta(minutes=1),
        expires_at=now + timedelta(minutes=6),
    )
    assert reclaimed is True
    governance.release("new")
    ledger.close()
