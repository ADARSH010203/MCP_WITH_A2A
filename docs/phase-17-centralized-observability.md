# Phase 17: Centralized Observability

Phase 17 turns the local debugging-oriented observability layer into a production integration point for centralized telemetry.

## OpenTelemetry

Each A2A HTTP request creates an OpenTelemetry span named `a2a.http.request`.

Specialist executions create `a2a.specialist.invoke` spans with bounded attributes for agent type, execution mode, attempt, and result status.

The tracer provider is process-global and initialized once. When `OTEL_EXPORTER_OTLP_ENDPOINT` is configured, spans are exported through OTLP HTTP. Without an endpoint, spans remain local to the process for instrumentation/testing.

No user prompt, session identifier, bearer token, API key, or arbitrary request payload is promoted to a span attribute.

## Correlation

Requests return `X-Request-ID`, `X-Trace-ID`, and `X-Span-ID` headers. The request ID also appears in structured server logs and collaboration traces.

## Prometheus

`GET /metrics` continues to support the existing JSON snapshot. Clients that advertise `text/plain` receive Prometheus-compatible text exposition.

The renderer keeps metric labels bounded to operational dimensions such as method, HTTP status, agent type, and trace stage. Arbitrary user data and request IDs are not metric labels.

Set `PROMETHEUS_METRICS_ENABLED=false` to disable the metrics surface.

## Centralized deployment

A Kubernetes, VM, or Compose deployment can point `OTEL_EXPORTER_OTLP_ENDPOINT` at an OpenTelemetry Collector. The collector can fan out traces to the operator's tracing backend while each process exposes Prometheus metrics for scraping.

The application itself remains vendor-neutral.

## Current boundary

The application metrics registry is still process-local. Prometheus aggregation occurs at the monitoring layer by scraping every instance. OTLP provides centralized trace export.

A future cost-governance phase can add centralized token/cost metrics using the same telemetry contract.
