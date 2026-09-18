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
    """Create a small, deterministic execution plan from selected specialists."""

    def build(
        self,
        query: str,
        agent_types: list[str],
        task_focus: dict[str, str],
        handoff_targets: dict[str, tuple[str, ...]],
    ) -> CollaborationPlan:
        del query  # The first phase plans from coordinator decisions, not an LLM.

        agents = tuple(agent_types)
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

        selected = set(agents)
        dependencies: dict[str, tuple[str, ...]] = {}
        for target, upstream_types in handoff_targets.items():
            if target not in selected:
                continue
            upstream = tuple(
                agent
                for agent in agents
                if agent in upstream_types
            )
            if upstream:
                dependencies[target] = upstream

        steps: list[CollaborationStep] = []
        lead_agents = [
            agent
            for agent in agents
            if agent not in dependencies
        ]

        for agent in lead_agents:
            steps.append(
                CollaborationStep(
                    agent=agent,
                    purpose=task_focus.get(agent, "Provide specialist findings."),
                    parallel_group=1,
                )
            )

        dependent_group = 2 if dependencies else 1
        for agent in agents:
            if agent not in dependencies:
                continue
            steps.append(
                CollaborationStep(
                    agent=agent,
                    purpose=task_focus.get(agent, "Use upstream findings to complete the task."),
                    depends_on=dependencies[agent],
                    parallel_group=dependent_group,
                )
            )

        steps.append(
            CollaborationStep(
                agent="critic",
                purpose="Review specialist findings, resolve contradictions, and synthesize the final response.",
                depends_on=agents,
                parallel_group=dependent_group + 1,
            )
        )

        rationale = (
            "The request spans multiple specialist domains. Independent work runs "
            "in parallel, dependent work receives upstream findings, and the critic "
            "performs the final synthesis."
        )

        return CollaborationPlan(
            mode="multi-agent",
            agents=agents,
            steps=tuple(steps),
            rationale=rationale,
            handoffs=dependencies,
        )
