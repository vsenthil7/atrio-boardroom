"""Unit tests for the in-memory Prometheus registry."""
from __future__ import annotations

import pytest

from app.observability import (
    Counter,
    Gauge,
    Histogram,
    Registry,
    get_registry,
    reset_registry,
)


# ----------------------------------------------------- counter


def test_counter_increments():
    c = Counter(name="t", help="test")
    c.inc()
    c.inc(2)
    out = "\n".join(c.render())
    assert "t 3" in out


def test_counter_with_labels():
    c = Counter(name="hits", help="hits")
    c.inc(labels={"path": "/a", "method": "GET"})
    c.inc(labels={"path": "/a", "method": "GET"})
    c.inc(labels={"path": "/b", "method": "POST"})
    out = "\n".join(c.render())
    assert 'hits{method="GET",path="/a"} 2' in out
    assert 'hits{method="POST",path="/b"} 1' in out


def test_counter_rejects_negative():
    c = Counter(name="x", help="x")
    with pytest.raises(ValueError):
        c.inc(-1)


# ----------------------------------------------------- gauge


def test_gauge_set_inc_dec():
    g = Gauge(name="g", help="g")
    g.set(5)
    g.inc()
    g.dec(2)
    out = "\n".join(g.render())
    assert "g 4" in out


def test_gauge_with_labels():
    g = Gauge(name="active", help="x")
    g.set(3, labels={"tenant": "a"})
    g.set(7, labels={"tenant": "b"})
    out = "\n".join(g.render())
    assert 'active{tenant="a"} 3' in out
    assert 'active{tenant="b"} 7' in out


# ----------------------------------------------------- histogram


def test_histogram_buckets():
    h = Histogram(name="lat", help="x", buckets=(0.1, 0.5, 1.0))
    h.observe(0.05)
    h.observe(0.3)
    h.observe(2.0)
    out = "\n".join(h.render())
    # 0.05 in 0.1, 0.5, 1.0, +Inf
    # 0.3  in 0.5, 1.0, +Inf
    # 2.0  only in +Inf
    assert 'lat_bucket{le="0.1"} 1' in out
    assert 'lat_bucket{le="0.5"} 2' in out
    assert 'lat_bucket{le="1.0"} 2' in out
    assert 'lat_bucket{le="+Inf"} 3' in out
    assert "lat_count 3" in out
    assert "lat_sum 2.35" in out


def test_histogram_labels_separate_streams():
    h = Histogram(name="lat", help="x", buckets=(1.0,))
    h.observe(0.5, labels={"agent_id": "cfo"})
    h.observe(0.5, labels={"agent_id": "cfo"})
    h.observe(0.5, labels={"agent_id": "cto"})
    out = "\n".join(h.render())
    assert 'lat_count{agent_id="cfo"} 2' in out
    assert 'lat_count{agent_id="cto"} 1' in out


# ----------------------------------------------------- registry


def test_registry_returns_existing_instances():
    r = Registry()
    c1 = r.counter("c", "help")
    c2 = r.counter("c", "help2")
    assert c1 is c2


def test_registry_render_includes_all_metric_types():
    r = Registry()
    r.counter("c", "help1").inc()
    r.gauge("g", "help2").set(5)
    r.histogram("h", "help3", buckets=(1.0,)).observe(0.5)
    body = r.render()
    assert "TYPE c counter" in body
    assert "TYPE g gauge" in body
    assert "TYPE h histogram" in body


def test_reset_registry_clears_atrio_metrics():
    g = get_registry().gauge("a", "help")
    g.set(99)
    reset_registry()
    # After reset, fetching the same gauge gives a fresh one with no value
    g2 = get_registry().gauge("a", "help")
    body = "\n".join(g2.render())
    # The metric line should be absent (no values recorded)
    assert "a 99" not in body


def test_label_escaping():
    c = Counter(name="x", help="x")
    c.inc(labels={"v": 'has "quotes" and \\ backslashes'})
    out = "\n".join(c.render())
    assert "quotes" in out  # didn't crash
    # The escaped form is present
    assert '\\"' in out
