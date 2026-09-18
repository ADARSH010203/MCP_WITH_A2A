import time

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
            "critic_reviewed": True,
        }


class SlowCritic(FakeCritic):
    def synthesize(self, query: str, contributions: list[dict]) -> dict:
        time.sleep(0.05)
        return super().synthesize(query, contributions)




class RetryAgent(FakeAgent):
    def __init__(self, name: str):
        super().__init__(name)
        self.attempts = 0

    def invoke(self, query: str, session_id: str) -> dict:
        self.calls.append((query, session_id))
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("temporary failure")
        return {
            "status": "completed",
            "content": f"{self.name} recovered",
        }


class SlowAgent(FakeAgent):
    def invoke(self, query: str, session_id: str) -> dict:
        self.calls.append((query, session_id))
        time.sleep(0.05)
        return {
            "status": "completed",
            "content": f"{self.name} result",
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


def test_builds_structured_plan_for_cross_domain_request():
    router = MultiAgent(fake_agents())
    plan = router.build_collaboration_plan(
        "Build a Python CNN image classification pipeline"
    )

    assert plan.mode == "multi-agent"
    assert "deep_learning" in plan.agents
    assert "code" in plan.agents
    assert plan.handoffs["code"] == ("deep_learning",)


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
    assert result["critic_reviewed"] is True
    assert result["collaboration_plan"]["mode"] == "multi-agent"
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



def test_three_agent_pipeline_handoffs_domain_findings_to_code():
    agents = fake_agents()
    critic = FakeCritic()
    router = MultiAgent(agents=agents, critic=critic)

    result = router.invoke(
        "Design a game using Q-learning and implement it in Python",
        "session-789",
    )

    assert result["status"] == "completed"
    assert result["collaboration_mode"] == "multi-agent"

    code_query = agents["code"].calls[0][0]
    assert "reinforcement" in code_query
    assert "game" in code_query
    assert "reinforcement result" in code_query
    assert "game result" in code_query



class InputRequiredAgent(FakeAgent):
    def invoke(self, query: str, session_id: str) -> dict:
        self.calls.append((query, session_id))
        return {
            "status": "input_required",
            "content": "Need deployment target.",
        }


def test_collaboration_surfaces_required_input_when_all_specialists_need_it():
    agents = fake_agents()
    agents["deep_learning"] = InputRequiredAgent("deep_learning")
    agents["code"] = InputRequiredAgent("code")

    result = MultiAgent(
        agents=agents,
        critic=FakeCritic(),
    ).invoke(
        "Build a Python CNN deployment system",
        "session-input",
    )

    assert result["status"] == "input_required"
    assert result["require_user_input"] is True
    assert "deep_learning" in result["content"]
    assert "code" in result["content"]


def test_specialist_retries_transient_failures():
    agents = fake_agents()
    agents["code"] = RetryAgent("code")
    router = MultiAgent(agents=agents)
    router.specialist_max_retries = 1
    router.specialist_timeout_seconds = 1

    result = router.invoke("Write Python code", "session-retry")

    assert result["status"] == "completed"
    assert agents["code"].attempts == 2


def test_specialist_timeout_is_isolated():
    agents = fake_agents()
    agents["code"] = SlowAgent("code")
    router = MultiAgent(agents=agents)
    router.specialist_timeout_seconds = 0.01
    router.specialist_max_retries = 1

    result = router.invoke("Write Python code", "session-timeout")

    assert result["status"] == "timeout"
    assert result["is_task_complete"] is False
    assert agents["code"].calls


def test_collaboration_continues_when_one_specialist_times_out():
    agents = fake_agents()
    agents["code"] = SlowAgent("code")
    critic = FakeCritic()
    router = MultiAgent(agents=agents, critic=critic)
    router.specialist_timeout_seconds = 0.01

    result = router.invoke(
        "Build a Python CNN image classification pipeline",
        "session-partial-timeout",
    )

    assert result["status"] == "completed"
    outcomes = {item["agent"]: item["status"] for item in critic.calls[0][1]}
    assert outcomes["deep_learning"] == "completed"
    assert outcomes["code"] == "timeout"


def test_call_budget_limits_retries_and_preserves_attempt_count():
    agents = fake_agents()
    agents["code"] = RetryAgent("code")
    router = MultiAgent(agents=agents)
    router.max_agent_calls_per_task = 1
    router.specialist_max_retries = 1

    result = router.invoke("Write Python code", "session-budget")

    assert result["status"] == "budget_exceeded"
    assert result["attempts"] == 1
    assert agents["code"].attempts == 1



def test_critic_timeout_falls_back_to_successful_findings():
    agents = fake_agents()
    router = MultiAgent(agents=agents, critic=SlowCritic())
    router.specialist_timeout_seconds = 0.01

    result = router.invoke(
        "Build a Python CNN image classification pipeline",
        "session-critic-timeout",
    )

    assert result["status"] == "completed"
    assert result["critic_reviewed"] is False
    assert "deep_learning result" in result["content"]



def test_collaboration_trace_contains_plan_handoff_and_critic():
    agents = fake_agents()
    critic = FakeCritic()
    router = MultiAgent(agents=agents, critic=critic)

    result = router.invoke(
        "Design a game using Q-learning and implement it in Python",
        "session-trace",
    )

    trace = result["collaboration_trace"]
    assert trace["trace_id"]
    assert trace["event_count"] >= 6

    stages = [event["stage"] for event in trace["events"]]
    assert stages[0] == "plan_created"
    assert "specialist_started" in stages
    assert "specialist_completed" in stages
    assert "handoff" in stages
    assert "critic_started" in stages
    assert "critic_completed" in stages
    assert stages[-1] == "request_completed"

    assert trace["duration_ms"] >= 0
    assert all(event["sequence"] > 0 for event in trace["events"])
    assert any(event["actor"] == "code" for event in trace["events"])


def test_single_agent_trace_is_available():
    router = MultiAgent(fake_agents())

    result = router.invoke("Explain binary search", "session-single-trace")

    trace = result["collaboration_trace"]
    assert trace["event_count"] >= 3
    assert trace["events"][0]["stage"] == "plan_created"
    assert trace["events"][-1]["stage"] == "request_completed"



def test_streaming_multi_agent_trace_reaches_final_event():
    async def scenario():
        router = MultiAgent(agents=fake_agents(), critic=FakeCritic())
        events = []

        async for event in router.stream(
            "Build a Python CNN image classification pipeline",
            "session-stream-trace",
        ):
            events.append(event)

        assert events
        final = events[-1]
        assert final["is_task_complete"] is True

        trace = final["collaboration_trace"]
        assert trace["trace_id"]
        assert trace["event_count"] >= 6
        assert trace["events"][-1]["stage"] == "request_completed"

    import asyncio

    asyncio.run(scenario())


def test_capability_registry_prefers_specialized_trigger():
    router = MultiAgent(fake_agents())

    selected = router.select_agent_types(
        "Design an image classification model"
    )

    assert selected[0] == "deep_learning"


def test_router_plan_exposes_generic_dependency_groups():
    router = MultiAgent(fake_agents())

    plan = router.build_collaboration_plan(
        "Design a game using Q-learning and implement it in Python"
    )

    steps = {step.agent: step for step in plan.steps}
    assert steps["reinforcement"].depends_on == ()
    assert steps["game"].depends_on == ()
    assert steps["code"].depends_on == ("reinforcement", "game")
    assert steps["reinforcement"].parallel_group == steps["game"].parallel_group == 1
    assert steps["code"].parallel_group == 2


class SlowStreamingAgent(FakeAgent):
    async def stream(self, query: str, session_id: str):
        self.calls.append((query, session_id))
        while True:
            await asyncio.sleep(0.004)
            yield {
                "status": "working",
                "is_task_complete": False,
                "require_user_input": False,
                "content": "still working",
            }


def test_streaming_specialist_timeout_is_total_not_per_chunk():
    import asyncio

    async def scenario():
        agents = fake_agents()
        agents["code"] = SlowStreamingAgent("code")
        router = MultiAgent(agents=agents)
        router.specialist_timeout_seconds = 0.02

        events = [
            event
            async for event in router.stream(
                "Write Python code",
                "session-stream-total-timeout",
            )
        ]

        final = events[-1]
        assert final["status"] == "timeout"
        assert final["is_task_complete"] is False
        assert final["collaboration_trace"]["events"][-1]["stage"] == "request_completed"

    asyncio.run(scenario())
