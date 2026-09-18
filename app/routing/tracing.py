"""Structured execution tracing for multi-agent collaboration."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4


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
        self.started_at = datetime.now(timezone.utc)
        self._started_at_monotonic = __import__("time").perf_counter()
        self._events: list[TraceEvent] = []
        self._lock = Lock()

    @property
    def duration_ms(self) -> float:
        return round(
            (__import__("time").perf_counter() - self._started_at_monotonic) * 1000,
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
                details=dict(details or {}),
            )
            self._events.append(event)
            return event

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            events = [event.to_dict() for event in self._events]

        return {
            "trace_id": self.trace_id,
            "started_at": self.started_at.isoformat(),
            "duration_ms": self.duration_ms,
            "event_count": len(events),
            "events": events,
        }
