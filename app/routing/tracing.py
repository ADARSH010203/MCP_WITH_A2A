"""Structured execution tracing for multi-agent collaboration."""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from app.observability.context import get_request_id
from app.observability.metrics import METRICS


_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(token|secret|password|api[_-]?key|authorization|credential)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def _redact(value: Any, key: str = "") -> Any:
    """Recursively redact common secret-bearing values before tracing."""
    if _SENSITIVE_KEY_PATTERN.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {
            str(item_key): _redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    if isinstance(value, str):
        return _BEARER_PATTERN.sub("Bearer <redacted>", value)
    return value


@dataclass(frozen=True)
class TraceEvent:
    """One observable event in a collaboration run."""

    sequence: int
    stage: str
    actor: str
    status: str
    duration_ms: float | None = None
    attempt: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CollaborationTrace:
    """Thread-safe, in-process trace for one top-level agent request."""

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or uuid4().hex
        self.request_id = get_request_id()
        self.started_at = datetime.now(timezone.utc)
        self._started_at_monotonic = time.perf_counter()
        self._events: list[TraceEvent] = []
        self._lock = Lock()

    @property
    def duration_ms(self) -> float:
        return round(
            (time.perf_counter() - self._started_at_monotonic) * 1000,
            2,
        )

    def record(
        self,
        stage: str,
        actor: str,
        status: str,
        duration_ms: float | None = None,
        attempt: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> TraceEvent:
        redacted_details = _redact(dict(details or {}))

        with self._lock:
            event = TraceEvent(
                sequence=len(self._events) + 1,
                stage=stage,
                actor=actor,
                status=status,
                duration_ms=(
                    round(duration_ms, 2)
                    if duration_ms is not None
                    else None
                ),
                attempt=attempt,
                details=redacted_details,
            )
            self._events.append(event)

        METRICS.increment(
            "trace_events_total",
            labels={"stage": stage},
        )
        if stage == "specialist_started":
            METRICS.increment(
                "specialist_calls_started_total",
                labels={"agent": actor},
            )
        elif stage == "specialist_completed":
            METRICS.increment(
                "specialist_calls_completed_total",
                labels={"agent": actor, "status": status},
            )
        elif stage == "specialist_retry":
            METRICS.increment(
                "specialist_retries_total",
                labels={"agent": actor},
            )
        elif stage == "handoff" and status == "started":
            METRICS.increment(
                "handoffs_total",
                labels={"agent": actor},
            )
        elif stage == "request_completed":
            METRICS.increment(
                "requests_completed_total",
                labels={"status": status},
            )
            if duration_ms is not None:
                METRICS.observe(
                    "request_duration_ms",
                    duration_ms,
                )

        return event

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            events = [event.to_dict() for event in self._events]

        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "started_at": self.started_at.isoformat(),
            "duration_ms": self.duration_ms,
            "event_count": len(events),
            "events": events,
        }
