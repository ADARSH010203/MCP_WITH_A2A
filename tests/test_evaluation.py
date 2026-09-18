from app.evaluation.benchmark import format_report, load_cases, run_benchmark
from app.evaluation.models import BenchmarkCase
from app.routing.router import MultiAgent


BENCHMARK_CASES = [
    BenchmarkCase(
        name="cnn_pipeline",
        query="Build a Python CNN image classification pipeline.",
        expected_agents=("deep_learning", "code"),
        expected_mode="multi-agent",
        expected_handoffs={"code": ("deep_learning",)},
    ),
    BenchmarkCase(
        name="binary_search",
        query="Explain binary search.",
        expected_agents=("dsa",),
        expected_mode="single-agent",
    ),
]


def test_load_cases_from_repository_fixture():
    cases = load_cases("benchmarks/routing_cases.json")
    assert len(cases) >= 10
    assert cases[0].name == "currency_exchange"


def test_benchmark_metrics_match_expected_routing():
    report = run_benchmark(MultiAgent(agents={}), BENCHMARK_CASES)

    assert report.total_cases == 2
    assert report.passed_cases == 2
    assert report.routing_accuracy == 1.0
    assert report.selection_accuracy == 1.0
    assert report.collaboration_accuracy == 1.0
    assert report.handoff_accuracy == 1.0
    assert report.average_latency_ms >= 0
    assert report.p95_latency_ms >= 0


def test_benchmark_report_serializes_case_results():
    report = run_benchmark(MultiAgent(agents={}), BENCHMARK_CASES)
    payload = report.to_dict()

    assert payload["overall_accuracy"] == 1.0
    assert payload["results"][0]["passed"] is True
    assert "latency_ms" in payload["results"][0]


def test_format_report_surfaces_metrics_and_failures():
    report = run_benchmark(
        MultiAgent(agents={}),
        [
            BenchmarkCase(
                name="intentional_failure",
                query="Explain CNNs.",
                expected_agents=("code",),
                expected_mode="single-agent",
            )
        ],
    )

    output = format_report(report)
    assert "Routing accuracy:" in output
    assert "Failures:" in output
    assert "intentional_failure" in output
