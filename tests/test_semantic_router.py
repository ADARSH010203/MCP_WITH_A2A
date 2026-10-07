from dataclasses import dataclass
from typing import Any

from app.routing.registry import DEFAULT_AGENT_REGISTRY
from app.routing.semantic import (
    SemanticAgentScore,
    SemanticRoutingDecision,
    SemanticRouter,
)


class FakeStructuredLLM:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.prompts: list[str] = []

    def with_structured_output(self, _schema: Any) -> "FakeStructuredLLM":
        return self

    def invoke(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        return self.result


@dataclass
class FakeSemanticRouter:
    selected: list[str]

    def select(
        self,
        query: str,
        candidates: tuple[str, ...] | None = None,
        max_agents: int = 3,
    ) -> list[str]:
        del query, candidates
        return self.selected[:max_agents]


def test_semantic_router_accepts_only_registered_agents() -> None:
    llm = FakeStructuredLLM(
        SemanticRoutingDecision(
            rankings=[
                SemanticAgentScore(
                    agent="email",
                    score=0.94,
                    reason="The request is communication-focused.",
                ),
                SemanticAgentScore(
                    agent="not_registered",
                    score=0.99,
                ),
                SemanticAgentScore(agent="code", score=0.40),
            ]
        )
    )
    router = SemanticRouter(
        DEFAULT_AGENT_REGISTRY,
        model_name="test-model",
        llm=llm,
    )

    selected = router.select("Please help me word a professional note to my professor.")

    assert selected == ["email"]
    assert "UNTRUSTED DATA" in llm.prompts[0]


def test_semantic_router_can_select_close_secondary_specialist() -> None:
    llm = FakeStructuredLLM(
        SemanticRoutingDecision(
            rankings=[
                SemanticAgentScore(agent="deep_learning", score=0.91),
                SemanticAgentScore(agent="code", score=0.84),
            ]
        )
    )
    router = SemanticRouter(
        DEFAULT_AGENT_REGISTRY,
        model_name="test-model",
        llm=llm,
        secondary_score=0.72,
        max_agents=3,
    )

    selected = router.select(
        "Build and implement a machine-learning model.",
        max_agents=3,
    )

    assert selected == ["deep_learning", "code"]


def test_semantic_router_rejects_low_confidence_result() -> None:
    llm = FakeStructuredLLM(
        SemanticRoutingDecision(
            rankings=[
                SemanticAgentScore(agent="code", score=0.31),
                SemanticAgentScore(agent="dsa", score=0.22),
            ]
        )
    )
    router = SemanticRouter(
        DEFAULT_AGENT_REGISTRY,
        model_name="test-model",
        llm=llm,
        min_score=0.58,
    )

    try:
        router.select("A vague request with no clear domain.")
    except Exception as exc:
        assert "confidence threshold" in str(exc)
    else:
        raise AssertionError("Expected low-confidence semantic routing to fail.")


def test_multAgent_uses_semantic_fallback_for_unmatched_language() -> None:
    from app.routing.router import MultiAgent

    router = MultiAgent(
        semantic_router=FakeSemanticRouter(selected=["email"]),
    )

    assert router.select_agent_types(
        "Please help me phrase a respectful request to my university."
    ) == ["email"]


def test_multAgent_keeps_existing_deterministic_route_without_semantic_call() -> None:
    from app.routing.router import MultiAgent

    semantic = FakeSemanticRouter(selected=["image"])
    router = MultiAgent(semantic_router=semantic)

    assert router.select_agent_types("Explain binary search complexity.") == ["dsa"]
    assert semantic.selected == ["image"]


def test_multAgent_falls_back_to_code_when_semantic_router_is_unavailable() -> None:
    from app.routing.router import MultiAgent
    from app.routing.semantic import SemanticRoutingError

    class BrokenSemanticRouter:
        def select(self, query: str, max_agents: int = 3) -> list[str]:
            del query, max_agents
            raise SemanticRoutingError("provider unavailable")

    router = MultiAgent(semantic_router=BrokenSemanticRouter())

    assert router.select_agent_types(
        "Please advise me on a completely unfamiliar task."
    ) == ["code"]
