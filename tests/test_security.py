"""Security boundary tests for the A2A HTTP surface."""

import asyncio

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
            a2a_cors_origins=(),
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
            a2a_cors_origins=(),
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


def test_chunked_body_is_bounded():
    server = A2AServer()

    class FakeRequest:
        headers = {}

        async def stream(self):
            yield b"x" * 1_000_001

    response = asyncio.run(server._read_request_body(FakeRequest()))
    assert response.status_code == 413


def test_bearer_scheme_is_case_insensitive(monkeypatch):
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

    response = client.post(
        "/",
        json={"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"id": "x"}},
        headers={"Authorization": "bearer secret"},
    )

    assert response.status_code != 401


def test_non_json_content_type_is_rejected(monkeypatch):
    monkeypatch.setattr(
        server_module,
        "settings",
        SimpleNamespace(
            a2a_api_key="",
            a2a_rate_limit_per_minute=60,
            a2a_max_request_body_bytes=1000000,
        ),
    )
    server = A2AServer()
    client = TestClient(server.app)

    response = client.post(
        "/",
        content=b"{}",
        headers={"Content-Type": "text/plain"},
    )

    assert response.status_code == 415


def test_readiness_reports_task_store_state(monkeypatch):
    from types import SimpleNamespace

    from app.a2a.models import AgentCapabilities, AgentCard, AgentSkill
    import app.a2a.readiness as readiness_module

    class TaskManager:
        def __init__(self, ready):
            self.ready = ready

        def is_ready(self):
            return self.ready

    class FakeSocket:
        def close(self):
            pass

    monkeypatch.setattr(
        readiness_module,
        "settings",
        SimpleNamespace(
            groq_api_key="groq-secret",
            a2a_memory_namespace_secret="memory-secret",
            a2a_memory_db_path=":memory:",
            mcp_url="http://127.0.0.1:3000/sse",
            a2a_specialist_urls={},
            a2a_specialist_api_keys={},
            a2a_remote_require_https=True,
            a2a_remote_require_auth=True,
        ),
    )
    monkeypatch.setattr(
        readiness_module.socket,
        "create_connection",
        lambda *args, **kwargs: FakeSocket(),
    )

    card = AgentCard(
        name="Test",
        description="test",
        url="http://127.0.0.1:8000/",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        skills=[
            AgentSkill(
                id="code",
                name="Code",
                tags=["programming"],
            )
        ],
    )

    not_ready = TestClient(
        A2AServer(agent_card=card, task_manager=TaskManager(False)).app
    )
    assert not_ready.get("/readyz").status_code == 503

    ready = TestClient(
        A2AServer(agent_card=card, task_manager=TaskManager(True)).app
    )
    response = ready.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
