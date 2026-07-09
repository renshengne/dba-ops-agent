"""会话上下文记忆（最近采集/诊断结果，供对话追问）。"""

from __future__ import annotations

from .models import Finding, MetricBundle, RecoveryPlan, Report


class Memory:
    """按数据库实例保存最近一次诊断上下文。"""

    def __init__(self) -> None:
        self._bundles: dict[str, MetricBundle] = {}
        self._findings: dict[str, list[Finding]] = {}
        self._reports: dict[str, Report] = {}
        self._plans: dict[str, list[RecoveryPlan]] = {}

    def save(
        self,
        db: str,
        bundle: MetricBundle,
        findings: list[Finding],
        report: Report,
        plans: list[RecoveryPlan],
    ) -> None:
        self._bundles[db] = bundle
        self._findings[db] = findings
        self._reports[db] = report
        self._plans[db] = plans

    def get_bundle(self, db: str) -> MetricBundle | None:
        return self._bundles.get(db)

    def get_findings(self, db: str) -> list[Finding] | None:
        return self._findings.get(db)

    def get_report(self, db: str) -> Report | None:
        return self._reports.get(db)

    def get_plans(self, db: str) -> list[RecoveryPlan] | None:
        return self._plans.get(db)
