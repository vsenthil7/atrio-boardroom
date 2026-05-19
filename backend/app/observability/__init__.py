"""Prometheus metrics for ATRIO.

We intentionally do not pull in `prometheus-client` as a hard dep — the
backend has been kept lean. Instead we maintain a tiny in-memory metrics
registry and expose it as text/plain in the Prometheus exposition format
at /api/v1/metrics. This is a hackathon-grade implementation; production
swaps in prometheus-client.

Metric types supported:
  - Counter  (monotonically increasing)
  - Gauge    (arbitrary up/down)
  - Histogram (with explicit buckets, exposes _count, _sum, _bucket)

All metrics are tenant-aware: pass `labels=` to add labels.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable


_DEFAULT_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5,
    1.0, 2.5, 5.0, 10.0, 30.0, 60.0,
)


def _labels_key(labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted(labels.items()))


def _format_labels(labels_key: tuple[tuple[str, str], ...]) -> str:
    if not labels_key:
        return ""
    inner = ",".join(f'{k}="{_esc(v)}"' for k, v in labels_key)
    return "{" + inner + "}"


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


@dataclass
class Counter:
    name: str
    help: str
    _values: dict[tuple, float] = field(default_factory=lambda: defaultdict(float))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        if amount < 0:
            raise ValueError("counter cannot decrease")
        with self._lock:
            self._values[_labels_key(labels)] += amount

    def render(self) -> Iterable[str]:
        yield f"# HELP {self.name} {self.help}"
        yield f"# TYPE {self.name} counter"
        with self._lock:
            for k, v in self._values.items():
                yield f"{self.name}{_format_labels(k)} {v}"


@dataclass
class Gauge:
    name: str
    help: str
    _values: dict[tuple, float] = field(default_factory=lambda: defaultdict(float))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._values[_labels_key(labels)] = value

    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._values[_labels_key(labels)] += amount

    def dec(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._values[_labels_key(labels)] -= amount

    def render(self) -> Iterable[str]:
        yield f"# HELP {self.name} {self.help}"
        yield f"# TYPE {self.name} gauge"
        with self._lock:
            for k, v in self._values.items():
                yield f"{self.name}{_format_labels(k)} {v}"


@dataclass
class Histogram:
    name: str
    help: str
    buckets: tuple[float, ...] = _DEFAULT_BUCKETS
    _counts: dict[tuple, list[int]] = field(default_factory=dict)
    _sums: dict[tuple, float] = field(default_factory=lambda: defaultdict(float))
    _totals: dict[tuple, int] = field(default_factory=lambda: defaultdict(int))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = _labels_key(labels)
        with self._lock:
            if key not in self._counts:
                self._counts[key] = [0] * (len(self.buckets) + 1)
            for i, b in enumerate(self.buckets):
                if value <= b:
                    self._counts[key][i] += 1
            self._counts[key][-1] += 1  # +Inf bucket
            self._sums[key] += value
            self._totals[key] += 1

    def render(self) -> Iterable[str]:
        yield f"# HELP {self.name} {self.help}"
        yield f"# TYPE {self.name} histogram"
        with self._lock:
            for k in self._counts:
                base = _format_labels(k)
                # bucket lines
                for i, b in enumerate(self.buckets):
                    inner_labels = list(k) + [("le", f"{b}")]
                    yield (
                        f"{self.name}_bucket"
                        f"{_format_labels(tuple(sorted(inner_labels)))} "
                        f"{self._counts[k][i]}"
                    )
                inner_labels = list(k) + [("le", "+Inf")]
                yield (
                    f"{self.name}_bucket"
                    f"{_format_labels(tuple(sorted(inner_labels)))} "
                    f"{self._counts[k][-1]}"
                )
                yield f"{self.name}_sum{base} {self._sums[k]}"
                yield f"{self.name}_count{base} {self._totals[k]}"


@dataclass
class Registry:
    counters: dict[str, Counter] = field(default_factory=dict)
    gauges: dict[str, Gauge] = field(default_factory=dict)
    histograms: dict[str, Histogram] = field(default_factory=dict)

    def counter(self, name: str, help: str) -> Counter:
        if name not in self.counters:
            self.counters[name] = Counter(name=name, help=help)
        return self.counters[name]

    def gauge(self, name: str, help: str) -> Gauge:
        if name not in self.gauges:
            self.gauges[name] = Gauge(name=name, help=help)
        return self.gauges[name]

    def histogram(
        self, name: str, help: str, buckets: tuple[float, ...] = _DEFAULT_BUCKETS
    ) -> Histogram:
        if name not in self.histograms:
            self.histograms[name] = Histogram(name=name, help=help, buckets=buckets)
        return self.histograms[name]

    def render(self) -> str:
        lines: list[str] = []
        for c in self.counters.values():
            lines.extend(c.render())
        for g in self.gauges.values():
            lines.extend(g.render())
        for h in self.histograms.values():
            lines.extend(h.render())
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        """Test helper — wipe everything."""
        self.counters.clear()
        self.gauges.clear()
        self.histograms.clear()


# Module-level singleton
_REGISTRY = Registry()


def get_registry() -> Registry:
    return _REGISTRY


def reset_registry() -> None:
    _REGISTRY.reset()


# ----------------------------------------------------- ATRIO metric definitions


# HTTP
http_requests_total = _REGISTRY.counter(
    "http_requests_total", "Total HTTP requests handled"
)
http_request_duration_seconds = _REGISTRY.histogram(
    "http_request_duration_seconds", "HTTP request latency in seconds"
)

# Sessions
sessions_active = _REGISTRY.gauge("atrio_sessions_active", "Currently active sessions")
sessions_opened_total = _REGISTRY.counter(
    "atrio_sessions_opened_total", "Sessions created since boot"
)
sessions_closed_total = _REGISTRY.counter(
    "atrio_sessions_closed_total", "Sessions closed since boot"
)

# Inference
inference_invocations_total = _REGISTRY.counter(
    "atrio_inference_invocations_total", "AI Gateway invocations"
)
inference_fallbacks_total = _REGISTRY.counter(
    "atrio_inference_fallbacks_total", "Times the primary failed and fallback ran"
)
inference_failures_total = _REGISTRY.counter(
    "atrio_inference_failures_total", "Times all providers in the chain failed"
)
inference_latency_seconds = _REGISTRY.histogram(
    "atrio_inference_latency_seconds", "Inference call latency"
)

# Treasury
treasury_proposed_total = _REGISTRY.counter(
    "atrio_treasury_proposed_total", "Treasury proposals created"
)
treasury_executed_total = _REGISTRY.counter(
    "atrio_treasury_executed_total", "Treasury proposals that reached executed state"
)
mandate_violations_total = _REGISTRY.counter(
    "atrio_mandate_violations_total",
    "Treasury proposals rejected by mandate (labelled by reason)",
)
two_party_blocks_total = _REGISTRY.counter(
    "atrio_two_party_blocks_total",
    "Times a single user tried to second-authorise their own proposal",
)
