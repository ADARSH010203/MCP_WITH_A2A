# Phase 21: Principal-Aware Client Credentials

Phase 21 adds explicit client credentials for tenant/principal-isolated memory and cost governance.

## Configuration

Use `A2A_PRINCIPAL_API_KEYS` with semicolon-separated `principal_id=api_key` pairs:

```env
A2A_API_KEY=optional-shared-operator-key
A2A_PRINCIPAL_API_KEYS=tenant-a=replace-with-random-key-a;tenant-b=replace-with-random-key-b
```

Generate a unique high-entropy secret for each principal. Do not reuse keys between principals. The parser rejects invalid or duplicate principal IDs, repeated credentials, collision with the shared operator key, empty keys, and more than 100 configured principals.

## Identity and isolation

Each valid principal key maps to a stable server-side identity, `client:<principal_id>`. The raw API key is never used as the stored principal ID. The existing cost ledger HMACs principal identities before persistence, and persistent memory derives an opaque scope key from the principal, session, and agent.

This means that when tenant-specific keys are used, the same session ID does not merge memory across tenants and daily/monthly cost reporting uses the correct principal scope.

## Authentication behavior

- A configured principal key is accepted even when the shared `A2A_API_KEY` is empty.
- Unknown keys are rejected with HTTP 401.
- The shared `A2A_API_KEY` remains supported for existing single-client/operator deployments.
- If authentication is disabled entirely for a local demo, requests share the single `anonymous` principal rather than allowing arbitrary bearer strings to create new identities.
- `/costs` reports only the authenticated principal's usage.
- `/metrics` requires a valid configured credential whenever authentication is enabled.

Authentication still runs before JSON-RPC parsing and model execution. Rate limits, capability policy, and budget admission remain separate enforcement layers.

## Operational notes

The credentials are loaded from environment configuration and held in process memory. Use a secret manager or deployment secrets in production, rotate keys deliberately, and never commit live keys to the repository.
