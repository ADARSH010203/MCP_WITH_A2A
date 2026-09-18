"""Build deterministic collaboration plans for the multi-agent coordinator."""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CollaborationStep:
    """One executable step in a collaboration plan."""

    agent: str
    purpose: str
    depends_on: tuple[str, ...] = ()
    parallel_group: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CollaborationPlan:
    """Structured execution plan produced before specialist work starts."""

    mode: str
    agents: tuple[str, ...]
    steps: tuple[CollaborationStep, ...]
    rationale: str
    handoffs: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "agents": list(self.agents),
            "steps": [step.to_dict() for step in self.steps],
            "rationale": self.rationale,
            "handoffs": {
                target: list(upstream)
                for target, upstream in self.handoffs.items()
            },
        }


class CollaborationPlanner:
    """Create a deterministic execution graph from selected specialists."""

    @staticmethod
    def _build_dependency_graph(
        agents: tuple[str, ...],
        dependency_map: dict[str, tuple[str, ...]],
    ) -> dict[str, tuple[str, ...]]:
        selected = set(agents)
        graph = {
            agent: tuple(
                dependency
                for dependency in dependency_map.get(agent, ())
                if dependency in selected
            )
            for agent in agents
        }

        for agent, dependencies in graph.items():
            if agent in dependencies:
                raise ValueError(
                    f"Agent dependency graph contains a self-dependency: {agent}"
                )

        return graph

    @staticmethod
    def _assign_parallel_groups(
        agents: tuple[str, ...],
        graph: dict[str, tuple[str, ...]],
    ) -> dict[str, int]:
        groups: dict[str, int] = {}
        remaining = set(agents)

        while remaining:
            ready = [
                agent
                for agent in agents
                if agent in remaining
                and all(dependency in groups for dependency in graph[agent])
            ]
            if not ready:
                raise ValueError("Agent dependency graph contains a cycle.")

            group = max((groups[d] for agent in ready for d in graph[agent]), default=0) + 1
            for agent in ready:
                groups[agent] = group
                remaining.remove(agent)

        return groups

    def build(
        self,
        query: str,
        agent_types: list[str],
        task_focus: dict[str, str],
        handoff_targets: dict[str, tuple[str, ...]],
        parallel_capabilities: dict[str, bool] | None = None,
    ) -> CollaborationPlan:
        del query

        agents = tuple(agent_types)
        if not agents:
            raise ValueError("At least one specialist agent is required.")

        dependency_map = self._build_dependency_graph(agents, handoff_targets)
        if parallel_capabilities is None:
            parallel_capabilities = {agent: True for agent in agents}

        if len(agents) == 1:
            agent = agents[0]
            return CollaborationPlan(
                mode="single-agent",
                agents=agents,
                steps=(
                    CollaborationStep(
                        agent=agent,
                        purpose=task_focus.get(agent, "Handle the user request."),
                    ),
                ),
                rationale="The request maps to one specialist domain.",
                handoffs={},
            )

        groups = self._assign_parallel_groups(agents, dependency_map)

        steps: list[CollaborationStep] = []
        for agent in agents:
            dependencies = dependency_map[agent]
            steps.append(
                CollaborationStep(
                    agent=agent,
                    purpose=task_focus.get(
                        agent,
                        "Use upstream findings to complete the task."
                        if dependencies
                        else "Provide specialist findings.",
                    ),
                    depends_on=dependencies,
                    parallel_group=groups[agent],
                )
            )

        # A non-parallel specialist gets an isolated execution group. All current
        # built-in specialists support parallel execution, but the registry can
        # disable it when a future agent needs shared state or serialization.
        for agent in agents:
            if parallel_capabilities.get(agent, True):
                continue
            group = groups[agent]
            for index, step in enumerate(steps):
                if step.agent == agent:
                    steps[index] = CollaborationStep(
                        agent=step.agent,
                        purpose=step.purpose,
                        depends_on=step.depends_on,
                        parallel_group=group + 1,
                    )
                elif step.parallel_group == group + 1:
                    steps[index] = CollaborationStep(
                        agent=step.agent,
                        purpose=step.purpose,
                        depends_on=step.depends_on,
                        parallel_group=group + 2,
                    )

        ordered_handoffs = {
            agent: dependency_map[agent]
            for agent in agents
            if dependency_map[agent]
        }
        critic_group = max(step.parallel_group for step in steps) + 1
        steps.append(
            CollaborationStep(
                agent="critic",
                purpose=(
                    "Review specialist findings, resolve contradictions, "
                    "and synthesize the final response."
                ),
                depends_on=agents,
                parallel_group=critic_group,
            )
        )

        return CollaborationPlan(
            mode="multi-agent",
            agents=agents,
            steps=tuple(steps),
            rationale=(
                "The request spans multiple specialist domains. The dependency "
                "graph determines which work can run in parallel, dependent work "
                "receives upstream findings, and the critic performs final synthesis."
            ),
            handoffs=ordered_handoffs,
        )
