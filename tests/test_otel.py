from app.observability.metrics import MetricsRegistry
from app.observability.otel import _parse_headers, span


def test_parse_otlp_headers():
    assert _parse_headers("Authorization=Bearer token,x-api-key=abc") == {
        "Authorization": "Bearer token",
        "x-api-key": "abc",
    }


def test_prometheus_renderer_escapes_labels():
    metrics = MetricsRegistry(max_samples=10)
    metrics.increment(
        "requests_total",
        labels={"method": "GET", "path": 'a"b\nc'},
    )

    rendered = metrics.prometheus()

    assert "requests_total{" in rendered
    assert 'method="GET"' in rendered
    assert 'path="a\\\"b\\\\nc"' in rendered


def test_prometheus_renderer_has_latency_series():
    metrics = MetricsRegistry(max_samples=10)
    metrics.observe("request_duration_ms", 12)
    metrics.observe("request_duration_ms", 20)

    rendered = metrics.prometheus()

    assert "request_duration_ms_count 2" in rendered
    assert "request_duration_ms_p50_ms 16.0" in rendered
    assert "request_duration_ms_p95_ms 19.6" in rendered
    assert "request_duration_ms_max_ms 20.0" in rendered


def test_span_context_is_available_without_exporter():
    with span("test.span", attributes={"test.value": 1}) as current:
        context = current.get_span_context()

    assert context.is_valid


def test_otlp_exporter_builds_trace_endpoint_and_payload(monkeypatch):
    from app.observability.otel import OTLPJsonSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry import trace

    provider = TracerProvider(resource=Resource.create({"service.name": "test-service"}))
    exporter = OTLPJsonSpanExporter(
        "https://collector.example.com",
        {},
        "test-service",
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("demo"):
        pass
    provider.shutdown()

    assert requests
    request, timeout = requests[0]
    assert request.full_url == "https://collector.example.com/v1/traces"
    assert timeout == 5.0
    assert b"test-service" in request.data
    trace.set_tracer_provider(trace.NoOpTracerProvider())
