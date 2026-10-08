# Phase 19: Persistent Cost Ledger and Budget Governance

Phase 19 moves cost accounting from process-local task results into a durable attribution ledger.

## Durable backend

The ledger follows the configured task-state backend:

- SQLite uses `A2A_TASK_DB_PATH`
- PostgreSQL uses `A2A_TASK_DATABASE_URL`

This keeps task state and cost attribution on the same durable infrastructure.

## Privacy

The ledger never stores the raw principal identity. It stores an HMAC-derived principal key using the existing memory namespace secret.

Task records contain token counts, estimated cost, status, specialist names, and timestamps. User prompts, responses, bearer tokens, and raw session identifiers are not written to the ledger.

## Idempotency

Each top-level coordinator invocation uses its trace ID as the ledger task key. Duplicate writes for the same key are ignored by both SQLite and PostgreSQL.

## Per-principal reporting

The protected `GET /costs` endpoint reports the authenticated principal's:

- current-day token usage
- current-day estimated cost
- current-month token usage
- current-month estimated cost
- task count
- configured daily/monthly budget limits

The endpoint returns only the caller's principal-scoped report.

Cost reporting requires the server's A2A bearer authentication. An unauthenticated cost report is never exposed.

## Budget governance

Phase 18 already enforces per-task token/USD limits while a task is executing.

Phase 19 adds durable daily/monthly principal budget visibility. These rolling budgets are reporting/governance controls; they do not retroactively stop tokens already spent by in-flight calls. A future admission controller can use the same ledger to reject new tasks before execution when a principal has exceeded an organizational budget.

## Provider billing boundary

Estimated USD cost remains configuration-driven. Provider pricing is not hardcoded.

The ledger is an internal attribution source, not an authoritative billing export. Production finance reconciliation should compare ledger estimates with provider billing data and account for credits, discounts, cached tokens, and provider-specific pricing rules.

## Operations

The ledger table is indexed by principal key and timestamp for efficient daily/monthly reporting.

When PostgreSQL is used, all workers share the same ledger. When SQLite is used, the existing single-node deployment guarantees remain unchanged; multi-process shared-state deployments should use PostgreSQL.

## Endpoint example

Authenticated:

`GET /costs`

Returns a principal-scoped report similar to:

```json
{
  "principal_scoped": true,
  "daily": {
    "input_tokens": 1200,
    "output_tokens": 500,
    "total_tokens": 1700,
    "estimated_cost_usd": 0.012,
    "tasks": 4
  },
  "monthly": {
    "input_tokens": 12000,
    "output_tokens": 5000,
    "total_tokens": 17000,
    "estimated_cost_usd": 0.12,
    "tasks": 37
  },
  "budget": {
    "within_budget": true
  }
}
```

No raw principal identifier is returned.
