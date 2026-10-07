# H7: Production Observability

H7 adds request correlation, redacted collaboration traces, operational counters, bounded latency samples, structured completion logging, and a protected `/metrics` endpoint.

## Request correlation

Each request receives an `X-Request-ID`. A caller-provided ID is accepted only when it matches a safe character/length policy; otherwise an opaque UUID is generated.

The request ID is carried into `CollaborationTrace` records and response headers.

## Trace privacy

Trace details are recursively redacted for keys containing common credential indicators such as token, secret, password, API key, authorization, and credential. Bearer tokens embedded in string values are also redacted.

User content is not added as a metric label.

## Metrics

The in-process metrics registry tracks:

- total HTTP requests by method/status
- failed HTTP requests
- request latency percentiles
- trace events
- specialist calls by registered agent/status
- retries
- handoffs
- completed requests

Latency samples are bounded to prevent unbounded in-memory growth.

## Metrics endpoint

`GET /metrics` returns the current JSON snapshot. When A2A authentication is configured, the same bearer credential protects the endpoint.

## Production limitation

The current registry is process-local. In a multi-instance deployment, each process has its own counters. A future production deployment should export these measurements to a centralized Prometheus/OpenTelemetry-compatible backend rather than relying on local process memory.

The observability layer intentionally keeps metric label cardinality small so arbitrary request IDs, session IDs, and user content are not promoted to labels.
