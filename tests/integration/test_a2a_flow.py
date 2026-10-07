from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Message,
    TaskSendParams,
)
from app.a2a.server import A2AServer
from app.a2a.task_manager import AgentTaskManager
from app.a2a.task_store import SQLiteTaskStore


class FakeNotificationAuth:
    async def verify_push_notification_url(self, url: str) -> bool:
        return True

    async def send_push_notification(self, url: str, data: dict) -> None:
        return None


class FakeAgent:
    def invoke(self, query: str, session_id: str) -> dict:
        return {
            "status": "completed",
            "is_task_complete": True,
            "require_user_input": False,
            "content": f"processed: {query}",
            "agents_used": ["code"],
        }

    async def stream(self, query: str, session_id: str):
        yield {
            "status": "completed",
            "is_task_complete": True,
            "require_user_input": False,
            "content": f"streamed: {query}",
            "agents_used": ["code"],
        }


def _server():
    manager = AgentTaskManager(
        agent=FakeAgent(),
        notification_sender_auth=FakeNotificationAuth(),
        store=SQLiteTaskStore(":memory:"),
    )
    card = AgentCard(
        name="Integration Agent",
        description="A2A integration test agent",
        url="http://testserver/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True),
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        skills=[
            AgentSkill(
                id="code",
                name="Code",
                description="Handles programming tasks.",
                tags=["programming"],
            )
        ],
    )
    return A2AServer(agent_card=card, task_manager=manager)


def test_a2a_task_submission_completes_end_to_end():
    client = TestClient(_server().app)

    response = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tasks/send",
            "params": {
                "id": "integration-task-1",
                "sessionId": "integration-session-1",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "write hello world"}],
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["status"]["state"] == "completed"
    assert payload["result"]["artifacts"][0]["parts"][0]["text"].startswith(
        "processed:"
    )
    assert response.headers["X-Request-ID"]


def test_a2a_agent_card_and_metrics_are_exposed():
    client = TestClient(_server().app)

    card = client.get("/.well-known/agent.json")
    metrics = client.get("/metrics")

    assert card.status_code == 200
    assert card.json()["name"] == "Integration Agent"
    assert metrics.status_code == 200
    assert "counters" in metrics.json()
