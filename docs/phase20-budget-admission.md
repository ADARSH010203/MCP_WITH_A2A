# Phase 20: Budget Admission

Phase 20 adds a pre-execution budget admission layer on top of the persistent Phase 19 cost ledger.

## Flow

```
request
  -> deterministic/semantic plan
  -> estimate reservation
  -> atomic principal budget admission
  -> model execution
  -> final cost ledger record
  -> reservation release
```

Admission reserves estimated token/cost capacity before the first specialist call. Active reservations are included in daily and monthly principal budget checks, so concurrent requests cannot independently consume the same remaining budget.

## Persistence

SQLite uses an immediate transaction for reservation admission. PostgreSQL uses a transaction-scoped advisory lock keyed by the privacy-preserving principal key.

Reservations have an expiry so abandoned workers cannot hold budget capacity forever.

## Estimation

Input tokens are conservatively estimated from request characters. Output reservation is based on the configured per-agent reservation and the collaboration plan. If a per-task maximum token/cost policy is configured, the reservation uses that upper bound.

This is intentionally an admission estimate, not a replacement for provider-reported token usage. Final usage is still recorded by the Phase 19 ledger.

## Rejection

If the principal has insufficient daily/monthly capacity, the request returns `budget_rejected` before any specialist model execution.

`A2A_BUDGET_ADMISSION_ENABLED=false` disables this layer without disabling Phase 19 cost recording.
