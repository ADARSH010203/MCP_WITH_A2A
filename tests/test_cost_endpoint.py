import hashlib
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.a2a.server import A2AServer
from app.memory.context import use_memory_principal
from app.observability.cost import TokenUsage
from app.observability.cost_ledger import CostGovernance, _SQLiteCostLedger


def test_cost_endpoint_requires_auth_and_returns_principal_scoped_report(
    monkeypatch,
    tmp_path,
):
    import app.a2a.server as server_module
    import app.observability.cost_ledger as ledger_module

    db_path = str(tmp_path / "cost.db")
    monkeypatch.setattr(
        ledger_module,
        "settings",
        SimpleNamespace(
            a2a_memory_namespace_secret="namespace-secret",
            a2a_task_store_backend="sqlite",
            a2a_task_db_path=db_path,
            a2a_task_database_url="",
        ),
    )
    monkeypatch.setattr(
        server_module,
        "settings",
        SimpleNamespace(
            a2a_cost_ledger_enabled=True,
            a2a_api_key="server-secret",
            a2a_daily_token_limit_per_principal=1000,
            a2a_monthly_token_limit_per_principal=2000,
            a2a_daily_cost_limit_usd_per_principal=1.0,
            a2a_monthly_cost_limit_usd_per_principal=2.0,
        ),
    )

    ledger = _SQLiteCostLedger(db_path, "namespace-secret")
    governance = CostGovernance(ledger)
    with use_memory_principal("tenant-a"):
        governance.record(
            task_key="endpoint-task",
            principal_id=(
                "bearer:"
                + hashlib.sha256(
                    "server-secret".encode("utf-8")
                ).hexdigest()
            ),
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            estimated_cost_usd=0.02,
            status="completed",
            agents=("code",),
        )
    ledger.close()

    client = TestClient(A2AServer().app)

    unauthorized = client.get("/costs")
    authorized = client.get(
        "/costs",
        headers={"Authorization": "Bearer server-secret"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    body = authorized.json()
    assert body["principal_scoped"] is True
    assert body["daily"]["total_tokens"] == 15


def test_cost_endpoint_is_unavailable_without_server_auth(
    monkeypatch,
):
    import app.a2a.server as server_module

    monkeypatch.setattr(
        server_module,
        "settings",
        SimpleNamespace(
            a2a_cost_ledger_enabled=True,
            a2a_api_key="",
        ),
    )

    client = TestClient(A2AServer().app)
    response = client.get("/costs")

    assert response.status_code == 503
