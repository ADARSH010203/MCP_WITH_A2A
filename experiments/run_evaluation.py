"""Run the deterministic routing benchmark from the command line."""

import argparse
import json
from pathlib import Path

from app.evaluation.benchmark import format_report, load_cases, run_benchmark
from app.routing.router import MultiAgent


DEFAULT_CASES = Path(__file__).resolve().parent.parent / "benchmarks" / "routing_cases.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate routing and collaboration behavior.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES,
        help="Path to the benchmark JSON file.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path for a machine-readable JSON report.",
    )
    parser.add_argument(
        "--min-routing-accuracy",
        type=float,
        default=1.0,
        help="Minimum acceptable routing accuracy between 0 and 1.",
    )
    parser.add_argument(
        "--min-overall-accuracy",
        type=float,
        default=1.0,
        help="Minimum acceptable full-case accuracy between 0 and 1.",
    )
    args = parser.parse_args()

    if not 0.0 <= args.min_routing_accuracy <= 1.0:
        parser.error("--min-routing-accuracy must be between 0 and 1.")
    if not 0.0 <= args.min_overall_accuracy <= 1.0:
        parser.error("--min-overall-accuracy must be between 0 and 1.")

    report = run_benchmark(MultiAgent(agents={}), load_cases(args.cases))
    print(format_report(report))

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report.to_dict(), indent=2),
            encoding="utf-8",
        )

    passed = (
        report.routing_accuracy >= args.min_routing_accuracy
        and report.overall_accuracy >= args.min_overall_accuracy
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
