from __future__ import annotations

from app.observability import registry, timed


def test_registry_counters_gauges_and_prometheus_render() -> None:
    registry.inc("hotspot_test_total", {"platform": "weibo"})
    registry.inc("hotspot_test_total", {"platform": "weibo"})
    registry.inc("hotspot_test_total", {"platform": "douyin"})
    registry.set_gauge("hotspot_test_pending", None, 3)

    text = registry.render_prometheus()

    assert 'hotspot_test_total{platform="weibo"} 2' in text
    assert 'hotspot_test_total{platform="douyin"} 1' in text
    assert "hotspot_test_pending 3" in text


def test_timed_context_observes_latency() -> None:
    with timed("hotspot_test_latency", {"stage": "x"}):
        pass

    snapshot = registry.snapshot()
    latency = snapshot["latencies"]['hotspot_test_latency{stage="x"}']
    assert latency["count"] == 1
    assert latency["total"] >= 0

    text = registry.render_prometheus()
    assert 'hotspot_test_latency{stage="x"}_count 1' in text
    assert 'hotspot_test_latency{stage="x"}_sum ' in text


def test_snapshot_is_deterministic_dict() -> None:
    snapshot = registry.snapshot()
    assert isinstance(snapshot["counters"], dict)
    assert isinstance(snapshot["gauges"], dict)
    assert isinstance(snapshot["latencies"], dict)
