"""Agent 编排核心：plan→collect→diagnose→advise，产出 AgentEvent 流。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from . import events
from .collector import Collector
from .config import AppConfig, DatabaseConfig
from .db.pool import ConnectionPool, PoolRegistry
from .diagnoser import Diagnoser
from .dialect import get_dialect
from .llm_core import LLMCore
from .models import AgentEvent, Finding, MetricBundle, RecoveryPlan, Report
from .recovery_advisor import RecoveryAdvisor


class AgentRunner:
    """Agent 编排：把采集/诊断/LLM/恢复建议串成事件流。"""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.pools = PoolRegistry()
        self.llm = LLMCore(config.llm)

    def _ensure_pool(self, db_name: str) -> tuple[ConnectionPool, DatabaseConfig]:
        if db_name not in self.pools._pools:
            db_cfg = self.config.get_database(db_name)
            self.pools.register(db_cfg)
        return self.pools.get(db_name), self.config.get_database(db_name)

    def run(
        self,
        db_name: str,
        task: str,
        metrics: list[str] | None = None,
        collect_kwargs: dict[str, Any] | None = None,
    ) -> Iterator[AgentEvent]:
        yield events.plan(f"开始任务: {task}，目标库: {db_name}")

        try:
            pool, db_cfg = self._ensure_pool(db_name)
        except Exception as e:
            yield events.error(f"连接池初始化失败: {e}")
            return

        yield events.collect("开始采集指标")
        dialect = get_dialect(db_cfg.dialect)
        collector = Collector(dialect, pool)
        try:
            bundle = collector.run(db_name, task, metrics, collect_kwargs)
        except Exception as e:
            yield events.error(f"采集失败: {e}")
            return
        yield events.collect(
            f"采集完成，共 {len(bundle.samples)} 项指标",
            {"samples": [s.name for s in bundle.samples]},
        )

        yield events.diagnose("开始诊断")
        template = self.config.patrol_templates.get("default")
        thresholds = template.thresholds if template else None
        diagnoser = Diagnoser(thresholds)
        findings = diagnoser.diagnose(bundle)
        yield events.diagnose(
            f"诊断完成，发现 {len(findings)} 项",
            {"findings": [f.id for f in findings]},
        )

        yield events.advise("生成报告与恢复建议")
        report = self.llm.explain(findings, db_name, task)
        advisor = RecoveryAdvisor()
        plans = advisor.advise(findings, db_name)
        yield events.advise(
            f"恢复建议 {len(plans)} 条",
            {"plans": [p.action_type for p in plans]},
        )

        yield events.done(
            "任务完成",
            {
                "report_narrative": report.narrative,
                "llm_available": report.llm_available,
                "findings": [f.__dict__ for f in findings],
                "plans": [p.__dict__ for p in plans],
            },
        )

    def chat(self, db_name: str, question: str) -> str:
        findings = self.last_findings(db_name)
        return self.llm.chat(question, findings)

    def last_bundle(self, db_name: str) -> MetricBundle | None:
        return _MemoryStore.get_bundle(db_name)

    def last_findings(self, db_name: str) -> list[Finding] | None:
        return _MemoryStore.get_findings(db_name)

    def last_report(self, db_name: str) -> Report | None:
        return _MemoryStore.get_report(db_name)

    def last_plans(self, db_name: str) -> list[RecoveryPlan] | None:
        return _MemoryStore.get_plans(db_name)


class _MemoryStore:
    """会话上下文存储（进程内），供对话追问使用。"""

    _bundles: dict[str, MetricBundle] = {}
    _findings: dict[str, list[Finding]] = {}
    _reports: dict[str, Report] = {}
    _plans: dict[str, list[RecoveryPlan]] = {}

    @classmethod
    def save(cls, db: str, bundle: MetricBundle, findings: list[Finding], report: Report, plans: list[RecoveryPlan]) -> None:
        cls._bundles[db] = bundle
        cls._findings[db] = findings
        cls._reports[db] = report
        cls._plans[db] = plans

    @classmethod
    def get_bundle(cls, db: str) -> MetricBundle | None:
        return cls._bundles.get(db)

    @classmethod
    def get_findings(cls, db: str) -> list[Finding] | None:
        return cls._findings.get(db)

    @classmethod
    def get_report(cls, db: str) -> Report | None:
        return cls._reports.get(db)

    @classmethod
    def get_plans(cls, db: str) -> list[RecoveryPlan] | None:
        return cls._plans.get(db)


def save_session(db: str, bundle: MetricBundle, findings: list[Finding], report: Report, plans: list[RecoveryPlan]) -> None:
    _MemoryStore.save(db, bundle, findings, report, plans)
