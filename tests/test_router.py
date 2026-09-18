from app.a2a.models import Message
from app.routing.router import MultiAgent


class FakeAgent:
    def __init__(self, name: str) -> None:
        self.name = name

    def invoke(self, query: str, session_id: str) -> dict:
        return {"agent": self.name, "content": query, "require_user_input": False}

    async def stream(self, query: str, session_id: str):
        yield {
            "agent": self.name,
            "content": query,
            "is_task_complete": True,
            "require_user_input": False,
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


def test_routes_dsa():
    router = MultiAgent(fake_agents())
    assert router._detect_agent_type(
        router_message("Solve this dynamic programming problem")
    ) == "dsa"


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
