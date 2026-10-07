"""Run the live LLM quality evaluation benchmark."""

import argparse
import json
from pathlib import Path

from app.evaluation.quality import (
    LLMQualityEvaluator,
    build_quality_report,
    load_quality_cases,
)
from app.routing.router import MultiAgent


DEFAULT_CASES = (
    Path(__file__).resolve().parent.parent / "benchmarks" / "quality_cases.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a real LLM judge over specialist responses."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-overall-score", type=float, default=0.75)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit must be non-negative.")
    if not 0.0 <= args.min_overall_score <= 1.0:
        parser.error("--min-overall-score must be between 0 and 1.")

    cases = load_quality_cases(args.cases)
    if args.limit:
        cases = cases[:args.limit]

    router = MultiAgent(agents={})
    evaluator = LLMQualityEvaluator(
        min_overall_score=args.min_overall_score,
    )

    results = []
    for case in cases:
        response = router.invoke(case.query, f"quality-eval:{case.name}")
        result = evaluator.evaluate_response(
            case,
            str(response.get("content", "")),
        )
        results.append(result)
        print(
            f"{case.name}: "
            f"{result.overall_score:.1%} "
            f"{'PASS' if result.passed else 'FAIL'}"
        )

    report = build_quality_report(results)
    print(
        f"Overall: {report.average_score:.1%}; "
        f"Pass rate: {report.pass_rate:.1%}; "
        f"Minimum: {report.minimum_score:.1%}"
    )

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report.to_dict(), indent=2),
            encoding="utf-8",
        )

    return 0 if report.pass_rate == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
