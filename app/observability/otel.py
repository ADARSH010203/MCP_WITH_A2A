"""OpenTelemetry tracing configuration and span helpers."""

from __future__ import annotations

import atexit
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_PROVIDER: TracerProvider | None = None
_INITIALIZED = False
_LOCK = Lock()


def _parse_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in raw.split(","):
        key, separator, value = item.partition("=")
        key = key.strip()
        if not separator or not key:
            continue
        headers[key] = value.strip()
    return headers


def initialize_telemetry() -> None:
    """Initialize the process tracer once, optionally exporting over OTLP."""
    global _INITIALIZED, _PROVIDER

    with _LOCK:
        if _INITIALIZED:
            return

        from app.config.settings import settings

        if not settings.otel_enabled:
            _INITIALIZED = True
            return

        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": settings.otel_service_name,
                    "service.version": "1.0.0",
                }
            )
        )

        if settings.otel_exporter_otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )
            except ImportError as exc:
                raise RuntimeError(
                    "OTLP exporter dependency is missing while telemetry export is enabled."
                ) from exc

            exporter = OTLPSpanExporter(
                endpoint=settings.otel_exporter_otlp_endpoint,
                headers=_parse_headers(settings.otel_exporter_otlp_headers),
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        _PROVIDER = provider
        _INITIALIZED = True

def shutdown_telemetry() -> None:
    """Flush the process-global tracer provider at process exit."""
    provider = _PROVIDER
    if provider is not None:
        provider.shutdown()


atexit.register(shutdown_telemetry)


def get_tracer(name: str = "mcp-a2a") -> trace.Tracer:
    """Return the application tracer after lazy initialization."""
    initialize_telemetry()
    return trace.get_tracer(name)


@contextmanager
def span(
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
) -> Iterator[trace.Span]:
    """Create a span with only bounded, non-secret attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as current_span:
        if attributes:
            for key, value in attributes.items():
                if isinstance(value, (str, int, float, bool)):
                    current_span.set_attribute(str(key), value)
        yield current_span
