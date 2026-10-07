# H10: CI/CD Quality Gates

The CI pipeline now enforces multiple independent quality gates before a change can be merged.

## Unit and regression

The existing root test suite runs as the deterministic unit/regression gate. It covers routing, planning, memory, security, MCP, observability, readiness, retry behavior, and evaluation components.

## Integration

Dedicated tests under `tests/integration/` exercise the A2A HTTP boundary, task manager, response serialization, request correlation, and metrics exposure together.

## Safety

Dedicated tests under `tests/safety/` enforce security invariants such as capability authorization, HTTPS-only remote configuration, opaque memory identifiers, and workspace confinement.

## LLM evaluation dataset

Standard CI validates the structure and integrity of the real-LLM quality dataset. Live Groq evaluation remains a separate manually triggered workflow because it consumes an external API budget.

## Routing benchmark

The deterministic routing benchmark must maintain its configured perfect-score gate.

## Cost regression

The cost gate checks representative deterministic workloads against explicit maximum specialist-call budgets and the global call-budget setting.

This is a model-call regression guard, not a billing estimator. Actual token/cost telemetry belongs to a future external observability/cost-control integration.

## Merge rule

A pull request is considered engineering-ready only when the required CI workflow completes successfully. A red gate blocks merge and must be fixed before the next hardening phase.
