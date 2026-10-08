# Phase 18: Cost Governance

Phase 18 adds provider-usage accounting and operator-configured cost controls to the multi-agent runtime.

## Usage accounting

Local specialist and critic agents extract token usage from LangChain model messages.

Supported usage shapes include:

- `usage_metadata.input_tokens/output_tokens`
- `response_metadata.token_usage.prompt_tokens/completion_tokens`

Remote specialists can report the same `usage` payload. When a provider does not return usage metadata, the system records an explicit `llm_usage_missing_total` metric rather than guessing from text length.

## Cost estimation

Provider pricing is not hardcoded.

Operators configure:

- `A2A_COST_INPUT_USD_PER_1M_TOKENS`
- `A2A_COST_OUTPUT_USD_PER_1M_TOKENS`

The evaluator computes a deterministic estimated USD value from observed tokens.

A zero rate is allowed when only usage accounting is required or pricing is intentionally managed outside the service.

## Hard task budgets

One shared budget covers every model call in a top-level request:

- specialist calls
- specialist retries
- critic synthesis

Optional limits:

- `A2A_MAX_TOTAL_TOKENS_PER_TASK`
- `A2A_MAX_ESTIMATED_COST_USD_PER_TASK`

When a limit is exceeded, completed usage is retained for reporting, the current result is marked as budget-exceeded, and no additional model call is started.

Parallel specialists already in flight cannot be retroactively stopped; the budget prevents subsequent calls and records the final observed usage.

## Telemetry

The cost layer exports bounded Prometheus-compatible metrics through the existing Phase 17 metrics registry:

- `llm_input_tokens_total`
- `llm_output_tokens_total`
- `llm_estimated_cost_usd`
- `llm_usage_missing_total`
- `llm_cost_budget_exceeded_total`

Agent type and execution mode are the only cost metric labels.

The response also includes a bounded `cost` object with cumulative task usage and estimated cost.

## Governance boundary

This is an estimation and enforcement layer, not a billing system.

A production deployment should periodically reconcile these estimates against the provider's authoritative billing export. Centralized cost attribution, organizational budgets, model-specific pricing catalogs, and finance reconciliation can be built on the same telemetry contract later.

No current provider price is embedded in source code, which avoids silently becoming incorrect when provider pricing changes.
