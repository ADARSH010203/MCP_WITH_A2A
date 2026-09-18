from types import SimpleNamespace

import pytest

from app.a2a.models import AgentCapabilities, AgentCard, AgentSkill, TaskState
from app.routing.remote_specialist import RemoteA2ASpecialist


class FakeResolver:
    def __init__(self, base_url, api_key=None):
        self.base_url = base_url
        self.api_key = api_key
        self.calls = 0

    def get_agent_card(self):
        self.calls += 1
        return AgentCard(
            name="Code Specialist",
            description="Remote code agent",
            url=f"{self.base_url}/",
            version="1.0.0",
            capabilities=AgentCapabilities(streaming=True),
            defaultInputModes=["text"],
            defaultOutputModes=["text"],
            skills=[
                AgentSkill(
                    id="code_specialist",
                    name="Code Specialist",
                    tags=["programming"],
                )
            ],
        )


class FakeClient:
    def __init__(self, response=None, events=None):
        self.response = response
        self.events = events or []
        self.send_calls = []

    async def send_task(self, payload):
        self.send_calls.append(payload)
        return self.response

    async def send_task_streaming(self, payload):
        self.send_calls.append(payload)
        for event in self.events:
            yield event


@pytest.fixture
def completed_task():
    artifact = SimpleNamespace(
        parts=[
            SimpleNamespace(type="text", text="remote result"),
        ]
    )
    status = SimpleNamespace(
        state=TaskState.COMPLETED,
        message=None,
    )
    task = SimpleNamespace(
        status=status,
        artifacts=[artifact],
    )
    return SimpleNamespace(error=None, result=task)


def test_remote_specialist_invokes_through_a2a(monkeypatch, completed_task):
    created_clients = []

    monkeypatch.setattr(
        "app.routing.remote_specialist.A2ACardResolver",
        FakeResolver,
    )

    def fake_client_factory(**kwargs):
        client = FakeClient(response=completed_task)
        created_clients.append(client)
        return client

    monkeypatch.setattr(
        "app.routing.remote_specialist.A2AClient",
        fake_client_factory,
    )

    agent = RemoteA2ASpecialist(
        agent_type="code",
        url="http://127.0.0.1:8101",
        api_key="secret",
    )

    result = agent.invoke("Implement this", "session-1")

    assert result["status"] == "completed"
    assert result["content"] == "remote result"
    assert result["execution_mode"] == "remote-a2a"
    assert result["remote_url"] == "http://127.0.0.1:8101"
    assert created_clients[0].send_calls[0]["metadata"]["specialist"] == "code"


def test_remote_stream_maps_completed_artifact(monkeypatch):
    artifact_event = SimpleNamespace(
        error=None,
        result=SimpleNamespace(
            artifact=SimpleNamespace(
                parts=[SimpleNamespace(type="text", text="streamed result")]
            ),
            metadata={"source": "remote"},
        ),
    )

    monkeypatch.setattr(
        "app.routing.remote_specialist.A2ACardResolver",
        FakeResolver,
    )
    monkeypatch.setattr(
        "app.routing.remote_specialist.A2AClient",
        lambda **kwargs: FakeClient(events=[artifact_event]),
    )

    async def scenario():
        agent = RemoteA2ASpecialist(
            agent_type="code",
            url="http://127.0.0.1:8101",
        )
        events = [event async for event in agent.stream("Implement this", "session-2")]

        assert events[-1]["status"] == "completed"
        assert events[-1]["is_task_complete"] is True
        assert events[-1]["content"] == "streamed result"
        assert events[-1]["execution_mode"] == "remote-a2a"

    import asyncio

    asyncio.run(scenario())


def test_router_can_use_configured_remote_specialist():
    from app.routing.router import MultiAgent

    router = MultiAgent(
        agents={},
        remote_specialist_urls={"code": "http://127.0.0.1:8101"},
    )

    agent = router._get_agent("code")
    assert isinstance(agent, RemoteA2ASpecialist)
    assert router._get_agent("code") is agent


def test_router_rejects_unknown_remote_specialist():
    from app.routing.router import MultiAgent

    with pytest.raises(ValueError, match="Unsupported remote specialist agents"):
        MultiAgent(
            agents={},
            remote_specialist_urls={"unknown": "http://127.0.0.1:8101"},
        )
