from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.a2a.server import A2AServer
from app.observability.cost import TokenUsage
from app.observability.cost_ledger import CostGovernance, _SQLiteCostLedger
import app.a2a.server as server_module
import app.config.settings as settings_module
import app.observability.cost_ledger as ledger_module


def _principal_auth_settings(**overrides):
    values = {
        "a2a_api_key": "",
        "a2a_principal_api_keys": {
            "tenant-a": "tenant-a-client-secret",
            "tenant-b": "tenant-b-client-secret",
        },
        "a2a_cors_origins": (),
        "a2a_rate_limit_per_minute": 60,
        "a2a_max_request_body_bytes": 1_000_000,
        "a2a_cost_ledger_enabled": False,
        "a2a_memory_namespace_secret": "test-namespace-secret",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_principal_api_key_loader_parses_separate_client_credentials(monkeypatch):
    monkeypatch.setenv("A2A_API_KEY", "shared-admin-secret")
    monkeypatch.setenv(
        "A2A_PRINCIPAL_API_KEYS",
        "tenant-a=tenant-a-key;tenant-b=tenant-b-key",
    )

    assert settings_module._load_principal_api_keys() == {
        "tenant-a": "tenant-a-key",
        "tenant-b": "tenant-b-key",
    }


@pytest.mark.parametrize(
    "raw",
    [
        "tenant-a=key-a;tenant-a=key-b",
        "tenant-a=shared-key;tenant-b=shared-key",
        "tenant-a=shared-admin-secret",
        "bad principal=key",
        "tenant-a=",
        "missing-separator",
    ],
)
def test_principal_api_key_loader_rejects_ambiguous_or_invalid_config(
    monkeypatch,
    raw,
):
    monkeypatch.setenv("A2A_API_KEY", "shared-admin-secret")
    monkeypatch.setenv("A2A_PRINCIPAL_API_KEYS", raw)

    with pytest.raises(ValueError):
        settings_module._load_principal_api_keys()


def test_a2a_endpoint_authenticates_principal_key_without_global_key(monkeypatch):
    monkeypatch.setattr(
        server_module,
        "settings",
        _principal_auth_settings(),
    )
    client = TestClient(A2AServer().app)

    accepted = client.post(
        "/",
        content="not-json",
        headers={
            "Authorization": "Bearer tenant-a-client-secret",
            "Content-Type": "text/plain",
        },
    )
    rejected = client.post(
        "/",
        content="not-json",
        headers={
            "Authorization": "Bearer wrong-secret",
            "Content-Type": "text/plain",
        },
    )

    # A valid principal key passes authentication and reaches content validation.
    assert accepted.status_code == 415
    assert rejected.status_code == 401


def test_legacy_global_api_key_still_works(monkeypatch):
    monkeypatch.setattr(
        server_module,
        "settings",
        _principal_auth_settings(
            a2a_api_key="shared-admin-secret",
            a2a_principal_api_keys={},
        ),
    )
    client = TestClient(A2AServer().app)

    accepted = client.post(
        "/",
        content="not-json",
        headers={
            "Authorization": "Bearer shared-admin-secret",
            "Content-Type": "text/plain",
        },
    )
    rejected = client.post(
        "/",
        content="not-json",
        headers={
            "Authorization": "Bearer wrong-secret",
            "Content-Type": "text/plain",
        },
    )

    assert accepted.status_code == 415
    assert rejected.status_code == 401


def test_cost_endpoint_returns_only_authenticated_principal_usage(
    monkeypatch,
    tmp_path,
):
    database_path = str(tmp_path / "principal-costs.db")
    monkeypatch.setattr(
        ledger_module,
        "settings",
        SimpleNamespace(
            a2a_memory_namespace_secret="test-namespace-secret",
            a2a_task_store_backend="sqlite",
            a2a_task_database_url="",
            a2a_task_db_path=database_path,
        ),
    )
    monkeypatch.setattr(
        server_module,
        "settings",
        _principal_auth_settings(
            a2a_cost_ledger_enabled=True,
            a2a_daily_token_limit_per_principal=10_000,
            a2a_monthly_token_limit_per_principal=20_000,
            a2a_daily_cost_limit_usd_per_principal=1.0,
            a2a_monthly_cost_limit_usd_per_principal=2.0,
        ),
    )

    ledger = _SQLiteCostLedger(database_path, "test-namespace-secret")
    governance = CostGovernance(ledger)
    now = datetime.now(timezone.utc)
    governance.record(
        task_key="tenant-a-task",
        principal_id="client:tenant-a",
        usage=TokenUsage(input_tokens=10, output_tokens=5),
        estimated_cost_usd=0.02,
        status="completed",
        agents=("code",),
        recorded_at=now,
    )
    governance.record(
        task_key="tenant-b-task",
        principal_id="client:tenant-b",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        estimated_cost_usd=0.20,
        status="completed",
        agents=("email",),
        recorded_at=now,
    )
    ledger.close()

    client = TestClient(A2AServer().app)
    tenant_a = client.get(
        "/costs",
        headers={"Authorization": "Bearer tenant-a-client-secret"},
    )
    tenant_b = client.get(
        "/costs",
        headers={"Authorization": "Bearer tenant-b-client-secret"},
    )
    unknown = client.get(
        "/costs",
        headers={"Authorization": "Bearer unknown-secret"},
    )

    assert tenant_a.status_code == 200
    assert tenant_b.status_code == 200
    assert tenant_a.json()["daily"]["total_tokens"] == 15
    assert tenant_b.json()["daily"]["total_tokens"] == 150
    assert unknown.status_code == 401
