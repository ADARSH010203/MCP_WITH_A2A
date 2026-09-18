from app.routing.router import MultiAgent


class FakeAgent:
    def invoke(self, query, session_id):
        return {"agent": self.name, "content": query, "require_user_input": False}

    async def stream(self, query, session_id):
        yield {"agent": self.name, "content": query, "is_task_complete": True, "require_user_input": False}


def fake_agents():
    agents = {}
    for name in ("currency", "email", "code", "image", "game", "deep_learning", "reinforcement", "dsa"):
        agent = FakeAgent()
        agent.name = name
        agents[name] = agent
    return agents


def test_routes_currency():
    router = MultiAgent(fake_agents())
    assert router._detect_agent_type(router_message("Convert 5 USD to EUR")) == "currency"


def test_routes_reinforcement_learning():
    router = MultiAgent(fake_agents())
    assert router._detect_agent_type(router_message("Explain Q-learning")) == "reinforcement"


def test_routes_dsa():
    router = MultiAgent(fake_agents())
    assert router._detect_agent_type(router_message("Solve this dynamic programming problem")) == "dsa"


def test_falls_back_to_code():
    router = MultiAgent(fake_agents())
    assert router._detect_agent_type(router_message("Build a Python function")) == "code"


def router_message(text):
    from app.a2a.models import Message
    return Message(role="user", parts=[{"type": "text", "text": text}])
