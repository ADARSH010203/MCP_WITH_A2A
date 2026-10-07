import pytest

from app.a2a.models import AgentCapabilities, AgentCard, AgentSkill
from app.routing.capability import (
    CapabilityAuthorizationError,
    CapabilityAuthorizer,
)
from app.routing.registry import AgentCapability, AgentRegistry, DEFAULT_AGENT_REGISTRY


def test_authorized_candidates_exclude_untrusted_agents():
    authorizer = CapabilityAuthorizer(
        DEFAULT_AGENT_REGISTRY,
        authorized_agents=("code", "dsa"),
    )

    assert authorizer.filter_candidates(("code", "email", "dsa")) == ("code", "dsa")


def test_selection_rejects_unauthorized_agent():
    authorizer = CapabilityAuthorizer(
        DEFAULT_AGENT_REGISTRY,
        authorized_agents=("code",),
    )

    with pytest.raises(CapabilityAuthorizationError, match="Unauthorized"):
        authorizer.validate_selection(("email",))


def test_selection_rejects_unknown_agent():
    authorizer = CapabilityAuthorizer(DEFAULT_AGENT_REGISTRY)

    with pytest.raises(CapabilityAuthorizationError, match="Unknown selected"):
        authorizer.validate_selection(("not_registered",))


def test_selection_enforces_input_and_output_contracts():
    registry = AgentRegistry(
        (
            AgentCapability(
                name="data",
                capabilities=("data analysis",),
                triggers=(("data", 1),),
                task_focus="Analyze data.",
                input_types=("file",),
                output_types=("json",),
            ),
        )
    )
    authorizer = CapabilityAuthorizer(registry)

    with pytest.raises(CapabilityAuthorizationError, match="input type"):
        authorizer.validate_selection(("data",))

    with pytest.raises(CapabilityAuthorizationError, match="output type"):
        authorizer.validate_selection(
            ("data",),
            input_type="file",
            output_type="text",
        )


def test_remote_agent_card_must_match_registered_capability_contract():
    authorizer = CapabilityAuthorizer(
        DEFAULT_AGENT_REGISTRY,
        authorized_agents=("code",),
    )
    card = AgentCard(
        name="Code Specialist",
        url="https://agent.example.com/",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        skills=[
            AgentSkill(
                id="unrelated",
                name="Calendar Specialist",
                tags=["calendar"],
            )
        ],
    )

    with pytest.raises(
        CapabilityAuthorizationError,
        match="compatible registered capability",
    ):
        authorizer.validate_agent_card("code", card)


def test_remote_agent_card_accepts_registered_capability():
    authorizer = CapabilityAuthorizer(
        DEFAULT_AGENT_REGISTRY,
        authorized_agents=("code",),
    )
    card = AgentCard(
        name="Code Specialist",
        url="https://agent.example.com/",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        skills=[
            AgentSkill(
                id="code",
                name="Programming Specialist",
                tags=["programming"],
            )
        ],
    )

    authorizer.validate_agent_card("code", card)
