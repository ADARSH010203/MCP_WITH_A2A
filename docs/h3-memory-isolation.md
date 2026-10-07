# H3: Memory Isolation and Privacy

Persistent conversation memory is isolated by three dimensions:

1. authenticated principal
2. A2A session
3. specialist agent type

The database stores only opaque HMAC-derived scope keys. Raw principal, session, and agent identifiers are not stored in the conversation table.

The A2A server derives the principal from the bearer credential fingerprint. This means the bearer credential is never persisted as memory data. Deployments that require per-user isolation should issue distinct authenticated credentials per principal or place the service behind a trusted identity gateway.

A dedicated `A2A_MEMORY_NAMESPACE_SECRET` is required for persistent memory. The service fails closed when the secret is missing.

During local threaded execution, the request principal is propagated through the execution context so specialist agents use the same memory scope. The same context is inherited by asynchronous streaming tasks.

Legacy conversation tables are re-keyed during initialization with a legacy principal marker; raw legacy identity columns are then removed from the active schema.
