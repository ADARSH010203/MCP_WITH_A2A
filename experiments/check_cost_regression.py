"""Check deterministic specialist-call budgets for representative workloads."""

from app.config.settings import settings
from app.routing.router import MultiAgent


CASES = (
    ("currency", "Convert USD to EUR.", 1),
    ("email", "Write a professional email to a recruiter.", 1),
    (
        "deep-learning-code",
        "Build a CNN image classification pipeline and provide Python code.",
        4,
    ),
    (
        "reinforcement-code",
        "Explain Q-learning and implement a training example.",
        4,
    ),
)


def main() -> int:
    router = MultiAgent(agents={})
    failures = []

    for name, query, expected_max_calls in CASES:
        plan = router.build_collaboration_plan(query)
        critic_calls = 1 if plan.mode == "multi-agent" else 0
        estimated_calls = len(plan.agents) + critic_calls

        if estimated_calls > expected_max_calls:
            failures.append(
                f"{name}: estimated {estimated_calls} calls > expected max "
                f"{expected_max_calls}"
            )
        if estimated_calls > settings.a2a_max_agent_calls_per_task:
            failures.append(
                f"{name}: estimated {estimated_calls} calls > global budget "
                f"{settings.a2a_max_agent_calls_per_task}"
            )

    if failures:
        for failure in failures:
            print(failure)
        return 1

    print(
        f"Cost regression gate passed for {len(CASES)} workloads. "
        f"Global specialist-call budget={settings.a2a_max_agent_calls_per_task}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
