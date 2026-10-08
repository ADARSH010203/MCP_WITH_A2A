"""Small thread-safe in-process metrics registry for operational visibility."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Mapping
from threading import Lock


class MetricsRegistry:
    """Track bounded counters and latency samples without unbounded label growth."""

    def __init__(self, max_samples: int = 2048) -> None:
        if max_samples < 1:
            raise ValueError("max_samples must be positive")
        self.max_samples = max_samples
        self._counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self._samples: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            deque[float],
        ] = {}
        self._lock = Lock()

    @staticmethod
    def _key(
        name: str,
        labels: Mapping[str, str] | None,
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        normalized = tuple(
            sorted((str(key), str(value)) for key, value in (labels or {}).items())
        )
        return name, normalized

    def increment(
        self,
        name: str,
        amount: int = 1,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        if amount < 0:
            raise ValueError("metric increment must be non-negative")
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += amount

    def observe(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        if value < 0:
            raise ValueError("metric observation must be non-negative")
        key = self._key(name, labels)
        with self._lock:
            samples = self._samples.setdefault(
                key,
                deque(maxlen=self.max_samples),
            )
            samples.append(float(value))

    @staticmethod
    def _percentile(samples: list[float], percentile: float) -> float:
        if not samples:
            return 0.0
        ordered = sorted(samples)
        index = (len(ordered) - 1) * percentile
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = index - lower
        return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction

    @staticmethod
    def _escape_label(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
        )

    def prometheus(self) -> str:
        """Render a bounded Prometheus text exposition."""
        snapshot = self.snapshot()
        lines: list[str] = []

        for name, payload in snapshot["counters"].items():
            if not isinstance(payload, dict):
                continue
            value = payload.get("value", 0)
            labels = {
                str(key): str(value)
                for key, value in payload.items()
                if key != "value"
            }
            label_text = ""
            if labels:
                encoded = ", ".join(
                    f'{key}="{self._escape_label(value)}"'
                    for key, value in sorted(labels.items())
                )
                label_text = "{" + encoded + "}"
            lines.append(f"{name}{label_text} {value}")

        for name, payload in snapshot["latencies"].items():
            if not isinstance(payload, dict):
                continue
            base_labels = {
                str(key): str(value)
                for key, value in payload.items()
                if key not in {"count", "p50_ms", "p95_ms", "max_ms"}
            }
            for suffix in ("count", "p50_ms", "p95_ms", "max_ms"):
                value = payload.get(suffix, 0)
                label_text = ""
                if base_labels:
                    encoded = ", ".join(
                        f'{key}="{self._escape_label(value)}"'
                        for key, value in sorted(base_labels.items())
                    )
                    label_text = "{" + encoded + "}"
                metric_name = f"{name}_{suffix}"
                lines.append(f"{metric_name}{label_text} {value}")

        return "\n".join(lines) + ("\n" if lines else "")

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            counters = dict(self._counters)
            samples = {
                key: list(values)
                for key, values in self._samples.items()
            }

        counter_payload = {
            name: {
                **dict(labels),
                "value": value,
            }
            for (name, labels), value in counters.items()
        }
        histogram_payload = {}
        for (name, labels), values in samples.items():
            histogram_payload[name] = {
                **dict(labels),
                "count": len(values),
                "p50_ms": round(self._percentile(values, 0.50), 2),
                "p95_ms": round(self._percentile(values, 0.95), 2),
                "max_ms": round(max(values), 2) if values else 0.0,
            }

        return {
            "counters": counter_payload,
            "latencies": histogram_payload,
        }


METRICS = MetricsRegistry()
