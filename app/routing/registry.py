"""Capability metadata for the built-in specialist agents."""

from dataclasses import dataclass
from typing import Callable


TriggerMatcher = Callable[[str, str], bool]


@dataclass(frozen=True)
class AgentCapability:
    """Describe what a specialist handles and how it participates in plans."""

    name: str
    capabilities: tuple[str, ...]
    triggers: tuple[tuple[str, int], ...]
    task_focus: str
    priority: int = 50
    dependencies: tuple[str, ...] = ()
    input_types: tuple[str, ...] = ("text",)
    output_types: tuple[str, ...] = ("text",)
    can_parallel: bool = True

    def score(self, text: str, matcher: TriggerMatcher) -> int:
        return sum(
            weight
            for trigger, weight in self.triggers
            if matcher(text, trigger)
        )


class AgentRegistry:
    """Validated registry used by routing and collaboration planning."""

    def __init__(self, capabilities: tuple[AgentCapability, ...]) -> None:
        self._capabilities = {item.name: item for item in capabilities}
        if len(self._capabilities) != len(capabilities):
            raise ValueError("Agent capability names must be unique.")
        self._validate_dependencies()

    def _validate_dependencies(self) -> None:
        unknown = {
            dependency
            for capability in self._capabilities.values()
            for dependency in capability.dependencies
            if dependency not in self._capabilities
        }
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown agent dependencies: {names}")
        self._validate_acyclic()

    def _validate_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(agent: str) -> None:
            if agent in visiting:
                raise ValueError("Agent dependency graph contains a cycle.")
            if agent in visited:
                return

            visiting.add(agent)
            for dependency in self._capabilities[agent].dependencies:
                visit(dependency)
            visiting.remove(agent)
            visited.add(agent)

        for agent in self._capabilities:
            visit(agent)

    def get(self, name: str) -> AgentCapability:
        try:
            return self._capabilities[name]
        except KeyError as exc:
            raise ValueError(f"Unknown agent type: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._capabilities)

    def items(self) -> tuple[AgentCapability, ...]:
        return tuple(self._capabilities.values())

    def score_all(self, text: str, matcher: TriggerMatcher) -> dict[str, int]:
        return {
            capability.name: capability.score(text, matcher)
            for capability in self.items()
            if capability.score(text, matcher) > 0
        }

    def task_focus_map(self) -> dict[str, str]:
        return {
            capability.name: capability.task_focus
            for capability in self.items()
        }

    def dependency_map(self) -> dict[str, tuple[str, ...]]:
        return {
            capability.name: capability.dependencies
            for capability in self.items()
            if capability.dependencies
        }

    def as_routes(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        return tuple(
            (capability.name, tuple(trigger for trigger, _weight in capability.triggers))
            for capability in self.items()
        )


DEFAULT_AGENT_REGISTRY = AgentRegistry(
    (
        AgentCapability(
            name="currency",
            capabilities=("currency", "foreign exchange", "exchange rates"),
            triggers=(
                ("currency", 3),
                ("exchange rate", 4),
                ("exchange rates", 4),
                ("forex", 3),
                ("usd", 1),
                ("eur", 1),
                ("gbp", 1),
            ),
            task_focus=(
                "Provide the relevant currency or exchange-rate facts and clearly "
                "state the rate/date returned by the currency tool."
            ),
            priority=90,
        ),
        AgentCapability(
            name="email",
            capabilities=("email writing", "professional communication"),
            triggers=(
                ("email", 4),
                ("mail", 2),
                ("draft an email", 5),
                ("professional message", 3),
                ("subject line", 3),
                ("letter", 2),
            ),
            task_focus=(
                "Focus on communication goals, recipient context, tone, structure, "
                "and a ready-to-use email."
            ),
            priority=80,
        ),
        AgentCapability(
            name="image",
            capabilities=("image generation", "visual design", "illustration"),
            triggers=(
                ("image", 3),
                ("picture", 2),
                ("photo", 2),
                ("illustration", 3),
                ("generate an image", 5),
                ("visual", 1),
            ),
            task_focus=(
                "Focus on the visual concept, composition, style, and concrete "
                "image-generation prompt requirements."
            ),
            priority=70,
        ),
        AgentCapability(
            name="game",
            capabilities=("game design", "gameplay", "level design"),
            triggers=(
                ("game", 4),
                ("gameplay", 3),
                ("level design", 4),
                ("character design", 3),
                ("game mechanics", 4),
                ("unity", 2),
                ("unreal engine", 2),
            ),
            task_focus=(
                "Focus on gameplay, mechanics, level/character design, and practical "
                "game-development decisions."
            ),
            priority=70,
        ),
        AgentCapability(
            name="deep_learning",
            capabilities=(
                "deep learning",
                "neural networks",
                "computer vision",
                "nlp",
                "transformers",
                "rag",
            ),
            triggers=(
                ("deep learning", 5),
                ("neural network", 4),
                ("neural networks", 4),
                ("model training", 2),
                ("cnn", 4),
                ("transformer", 4),
                ("transformer architecture", 5),
                ("pytorch", 2),
                ("tensorflow", 2),
                ("rag", 3),
                ("nlp", 3),
                ("graph neural network", 6),
                ("image classification", 5),
            ),
            task_focus=(
                "Focus on model architecture, data, training, evaluation, optimization, "
                "and ML-specific tradeoffs."
            ),
            priority=95,
        ),
        AgentCapability(
            name="reinforcement",
            capabilities=("reinforcement learning", "RL algorithms", "policy learning"),
            triggers=(
                ("reinforcement learning", 5),
                ("reinforcement", 3),
                ("q-learning", 5),
                ("policy gradient", 5),
                ("dqn", 5),
                ("deep reinforcement learning", 6),
            ),
            task_focus=(
                "Focus on environment, rewards, policies, learning algorithms, "
                "evaluation, and RL-specific tradeoffs."
            ),
            priority=95,
        ),
        AgentCapability(
            name="dsa",
            capabilities=("data structures", "algorithms", "complexity analysis"),
            triggers=(
                ("dsa", 5),
                ("data structures", 4),
                ("binary search", 5),
                ("sorting", 3),
                ("shortest path", 4),
                ("dynamic programming", 5),
                ("backtracking", 4),
                ("graph", 2),
                ("linked list", 4),
                ("binary tree", 4),
                ("heap", 3),
                ("stack", 3),
                ("queue", 3),
                ("graph algorithm", 5),
                ("graph traversal", 5),
            ),
            task_focus=(
                "Focus on algorithm choice, correctness, complexity, edge cases, "
                "and DSA reasoning."
            ),
            priority=90,
        ),
        AgentCapability(
            name="code",
            capabilities=(
                "software implementation",
                "debugging",
                "API development",
                "programming",
            ),
            triggers=(
                ("code", 4),
                ("program", 3),
                ("programming", 3),
                ("function", 2),
                ("class", 2),
                ("script", 2),
                ("algorithm", 2),
                ("python", 2),
                ("java", 2),
                ("javascript", 2),
                ("debug", 4),
                ("bug fix", 4),
                ("api", 3),
                ("implementation", 4),
            ),
            task_focus=(
                "Focus on implementation details, interfaces, maintainability, "
                "debugging, and runnable code where appropriate."
            ),
            priority=85,
            dependencies=(
                "deep_learning",
                "reinforcement",
                "dsa",
                "game",
                "image",
                "currency",
            ),
        ),
    )
)
