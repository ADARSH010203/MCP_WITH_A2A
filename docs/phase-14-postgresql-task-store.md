# Phase 14: PostgreSQL Task Store

Phase 14 adds a server-grade PostgreSQL backend behind the existing task-store contract.

## Backend selection

`A2A_TASK_STORE_BACKEND=sqlite` remains the default for local development.

`A2A_TASK_STORE_BACKEND=postgres` selects the PostgreSQL implementation and requires `A2A_TASK_DATABASE_URL`.

## PostgreSQL contract

The PostgreSQL store supports the same durable operations used by the coordinator:

- task creation with `ON CONFLICT DO NOTHING`
- direct task reads
- task persistence
- push-notification persistence
- retention cleanup
- atomic worker leases
- lease renewal
- lease release
- live-lease ownership checks

Worker leases are stored transactionally in PostgreSQL, so multiple A2A processes/hosts can coordinate task ownership through one shared database.

## Production deployment

`docker-compose.production.yml` provides a PostgreSQL 17 service and overlays the A2A service to use it.

Use a strong `POSTGRES_PASSWORD` and, for an external PostgreSQL deployment, prefer a TLS-enabled connection URL.

## Migration boundary

The code intentionally keeps SQLite as the development/default backend. Existing SQLite databases are not automatically copied into PostgreSQL by this phase; migration should be an explicit operational step.

## Remaining distributed limits

PostgreSQL removes the task-store single-process/database-file limitation, but the current A2A runtime still keeps active asyncio workers and SSE subscribers process-local.

An autonomous queue scheduler/worker fleet is still a separate phase. This phase establishes the server-grade persistence and distributed lease primitive required by that worker model.