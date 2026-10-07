# H8: Comprehensive Readiness Checks

The A2A `/readyz` endpoint now reports named startup-critical checks rather than only a binary process state.

Checks include:

- task manager availability
- Agent Card configuration and advertised skills
- Groq credential configuration
- persistent-memory namespace secret and database accessibility
- durable task-store readiness
- MCP endpoint host reachability
- remote-specialist URL, HTTPS, and credential configuration

The endpoint returns HTTP 200 only when every check is ready. Otherwise it returns HTTP 503 and includes non-sensitive diagnostic details.

Secrets and bearer credentials are never included in readiness output.

## Deployment alignment

Docker Compose now propagates the semantic-routing, authorization, memory, remote-A2A, and retry/timeout hardening settings into the A2A service.

The memory namespace secret remains optional at configuration syntax level so environments can start the container, but readiness fails closed until a real secret is provided.

The MCP readiness check verifies TCP reachability of the configured MCP host. It does not consume an SSE stream, which keeps readiness probes bounded and inexpensive.

Remote specialist readiness validates configuration locally; actual Agent Card capability validation still happens at remote-client initialization.
