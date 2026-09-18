"""Run deterministic routing and collaboration benchmarks."""

import json
import time
from pathlib import Path
from statistics import mean
from typing import Any

from app.evaluation.models import BenchmarkCase, BenchmarkReport, BenchmarkResult
from app.routing.router import MultiAgent


def load_cases(path: str | Path) -> list[BenchmarkCase]:
    """Load benchmark cases from a JSON file."""
    benchmark_path = Path(path)
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Benchmark file must contain a JSON list.")
    return [BenchmarkCase.from_dict(item) for item in payload]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _expected_handoffs(case: BenchmarkCase) -> dict[str, tuple[str, ...]]:
    return case.expected_handoffs or {}


def evaluate_case(router: MultiAgent, case: BenchmarkCase) -> BenchmarkResult:
    """Evaluate one case without invoking an LLM or external service."""
    started = time.perf_counter()
    selected = tuple(router.select_agent_types(case.query))
    plan = router.build_collaboration_plan(case.query, list(selected))
    elapsed_ms = (time.perf_counter() - started) * 1000

    expected_handoffs = _expected_handoffs(case)
    actual_handoffs = {
        target: tuple(upstream)
        for target, upstream in plan.handoffs.items()
    }

    routing_passed = bool(selected) and selected[0] == case.expected_agents[0]
    selection_passed = set(selected) == set(case.expected_agents)
    collaboration_passed = (
        case.expected_mode is None or plan.mode == case.expected_mode
    )
    handoff_passed = (
        not expected_handoffs
        or all(actual_handoffs.get(target) == upstream for target, upstream in expected_handoffs.items())
    )

    return BenchmarkResult(
        name=case.name,
        query=case.query,
        expected_agents=case.expected_agents,
        selected_agents=selected,
        expected_mode=case.expected_mode,
        actual_mode=plan.mode,
        expected_handoffs=expected_handoffs,
        actual_handoffs=actual_handoffs,
        routing_passed=routing_passed,
        selection_passed=selection_passed,
        collaboration_passed=collaboration_passed,
        handoff_passed=handoff_passed,
        latency_ms=elapsed_ms,
    )


def run_benchmark(router: MultiAgent, cases: list[BenchmarkCase]) -> BenchmarkReport:
    """Run all benchmark cases and calculate regression metrics."""
    results = tuple(evaluate_case(router, case) for case in cases)
    latencies = [result.latency_ms for result in results]

    return BenchmarkReport(
        total_cases=len(results),
        passed_cases=sum(result.passed for result in results),
        routing_accuracy=(
            mean(result.routing_passed for result in results) if results else 1.0
        ),
        selection_accuracy=(
            mean(result.selection_passed for result in results) if results else 1.0
        ),
        collaboration_accuracy=(
            mean(result.collaboration_passed for result in results) if results else 1.0
        ),
        handoff_accuracy=(
            mean(result.handoff_passed for result in results) if results else 1.0
        ),
        average_latency_ms=mean(latencies) if latencies else 0.0,
        p95_latency_ms=_percentile(latencies, 0.95),
        results=results,
    )


def format_report(report: BenchmarkReport) -> str:
    """Return a compact human-readable benchmark summary."""
    lines = [
        f"Cases: {report.passed_cases}/{report.total_cases} passed",
        f"Routing accuracy: {report.routing_accuracy:.1%}",
        f"Selection accuracy: {report.selection_accuracy:.1%}",
        f"Collaboration accuracy: {report.collaboration_accuracy:.1%}",
        f"Handoff accuracy: {report.handoff_accuracy:.1%}",
        f"Average decision latency: {report.average_latency_ms:.2f} ms",
        f"P95 decision latency: {report.p95_latency_ms:.2f} ms",
    ]

    failed = [result for result in report.results if not result.passed]
    if failed:
        lines.append("Failures:")
        lines.extend(
            f"- {result.name}: expected {list(result.expected_agents)}, "
            f"got {list(result.selected_agents)}"
            for result in failed
        )
    return "\\n".join(lines)
