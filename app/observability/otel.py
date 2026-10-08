"""OpenTelemetry tracing configuration and OTLP JSON export."""

from __future__ import annotations

import atexit
import json
import threading
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExportResult,
    SpanExporter,
)


_PROVIDER: TracerProvider | None = None
_INITIALIZED = False
_LOCK = threading.Lock()


def _parse_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in raw.split(","):
        key, separator, value = item.partition("=")
        key = key.strip()
        if not separator or not key:
            continue
        headers[key] = value.strip()
    return headers


class OTLPJsonSpanExporter(SpanExporter):
    """Send spans to an OTLP/HTTP JSON endpoint without protobuf coupling."""

    def __init__(
        self,
        endpoint: str,
        headers: dict[str, str],
        service_name: str,
        timeout_seconds: float = 5.0,
    ) -> None:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OTLP endpoint must be an HTTP(S) URL.")
        path = parsed.path.rstrip("/")
        if not path.endswith("/v1/traces"):
            path += "/v1/traces"
        self.endpoint = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
        self.headers = {
            "Content-Type": "application/json",
            **headers,
        }
        self.service_name = service_name
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _value(value: Any) -> dict[str, Any] | None:
        if isinstance(value, bool):
            return {"boolValue": value}
        if isinstance(value, int):
            return {"intValue": str(value)}
        if isinstance(value, float):
            return {"doubleValue": value}
        if isinstance(value, str):
            return {"stringValue": value[:4096]}
        if isinstance(value, (list, tuple)):
            values = []
            for item in value:
                encoded = OTLPJsonSpanExporter._value(item)
                if encoded is not None:
                    values.append(encoded)
            return {"arrayValue": {"values": values}}
        return None

    def _span_payload(self, item: ReadableSpan) -> dict[str, Any]:
        context = item.context
        payload: dict[str, Any] = {
            "traceId": format(context.trace_id, "032x"),
            "spanId": format(context.span_id, "016x"),
            "name": item.name,
            "kind": "SPAN_KIND_INTERNAL",
            "startTimeUnixNano": str(item.start_time),
            "endTimeUnixNano": str(item.end_time),
        }
        if item.parent is not None:
            payload["parentSpanId"] = format(item.parent.span_id, "016x")

        attributes = []
        for key, value in item.attributes.items():
            encoded = self._value(value)
            if encoded is not None:
                attributes.append({"key": str(key), "value": encoded})
        if attributes:
            payload["attributes"] = attributes

        status_code = getattr(item.status, "status_code", None)
        if status_code is not None:
            payload["status"] = {"code": str(status_code)}
        return payload

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        if not spans:
            return SpanExportResult.SUCCESS

        payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": self.service_name},
                            }
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "mcp-a2a"},
                            "spans": [self._span_payload(item) for item in spans],
                        }
                    ],
                }
            ]
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(
                payload,
                separators=(",", ":"),
            ).encode("utf-8"),
            headers=self.headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ):
                return SpanExportResult.SUCCESS
        except Exception:
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        return None


def initialize_telemetry() -> None:
    """Initialize the process tracer once and optionally export over OTLP."""
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
            exporter = OTLPJsonSpanExporter(
                endpoint=settings.otel_exporter_otlp_endpoint,
                headers=_parse_headers(settings.otel_exporter_otlp_headers),
                service_name=settings.otel_service_name,
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
    """Create a span with bounded, non-sensitive attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as current_span:
        if attributes:
            for key, value in attributes.items():
                if isinstance(value, (str, int, float, bool)):
                    current_span.set_attribute(str(key), value)
        yield current_span
