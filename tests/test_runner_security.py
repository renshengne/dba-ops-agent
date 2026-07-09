"""runner 集成测试 + 安全边界 + LLM 降级。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from dba_ops_agent.config import (
    AppConfig,
    DatabaseConfig,
    LLMConfig,
    NotifierConfig,
    PatrolTemplate,
)
from dba_ops_agent.db.pool import ReadOnlyViolation
from dba_ops_agent.llm_core.core import LLMCore
from dba_ops_agent.models import (
    Finding,
    Severity,
)
from dba_ops_agent.runner import AgentRunner

from .conftest import MockConnection


def _make_config(write_account: bool = False) -> AppConfig:
    return AppConfig(
        databases={
            "test-mysql": DatabaseConfig(
                name="test-mysql",
                dialect="mysql",
                host="127.0.0.1",
                port=3306,
                user="ro",
                password="x",
                database=None,
                allow_write_account=write_account,
            ),
        },
        llm=LLMConfig(enabled=False),
        notifier=NotifierConfig(),
        patrol_templates={
            "default": PatrolTemplate(
                metrics=["connection_usage"],
                thresholds={"connection_usage": {"warn": 70, "critical": 90}},
                cron="0 */6 * * *",
            )
        },
        reports_dir="reports",
    )


def test_runner_event_flow():
    cfg = _make_config()
    runner = AgentRunner(cfg)

    fake_conn = MockConnection({
        "Threads_connected": [("Threads_connected", "95")],
        "max_connections": [("max_connections", "100")],
    })
    pool = runner.pools.register(cfg.databases["test-mysql"])

    with patch.object(pool, "_create_connection", return_value=fake_conn):
        events = list(runner.run("test-mysql", task="patrol"))

    stages = [e.stage for e in events]
    assert "plan" in stages
    assert "collect" in stages
    assert "diagnose" in stages
    assert "advise" in stages
    assert "done" in stages

    done_ev = [e for e in events if e.stage == "done"][0]
    assert done_ev.data["llm_available"] is False
    assert "规则结论" in done_ev.data["report_narrative"]


def test_read_only_account_rejected():
    cfg = _make_config()
    db_cfg = cfg.databases["test-mysql"]

    fake_conn = MockConnection({})
    with patch.object(fake_conn, "cursor") as mock_cursor_factory:
        class _Cur:
            def execute(self, *a, **k): pass
            def fetchall(self):
                return [
                    ("GRANT SELECT ON *.* TO 'ro'@'%'",),
                    ("GRANT INSERT, UPDATE ON *.* TO 'ro'@'%'",),
                ]
            def close(self): pass
        mock_cursor_factory.return_value = _Cur()
        from dba_ops_agent.db.pool import ConnectionPool
        p = ConnectionPool(db_cfg)
        with patch.object(p, "_create_connection", return_value=fake_conn):
            with pytest.raises(ReadOnlyViolation):
                p.check_read_only_permission()


def test_llm_fallback_to_rules():
    cfg = LLMConfig(enabled=False)
    core = LLMCore(cfg)
    assert core.is_available is False

    findings = [
        Finding(
            id="x-critical-0",
            metric="lock_waits",
            severity=Severity.CRITICAL,
            symptom="lock_waits 严重",
            evidence=[],
            root_cause="持锁",
            suggestion=["kill"],
        )
    ]
    report = core.explain(findings, "db", "test")
    assert report.llm_available is False
    assert "LLM 不可用" in report.narrative
    assert "规则结论" in report.narrative


def test_no_write_in_full_pipeline():
    cfg = _make_config()
    runner = AgentRunner(cfg)
    fake_conn = MockConnection({
        "Threads_connected": [("Threads_connected", "95")],
        "max_connections": [("max_connections", "100")],
    })
    pool = runner.pools.register(cfg.databases["test-mysql"])

    captured_sql: list[str] = []

    class _SpyCursor:
        def __init__(self):
            self.last = None

        def execute(self, sql, params=None):
            self.last = sql
            captured_sql.append(sql)

        def fetchall(self):
            up = (self.last or "").upper()
            if "THREADS_CONNECTED" in up:
                return [("Threads_connected", "95")]
            if "MAX_CONNECTIONS" in up:
                return [("max_connections", "100")]
            if "GRANTS" in up or "SESSION_PRIVS" in up:
                return []
            return []

        def close(self):
            pass

    with patch.object(fake_conn, "cursor", return_value=_SpyCursor()):
        with patch.object(pool, "_create_connection", return_value=fake_conn):
            list(runner.run("test-mysql", task="patrol"))

    write_keywords = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE")
    for sql in captured_sql:
        words = set(sql.upper().split())
        for kw in write_keywords:
            assert kw not in words, f"写语句泄露: {sql[:60]}"
