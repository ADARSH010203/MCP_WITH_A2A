"""Security boundary tests for the A2A HTTP surface."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.a2a.server import A2AServer
from app.a2a.models import TaskIdParams, TaskSendParams, Message
import app.a2a.server as server_module


def test_security_headers_are_present():
    server = A2AServer()
    client = TestClient(server.app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_api_key_uses_bearer_auth(monkeypatch):
    monkeypatch.setattr(
        server_module,
        "settings",
        SimpleNamespace(
            a2a_api_key="secret",
            a2a_rate_limit_per_minute=60,
            a2a_max_request_body_bytes=1000000,
        ),
    )
    server = A2AServer()
    client = TestClient(server.app)

    response = client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"id": "x"}})

    assert response.status_code == 401


def test_oversized_request_is_rejected_before_jsonrpc_dispatch(monkeypatch):
    monkeypatch.setattr(
        server_module,
        "settings",
        SimpleNamespace(
            a2a_api_key="",
            a2a_rate_limit_per_minute=60,
            a2a_max_request_body_bytes=64,
        ),
    )
    server = A2AServer()
    client = TestClient(server.app)

    response = client.post(
        "/",
        content=b"x" * 65,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_task_identifiers_have_bounded_length():
    message = Message(role="user", parts=[{"type": "text", "text": "hello"}])

    try:
        TaskSendParams(id="x" * 129, message=message)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected an oversized task ID to be rejected")

    try:
        TaskIdParams(id="x" * 129)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected an oversized task ID to be rejected")
