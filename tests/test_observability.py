from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.a2a.server import A2AServer
from app.observability.context import (
    normalize_request_id,
    use_request_id,
)
from app.observability.metrics import MetricsRegistry
from app.routing.tracing import CollaborationTrace


def test_request_id_normalization_keeps_safe_ids():
    assert normalize_request_id("req-123:abc") == "req-123:abc"


def test_request_id_normalization_replaces_unsafe_ids():
    generated = normalize_request_id("bad request/with spaces")
    assert generated
    assert generated != "bad request/with spaces"
    assert len(generated) == 32


def test_metrics_registry_tracks_counters_and_bounded_latency():
    metrics = MetricsRegistry(max_samples=3)

    metrics.increment("requests_total", labels={"status": "200"})
    metrics.increment("requests_total", labels={"status": "200"}, amount=2)
    for value in (10, 20, 30, 40):
        metrics.observe("request_duration_ms", value)

    snapshot = metrics.snapshot()
    assert snapshot["counters"]["requests_total"]["status"] == "200"
    assert snapshot["counters"]["requests_total"]["value"] == 3
    assert snapshot["latencies"]["request_duration_ms"]["count"] == 3
    assert snapshot["latencies"]["request_duration_ms"]["p50_ms"] == 30
    assert snapshot["latencies"]["request_duration_ms"]["p95_ms"] == 39.0
    assert snapshot["latencies"]["request_duration_ms"]["max_ms"] == 40


def test_trace_includes_request_id_and_redacts_sensitive_details():
    with use_request_id("request-42"):
        trace = CollaborationTrace(trace_id="trace-42")
        trace.record(
            "specialist_completed",
            "code",
            "completed",
            details={
                "api_key": "top-secret",
                "nested": {
                    "Authorization": "Bearer secret-token",
                    "safe": "value",
                },
            },
        )

    event = trace.snapshot()["events"][0]
    assert trace.snapshot()["request_id"] == "request-42"
    assert event["details"]["api_key"] == "<redacted>"
    assert event["details"]["nested"]["Authorization"] == "<redacted>"
    assert event["details"]["nested"]["safe"] == "value"


def test_a2a_server_sets_request_id_and_records_http_metrics(monkeypatch):
    import app.a2a.server as server_module

    monkeypatch.setattr(
        server_module,
        "settings",
        SimpleNamespace(
            a2a_api_key="",
            a2a_cors_origins=(),
        ),
    )
    server = A2AServer()
    client = TestClient(server.app)

    response = client.get(
        "/healthz",
        headers={"X-Request-ID": "observability-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "observability-test"
    payload = response.json()
    assert payload["status"] == "ok"


def test_metrics_endpoint_requires_a2a_auth_when_configured(monkeypatch):
    import app.a2a.server as server_module

    monkeypatch.setattr(
        server_module,
        "settings",
        SimpleNamespace(
            a2a_api_key="server-secret",
            a2a_cors_origins=(),
        ),
    )
    server = A2AServer()
    client = TestClient(server.app)

    unauthorized = client.get("/metrics")
    authorized = client.get(
        "/metrics",
        headers={"Authorization": "Bearer server-secret"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    body = authorized.json()
    assert "counters" in body
    assert "latencies" in body
