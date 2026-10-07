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


def test_remote_specialist_invokes_capability_validator(monkeypatch):
    monkeypatch.setattr(
        "app.routing.remote_specialist.A2ACardResolver",
        FakeResolver,
    )
    monkeypatch.setattr(
        "app.routing.remote_specialist.A2AClient",
        lambda **kwargs: FakeClient(),
    )
    calls = []

    def validator(agent_type, card):
        calls.append((agent_type, card.name))

    agent = RemoteA2ASpecialist(
        agent_type="code",
        url="https://127.0.0.1:8101",
        api_key="secret",
        capability_validator=validator,
    )

    agent._ensure_client()
    assert calls == [("code", "Code Specialist")]


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
        url="https://127.0.0.1:8101",
        api_key="secret",
    )

    result = agent.invoke("Implement this", "session-1")

    assert result["status"] == "completed"
    assert result["content"] == "remote result"
    assert result["execution_mode"] == "remote-a2a"
    assert result["remote_url"] == "https://127.0.0.1:8101"
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
            url="https://127.0.0.1:8101",
            api_key="secret",
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


class ForeignCardResolver(FakeResolver):
    def get_agent_card(self):
        card = super().get_agent_card()
        return card.model_copy(update={"url": "https://unexpected.example.com/a2a"})


def test_remote_specialist_rejects_agent_card_origin_change(monkeypatch):
    monkeypatch.setattr(
        "app.routing.remote_specialist.A2ACardResolver",
        ForeignCardResolver,
    )

    agent = RemoteA2ASpecialist(
        agent_type="code",
        url="https://agent.example.com",
        api_key="secret",
    )

    with pytest.raises(ValueError, match="outside the configured service origin"):
        agent._ensure_client()


def test_router_uses_per_specialist_api_key(monkeypatch):
    from types import SimpleNamespace

    import app.routing.router as router_module

    created = []

    class FakeRemote:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr(router_module, "RemoteA2ASpecialist", FakeRemote)
    monkeypatch.setattr(
        router_module,
        "settings",
        SimpleNamespace(
            a2a_max_collaborative_agents=3,
            a2a_specialist_urls={},
            a2a_specialist_api_keys={"code": "code-secret"},
            a2a_specialist_timeout_seconds=45,
            a2a_specialist_max_retries=1,
            a2a_specialist_retry_backoff_seconds=0,
            a2a_max_agent_calls_per_task=6,
            a2a_api_key="global-secret",
        ),
    )

    router = router_module.MultiAgent(
        agents={},
        remote_specialist_urls={"code": "http://127.0.0.1:8101"},
    )
    router._get_agent("code")

    assert created[0]["api_key"] == "code-secret"


def test_router_rejects_unknown_remote_credentials(monkeypatch):
    from types import SimpleNamespace

    import app.routing.router as router_module

    monkeypatch.setattr(
        router_module,
        "settings",
        SimpleNamespace(
            a2a_max_collaborative_agents=3,
            a2a_specialist_urls={},
            a2a_specialist_api_keys={"unknown": "secret"},
            a2a_specialist_timeout_seconds=45,
            a2a_specialist_max_retries=1,
            a2a_specialist_retry_backoff_seconds=0,
            a2a_max_agent_calls_per_task=6,
            a2a_api_key="",
        ),
    )

    with pytest.raises(ValueError, match="Unsupported remote specialist credentials"):
        router_module.MultiAgent(
            agents={},
            remote_specialist_urls={},
        )


def test_remote_specialist_rejects_insecure_transport(monkeypatch):
    import app.routing.remote_specialist as module
    from types import SimpleNamespace

    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(a2a_remote_require_https=True, a2a_remote_require_auth=False),
    )
    agent = RemoteA2ASpecialist(
        agent_type="code",
        url="http://agent.example.com",
    )

    with pytest.raises(ValueError, match="must use HTTPS"):
        agent._ensure_client()


def test_remote_specialist_rejects_missing_remote_auth(monkeypatch):
    import app.routing.remote_specialist as module
    from types import SimpleNamespace

    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(a2a_remote_require_https=False, a2a_remote_require_auth=True),
    )
    agent = RemoteA2ASpecialist(
        agent_type="code",
        url="http://agent.example.com",
    )

    with pytest.raises(ValueError, match="requires an API key"):
        agent._ensure_client()


def test_remote_specialist_rejects_embedded_url_credentials(monkeypatch):
    import app.routing.remote_specialist as module
    from types import SimpleNamespace

    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(a2a_remote_require_https=False, a2a_remote_require_auth=False),
    )
    agent = RemoteA2ASpecialist(
        agent_type="code",
        url="http://user:password@agent.example.com",
    )

    with pytest.raises(ValueError, match="embedded credentials"):
        agent._ensure_client()


def test_remote_specialist_reuses_supplied_task_id(monkeypatch):
    created_clients = []

    monkeypatch.setattr(
        "app.routing.remote_specialist.A2ACardResolver",
        FakeResolver,
    )

    def fake_client_factory(**kwargs):
        client = FakeClient(response=None)
        created_clients.append(client)
        return client

    monkeypatch.setattr(
        "app.routing.remote_specialist.A2AClient",
        fake_client_factory,
    )

    agent = RemoteA2ASpecialist(
        agent_type="code",
        url="https://127.0.0.1:8101",
        api_key="secret",
    )

    agent.invoke("Implement this", "session-1", task_id="stable-task-1")
    payload = created_clients[0].send_calls[0]
    assert payload["id"] == "stable-task-1"
