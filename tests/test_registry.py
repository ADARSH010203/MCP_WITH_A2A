import pytest

from app.routing.registry import AgentCapability, AgentRegistry


def test_default_registry_has_all_current_specialists():
    from app.routing.registry import DEFAULT_AGENT_REGISTRY

    assert DEFAULT_AGENT_REGISTRY.names() == (
        "currency",
        "email",
        "image",
        "game",
        "deep_learning",
        "reinforcement",
        "dsa",
        "code",
    )
    assert DEFAULT_AGENT_REGISTRY.get("code").dependencies


def test_registry_rejects_unknown_dependency():
    with pytest.raises(ValueError, match="Unknown agent dependencies"):
        AgentRegistry(
            (
                AgentCapability(
                    name="code",
                    capabilities=("implementation",),
                    triggers=(("code", 1),),
                    task_focus="Write code.",
                    dependencies=("missing",),
                ),
            )
        )


def test_registry_rejects_dependency_cycle():
    with pytest.raises(ValueError, match="cycle"):
        AgentRegistry(
            (
                AgentCapability(
                    name="a",
                    capabilities=("a",),
                    triggers=(("a", 1),),
                    task_focus="A",
                    dependencies=("b",),
                ),
                AgentCapability(
                    name="b",
                    capabilities=("b",),
                    triggers=(("b", 1),),
                    task_focus="B",
                    dependencies=("a",),
                ),
            )
        )


def test_registry_keeps_capability_priority_available_for_routing():
    registry = AgentRegistry(
        (
            AgentCapability(
                name="generic",
                capabilities=("generic",),
                triggers=(("model", 1),),
                task_focus="Generic",
                priority=10,
            ),
            AgentCapability(
                name="specialist",
                capabilities=("specialist",),
                triggers=(("model", 1),),
                task_focus="Specialist",
                priority=90,
            ),
        )
    )

    scores = registry.score_all(
        "model",
        lambda text, trigger: trigger in text,
    )

    ranked = sorted(
        scores,
        key=lambda name: (-scores[name], -registry.get(name).priority, name),
    )
    assert ranked == ["specialist", "generic"]
