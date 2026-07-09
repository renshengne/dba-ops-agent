"""recovery_advisor 单元测试：生成脚本无执行调用、含回滚预案。"""

from dba_ops_agent.models import Finding, RecoveryPlan, Severity
from dba_ops_agent.recovery_advisor import RecoveryAdvisor

_WRITE_INDICATORS = (
    ".execute(", ".commit(", "cursor.execute", "run_sql", "apply(",
)


def _finding(metric: str, severity: Severity, detail: dict | None = None) -> Finding:
    return Finding(
        id=f"{metric}-{severity.value}-0",
        metric=metric,
        severity=severity,
        symptom=f"{metric} {severity.value}",
        evidence=[],
        root_cause="root",
        suggestion=[],
        raw={"detail": detail},
    )


def test_no_write_execution_in_plans():
    findings = [
        _finding("lock_waits", Severity.CRITICAL, {"blocked_sessions": [1, 2]}),
        _finding("connection_usage", Severity.CRITICAL),
        _finding("slow_queries", Severity.CRITICAL),
        _finding("replication_lag", Severity.CRITICAL),
        _finding("disk_usage", Severity.CRITICAL),
    ]
    plans = RecoveryAdvisor().advise(findings, "db")
    assert len(plans) == 5
    for p in plans:
        assert isinstance(p, RecoveryPlan)
        assert p.requires_human is True
        assert p.rollback != ""
        assert p.impact != ""
        blob = " ".join(s.script for s in p.steps)
        for indicator in _WRITE_INDICATORS:
            assert indicator not in blob, f"plan {p.action_type} 含执行调用: {indicator}"


def test_ok_findings_no_plan():
    findings = [_finding("connection_usage", Severity.OK)]
    plans = RecoveryAdvisor().advise(findings, "db")
    assert plans == []


def test_lock_waits_plan_has_kill_and_human_note():
    f = _finding("lock_waits", Severity.CRITICAL, {"blocked_sessions": [1, 2, 3]})
    plans = RecoveryAdvisor().advise([f], "db")
    assert len(plans) == 1
    p = plans[0]
    assert p.action_type == "kill_blocked_session"
    scripts = " ".join(s.script for s in p.steps)
    assert "KILL" in scripts.upper()
    assert any("需 DBA 人工执行" in s.note for s in p.steps)


def test_replication_lag_plan_is_failover():
    f = _finding("replication_lag", Severity.CRITICAL)
    plans = RecoveryAdvisor().advise([f], "db")
    assert plans[0].action_type == "failover_check"
    titles = [s.title for s in plans[0].steps]
    assert any("切换前检查" in t for t in titles)
    assert any("切换后验证" in t for t in titles)
