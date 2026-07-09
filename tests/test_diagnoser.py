"""diagnoser 规则单元测试。"""

from datetime import datetime

from dba_ops_agent.diagnoser import Diagnoser, classify_wait_events
from dba_ops_agent.models import (
    MetricBundle,
    MetricSample,
    MetricStatus,
    Severity,
    WaitClass,
)


def _bundle(db: str, samples: list[MetricSample]) -> MetricBundle:
    return MetricBundle(database=db, task="test", samples=samples, collected_at=datetime.now())


def test_threshold_three_states():
    thresholds = {"connection_usage": {"warn": 70, "critical": 90}}
    diag = Diagnoser(thresholds)
    ok = diag.diagnose(_bundle("db", [MetricSample("connection_usage", 50, "%")]))[0]
    warn = diag.diagnose(_bundle("db", [MetricSample("connection_usage", 80, "%")]))[0]
    crit = diag.diagnose(_bundle("db", [MetricSample("connection_usage", 95, "%")]))[0]
    assert ok.severity is Severity.OK
    assert warn.severity is Severity.WARN
    assert crit.severity is Severity.CRITICAL


def test_higher_is_better_metric_threshold():
    thresholds = {"buffer_pool_hit_rate": {"warn": 95, "critical": 90}}
    diag = Diagnoser(thresholds)
    ok = diag.diagnose(_bundle("db", [MetricSample("buffer_pool_hit_rate", 97.14, "%")]))[0]
    warn = diag.diagnose(_bundle("db", [MetricSample("buffer_pool_hit_rate", 93, "%")]))[0]
    crit = diag.diagnose(_bundle("db", [MetricSample("buffer_pool_hit_rate", 85, "%")]))[0]
    assert ok.severity is Severity.OK
    assert warn.severity is Severity.WARN
    assert crit.severity is Severity.CRITICAL


def test_error_sample_produces_error_finding():
    diag = Diagnoser()
    sample = MetricSample("connection_usage", None, status=MetricStatus.ERROR, error="boom")
    f = diag.diagnose(_bundle("db", [sample]))[0]
    assert f.severity is Severity.ERROR
    assert "采集失败" in f.symptom


def test_lock_wait_root_cause():
    diag = Diagnoser({"lock_waits": {"warn": 1, "critical": 10}})
    sample = MetricSample(
        "lock_waits", 15, "count",
        detail={"blocked_sessions": [{"pid": 1}, {"pid": 2}]},
    )
    f = diag.diagnose(_bundle("db", [sample]))[0]
    assert f.severity is Severity.CRITICAL
    assert f.root_cause is not None
    assert "2" in f.root_cause
    assert any("kill" in s.lower() or "索引" in s for s in f.suggestion)


def test_connection_usage_pool_leak_root_cause():
    diag = Diagnoser({"connection_usage": {"warn": 70, "critical": 90}})
    sample = MetricSample(
        "connection_usage", 95, "%",
        detail={"current": 5, "max": 100},
    )
    f = diag.diagnose(_bundle("db", [sample]))[0]
    assert f.severity is Severity.CRITICAL
    assert f.root_cause is not None
    assert "连接池泄漏" in f.root_cause


def test_slow_queries_root_cause():
    diag = Diagnoser({"slow_queries": {"warn": 5, "critical": 20}})
    sample = MetricSample("slow_queries", 25, "count", detail={"slow_sessions": [{}] * 3})
    f = diag.diagnose(_bundle("db", [sample]))[0]
    assert f.severity is Severity.CRITICAL
    assert "3" in (f.root_cause or "")


def test_classify_wait_events():
    events = [
        {"event": "db file sequential read"},
        {"event": "enq: TX - row lock contention"},
        {"event": "SQL*Net message from client"},
    ]
    grouped = classify_wait_events(events)
    assert WaitClass.IO in grouped
    assert WaitClass.LOCK in grouped
    assert WaitClass.NETWORK in grouped
