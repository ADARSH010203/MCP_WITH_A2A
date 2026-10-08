# Phase 16: Distributed Live SSE Event Bus

Phase 13-15 establish durable task state, worker leases, PostgreSQL support, and autonomous recovery. Phase 16 closes the remaining live-event gap between multiple A2A worker processes.

## Architecture

```text
Client A
  │
  │ SSE
  ▼
A2A Worker A ───────┐
                    │ Redis Pub/Sub
A2A Worker B ◄──────┘
  │
  └── durable task state → PostgreSQL / SQLite
```

The worker that owns a task publishes task status/artifact events to the task channel. Every worker with an active SSE subscriber bridges that Redis channel into its local SSE queue.

## Configuration

`A2A_EVENT_BUS_BACKEND=memory` is the default and keeps the existing local-only behavior.

Set `A2A_EVENT_BUS_BACKEND=redis` and `A2A_EVENT_BUS_URL` to enable cross-process live events.

The Compose distributed profile starts Redis 7 with append-only persistence for the broker container:

```bash
docker compose --profile distributed up --build
```

## Safety properties

Event messages are size-bounded before publish.

Event types are allowlisted when decoded into A2A SSE models.

Redis failures do not fail the underlying task execution. The event layer falls back to local subscribers and the durable task record remains authoritative.

Shutdown cancels bridge tasks and closes the Redis client.

## Delivery semantics

The transport is live Pub/Sub, not durable event storage. A subscriber that reconnects after an event was published cannot replay missed intermediate events from Redis Pub/Sub.

The durable task store therefore remains the source of truth for current task status. This keeps the event bus lightweight and avoids coupling task correctness to broker history.

## Operational model

Multiple A2A processes can share the same PostgreSQL task store and Redis event bus. Worker leases prevent concurrent execution of the same task, while Redis distributes the resulting live updates to whichever worker is serving the client's SSE connection.

A future event-stream phase can replace Pub/Sub with Redis Streams or another durable log if strict event replay is required.
