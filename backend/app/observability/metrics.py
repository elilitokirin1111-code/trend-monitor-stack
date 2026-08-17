"""Process-local metrics registry with Prometheus text rendering.

Business signals (provider success, stale age, fallback ratio, report and
delivery state) are aggregated from the database by ``PipelineMonitor``;
this registry covers low-level runtime counters such as request volume,
request latency and pipeline step outcomes.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(slots=True)
class MetricsRegistry:
    _counters: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    _gauges: dict[str, float] = field(default_factory=dict)
    _latencies: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, name: str, labels: Mapping[str, str] | None = None, value: int = 1) -> None:
        key = _key(name, labels)
        with self._lock:
            self._counters[key] += value

    def set_gauge(self, name: str, labels: Mapping[str, str] | None, value: float) -> None:
        key = _key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def observe(self, name: str, labels: Mapping[str, str] | None, seconds: float) -> None:
        key = _key(name, labels)
        with self._lock:
            self._latencies[key].append(seconds)

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "latencies": {
                    key: _summary(values) for key, values in self._latencies.items()
                },
            }

    def render_prometheus(self) -> str:
        snapshot = self.snapshot()
        lines: list[str] = []
        for key, value in sorted(snapshot["counters"].items()):
            lines.append(f"{_prom(key)} {value}")
        for key, value in sorted(snapshot["gauges"].items()):
            lines.append(f"{_prom(key)} {value}")
        for key, value in sorted(snapshot["latencies"].items()):
            count, total = value["count"], value["total"]
            lines.append(f"{_prom(key + '_count')} {count}")
            lines.append(f"{_prom(key + '_sum')} {total}")
        return "\n".join(lines) + ("\n" if lines else "")


registry = MetricsRegistry()


def _key(name: str, labels: Mapping[str, str] | None) -> str:
    if not labels:
        return name
    pairs = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{pairs}}}"


def _prom(key: str) -> str:
    return key.replace("{", "{").replace("}", "}")


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "total": 0.0, "avg": 0.0, "max": 0.0}
    return {
        "count": len(values),
        "total": sum(values),
        "avg": sum(values) / len(values),
        "max": max(values),
    }


class timed:
    """Context manager that observes elapsed seconds on the registry."""

    def __init__(self, name: str, labels: Mapping[str, str] | None = None) -> None:
        self._name = name
        self._labels = labels
        self._started: float | None = None

    def __enter__(self) -> "timed":
        self._started = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._started is not None:
            registry.observe(
                self._name, self._labels, time.monotonic() - self._started
            )
