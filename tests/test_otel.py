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
    assert 'path="a\"b\\nc"' in rendered


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
