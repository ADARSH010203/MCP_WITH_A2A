"""Data models for deterministic routing benchmarks."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BenchmarkCase:
    """One routing or collaboration expectation."""

    name: str
    query: str
    expected_agents: tuple[str, ...]
    expected_mode: str | None = None
    expected_handoffs: dict[str, tuple[str, ...]] | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkCase":
        handoffs = payload.get("expected_handoffs")
        return cls(
            name=str(payload["name"]),
            query=str(payload["query"]),
            expected_agents=tuple(str(agent) for agent in payload["expected_agents"]),
            expected_mode=(
                None if payload.get("expected_mode") is None else str(payload["expected_mode"])
            ),
            expected_handoffs=(
                None
                if handoffs is None
                else {
                    str(target): tuple(str(agent) for agent in upstream)
                    for target, upstream in handoffs.items()
                }
            ),
        )


@dataclass(frozen=True)
class BenchmarkResult:
    """Observed result for one benchmark case."""

    name: str
    query: str
    expected_agents: tuple[str, ...]
    selected_agents: tuple[str, ...]
    expected_mode: str | None
    actual_mode: str
    expected_handoffs: dict[str, tuple[str, ...]]
    actual_handoffs: dict[str, tuple[str, ...]]
    routing_passed: bool
    selection_passed: bool
    collaboration_passed: bool
    handoff_passed: bool
    latency_ms: float

    @property
    def passed(self) -> bool:
        return (
            self.routing_passed
            and self.selection_passed
            and self.collaboration_passed
            and self.handoff_passed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "query": self.query,
            "expected_agents": list(self.expected_agents),
            "selected_agents": list(self.selected_agents),
            "expected_mode": self.expected_mode,
            "actual_mode": self.actual_mode,
            "expected_handoffs": {
                target: list(upstream)
                for target, upstream in self.expected_handoffs.items()
            },
            "actual_handoffs": {
                target: list(upstream)
                for target, upstream in self.actual_handoffs.items()
            },
            "routing_passed": self.routing_passed,
            "selection_passed": self.selection_passed,
            "collaboration_passed": self.collaboration_passed,
            "handoff_passed": self.handoff_passed,
            "passed": self.passed,
            "latency_ms": round(self.latency_ms, 3),
        }


@dataclass(frozen=True)
class BenchmarkReport:
    """Aggregate metrics for a benchmark run."""

    total_cases: int
    passed_cases: int
    routing_accuracy: float
    selection_accuracy: float
    collaboration_accuracy: float
    handoff_accuracy: float
    average_latency_ms: float
    p95_latency_ms: float
    results: tuple[BenchmarkResult, ...]

    @property
    def overall_accuracy(self) -> float:
        if not self.total_cases:
            return 1.0
        return self.passed_cases / self.total_cases

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "overall_accuracy": round(self.overall_accuracy, 4),
            "routing_accuracy": round(self.routing_accuracy, 4),
            "selection_accuracy": round(self.selection_accuracy, 4),
            "collaboration_accuracy": round(self.collaboration_accuracy, 4),
            "handoff_accuracy": round(self.handoff_accuracy, 4),
            "average_latency_ms": round(self.average_latency_ms, 3),
            "p95_latency_ms": round(self.p95_latency_ms, 3),
            "results": [result.to_dict() for result in self.results],
        }
