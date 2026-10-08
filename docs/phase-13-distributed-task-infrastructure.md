# Phase 13: Distributed Task Infrastructure

Phase 13 introduces durable task ownership across independent A2A worker processes.

## Durable source of truth

Task reads and creation now consult the persistent task store instead of relying only on a process-local task dictionary.

Task creation uses an atomic database operation so concurrent workers cannot both become the creator of the same task.

## Worker leases

Each task execution is protected by a database-backed lease:

- a worker claims the task with a bounded lease
- another worker cannot claim the same live lease
- the owning worker renews the lease periodically
- the lease is released only after terminal state persistence
- an expired lease can be claimed by another worker

This closes the most important multi-process duplicate-execution race in the current architecture.

## Failover semantics

A task left in submitted or working state can be picked up again when another request for the same idempotent task arrives after the previous lease expires.

This increment uses request-driven failover. An autonomous distributed worker scheduler/queue is still a separate concern.

## Current boundary

The implementation uses the existing SQLite task store, so workers must share the same durable database.

This improves coordination across processes using a shared SQLite deployment, but SQLite is not the target datastore for a large multi-host deployment. The next infrastructure step should move the same task-store/lease contract to PostgreSQL or another server-grade transactional database.

The in-process SSE subscriber registry and active asyncio workers remain process-local. A worker on another host can recover task execution, but it cannot inherit an existing in-memory SSE stream.

## Configuration

`A2A_TASK_LEASE_SECONDS` controls the default lease duration.

`A2A_WORKER_ID` may be set to a stable operator-visible worker identifier; when omitted, each process receives an ephemeral hostname + UUID identity.

Worker IDs are coordination metadata, not authentication credentials, and should not contain secrets.
