"""Capability and authorization validation for specialist execution."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.a2a.models import AgentCard
from app.routing.registry import AgentCapability, AgentRegistry


class CapabilityAuthorizationError(ValueError):
    """Raised when an agent selection violates the capability contract."""


class CapabilityAuthorizer:
    """Validate agent authorization, capability contracts, and runtime inputs."""

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        authorized_agents: Iterable[str] | None = None,
    ) -> None:
        self.registry = registry
        configured = (
            set(registry.names())
            if authorized_agents is None
            else set(authorized_agents)
        )

        unknown = configured - set(registry.names())
        if unknown:
            names = ", ".join(sorted(unknown))
            raise CapabilityAuthorizationError(
                f"Unknown authorized agents: {names}"
            )

        self._authorized_agents = frozenset(configured)

    @property
    def authorized_agents(self) -> frozenset[str]:
        return self._authorized_agents

    def filter_candidates(self, candidates: Sequence[str]) -> tuple[str, ...]:
        """Return only registered agents that this coordinator may use."""
        unknown = set(candidates) - set(self.registry.names())
        if unknown:
            names = ", ".join(sorted(unknown))
            raise CapabilityAuthorizationError(
                f"Unknown candidate agents: {names}"
            )

        return tuple(agent for agent in candidates if agent in self._authorized_agents)

    def select_fallback(self) -> str:
        """Choose the highest-priority authorized specialist for safe fallback."""
        if not self._authorized_agents:
            raise CapabilityAuthorizationError("No authorized agents are available.")

        if "code" in self._authorized_agents:
            return "code"

        return max(
            self._authorized_agents,
            key=lambda name: (
                self.registry.get(name).priority,
                name,
            ),
        )

    def validate_selection(
        self,
        agents: Sequence[str],
        *,
        input_type: str = "text",
        output_type: str = "text",
    ) -> tuple[str, ...]:
        """Validate selected specialists before planning or execution."""
        if not agents:
            raise CapabilityAuthorizationError("At least one agent must be selected.")

        normalized = tuple(dict.fromkeys(agents))
        unknown = set(normalized) - set(self.registry.names())
        if unknown:
            names = ", ".join(sorted(unknown))
            raise CapabilityAuthorizationError(
                f"Unknown selected agents: {names}"
            )

        unauthorized = set(normalized) - set(self._authorized_agents)
        if unauthorized:
            names = ", ".join(sorted(unauthorized))
            raise CapabilityAuthorizationError(
                f"Unauthorized agent selection: {names}"
            )

        for agent_name in normalized:
            capability = self.registry.get(agent_name)
            self._validate_types(
                capability,
                input_type=input_type,
                output_type=output_type,
            )

        return normalized

    @staticmethod
    def _validate_types(
        capability: AgentCapability,
        *,
        input_type: str,
        output_type: str,
    ) -> None:
        if input_type not in capability.input_types:
            raise CapabilityAuthorizationError(
                f"Agent '{capability.name}' does not accept input type "
                f"'{input_type}'. Supported: {capability.input_types}"
            )

        if output_type not in capability.output_types:
            raise CapabilityAuthorizationError(
                f"Agent '{capability.name}' does not produce output type "
                f"'{output_type}'. Supported: {capability.output_types}"
            )

    def validate_agent_card(
        self,
        agent_type: str,
        card: AgentCard,
        *,
        input_type: str = "text",
        output_type: str = "text",
    ) -> None:
        """Validate a remote agent's advertised contract against local policy."""
        self.validate_selection(
            [agent_type],
            input_type=input_type,
            output_type=output_type,
        )

        expected = self.registry.get(agent_type).capabilities
        skill_text = " ".join(
            (
                skill.id,
                skill.name,
                skill.description or "",
                " ".join(skill.tags or ()),
                " ".join(skill.examples or ()),
            )
            for skill in card.skills
        ).casefold()

        if not any(
            capability.casefold() in skill_text
            for capability in expected
        ):
            raise CapabilityAuthorizationError(
                f"Remote agent '{agent_type}' does not advertise a compatible "
                "registered capability."
            )

        if input_type not in card.defaultInputModes:
            raise CapabilityAuthorizationError(
                f"Remote agent '{agent_type}' does not advertise input mode "
                f"'{input_type}'."
            )

        if output_type not in card.defaultOutputModes:
            raise CapabilityAuthorizationError(
                f"Remote agent '{agent_type}' does not advertise output mode "
                f"'{output_type}'."
            )
