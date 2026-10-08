# Phase 15: Autonomous Task Recovery

Phase 15 adds a background recovery worker on top of the Phase 13 lease primitive.

## Recovery loop

Each A2A worker can periodically query the durable task store for submitted tasks or working tasks whose lease is no longer live.

For every candidate, the normal idempotent `tasks/send` execution path is reused. The same worker lease rules therefore protect normal requests and recovery requests.

## Crash recovery

If a process dies after persisting a task as working, its lease eventually expires. Another worker can then claim the task and resume execution without requiring a client to resend the request.

If a task was persisted as submitted before the original worker reached execution, the recovery worker can pick it up automatically.

## Safety

Live leases are never reclaimed. Concurrent recovery attempts are resolved by the durable atomic claim operation.

The worker has bounded polling and batch-size settings so recovery work cannot become an unbounded database scan.

## Lifecycle

The A2A server starts the recovery worker during application startup and stops it during shutdown.

## Remaining boundary

Active SSE subscribers and already-running Python workers remain process-local. Recovery restores execution ownership from durable task state, but it cannot reconstruct an SSE connection that existed on a failed host.

The recovery worker also does not provide a general distributed message broker. PostgreSQL task storage plus leases is the durable coordination layer; a dedicated broker can be added later if task throughput requires queue semantics or stronger delivery guarantees.