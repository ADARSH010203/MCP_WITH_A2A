from app.a2a.models import Message
from app.routing.router import MultiAgent


class FakeAgent:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = []

    def invoke(self, query: str, session_id: str) -> dict:
        self.calls.append((query, session_id))
        return {
            "status": "completed",
            "agent": self.name,
            "content": f"{self.name} result",
        }

    async def stream(self, query: str, session_id: str):
        yield {
            "status": "completed",
            "agent": self.name,
            "content": f"{self.name} result",
            "is_task_complete": True,
            "require_user_input": False,
        }


class FakeCritic:
    def __init__(self):
        self.calls = []

    def synthesize(self, query: str, contributions: list[dict]) -> dict:
        self.calls.append((query, contributions))
        return {
            "status": "completed",
            "content": "critic synthesis",
            "verified": True,
        }


def fake_agents():
    return {
        name: FakeAgent(name)
        for name in (
            "currency",
            "email",
            "code",
            "image",
            "game",
            "deep_learning",
            "reinforcement",
            "dsa",
        )
    }


def router_message(text: str) -> Message:
    return Message(role="user", parts=[{"type": "text", "text": text}])


def test_routes_currency():
    router = MultiAgent(fake_agents())
    assert router._detect_agent_type(router_message("Convert 5 USD to EUR")) == "currency"


def test_routes_reinforcement_learning():
    router = MultiAgent(fake_agents())
    assert router._detect_agent_type(router_message("Explain Q-learning")) == "reinforcement"


def test_routes_all_specialists():
    router = MultiAgent(fake_agents())
    cases = {
        "Write a professional email for leave": "email",
        "Generate an image of a mountain": "image",
        "Design a Unity game level": "game",
        "Explain CNN training in PyTorch": "deep_learning",
        "Explain policy gradient reinforcement learning": "reinforcement",
        "Solve this linked list problem": "dsa",
        "Debug this Python API": "code",
    }
    for query, expected in cases.items():
        assert router._detect_agent_type(router_message(query)) == expected


def test_prefers_deep_learning_for_transformer_architecture():
    router = MultiAgent(fake_agents())
    assert (
        router._detect_agent_type(
            router_message("Explain transformer architecture for NLP")
        )
        == "deep_learning"
    )


def test_falls_back_to_code():
    router = MultiAgent(fake_agents())
    assert router._detect_agent_type(router_message("Build a Python function")) == "code"


def test_empty_injected_agents_are_preserved():
    router = MultiAgent(agents={})
    assert router.agents == {}
    assert set(router.agent_factories) == {
        "currency",
        "email",
        "code",
        "image",
        "game",
        "deep_learning",
        "reinforcement",
        "dsa",
    }


def test_selects_multiple_agents_for_cross_domain_request():
    router = MultiAgent(fake_agents())
    selected = router.select_agent_types(
        "Build a Python CNN image classification pipeline"
    )
    assert "deep_learning" in selected
    assert "code" in selected
    assert len(selected) <= 3


def test_keeps_simple_request_single_agent():
    router = MultiAgent(fake_agents())
    assert router.select_agent_types("Explain binary search") == ["dsa"]


def test_collaboration_runs_specialists_and_critic():
    agents = fake_agents()
    critic = FakeCritic()
    router = MultiAgent(agents=agents, critic=critic)

    result = router.invoke(
        "Build a Python CNN image classification pipeline",
        "session-123",
    )

    assert result["status"] == "completed"
    assert result["content"] == "critic synthesis"
    assert result["verified"] is True
    assert len(critic.calls) == 1

    used_agents = [item["agent"] for item in critic.calls[0][1]]
    assert "deep_learning" in used_agents
    assert "code" in used_agents

    for agent_type in used_agents:
        assert len(agents[agent_type].calls) == 1

    code_query = agents["code"].calls[0][0]
    assert "deep_learning" in code_query
    assert "deep_learning result" in code_query



class FailingAgent(FakeAgent):
    def invoke(self, query: str, session_id: str) -> dict:
        self.calls.append((query, session_id))
        raise RuntimeError("temporary specialist failure")


def test_collaboration_survives_one_specialist_failure():
    agents = fake_agents()
    agents["code"] = FailingAgent("code")
    critic = FakeCritic()
    router = MultiAgent(agents=agents, critic=critic)

    result = router.invoke(
        "Build a Python CNN image classification pipeline",
        "session-456",
    )

    assert result["status"] == "completed"
    assert result["content"] == "critic synthesis"

    outcomes = {item["agent"]: item["status"] for item in critic.calls[0][1]}
    assert outcomes["deep_learning"] == "completed"
    assert outcomes["code"] == "error"
