"""Validate the real LLM quality evaluation dataset without calling an LLM."""

from pathlib import Path

from app.evaluation.quality import load_quality_cases


DEFAULT_CASES = (
    Path(__file__).resolve().parent.parent / "benchmarks" / "quality_cases.json"
)


def main() -> int:
    cases = load_quality_cases(DEFAULT_CASES)
    print(f"Validated {len(cases)} LLM quality evaluation cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
