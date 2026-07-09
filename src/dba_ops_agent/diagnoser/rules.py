"""规则诊断引擎。"""

from __future__ import annotations

from typing import Any

from ..models import (
    Finding,
    MetricBundle,
    MetricSample,
    MetricStatus,
    Severity,
    WaitClass,
)

_WAIT_CLASS_MAP = {
    "db file sequential read": WaitClass.IO,
    "db file scattered read": WaitClass.IO,
    "log file sync": WaitClass.IO,
    "read by other session": WaitClass.IO,
    "enqueue": WaitClass.LOCK,
    "enq": WaitClass.LOCK,
    "lock": WaitClass.LOCK,
    "row lock": WaitClass.LOCK,
    "sql*net": WaitClass.NETWORK,
    "cpu": WaitClass.CPU,
    "resmgr:cpu quantum": WaitClass.CPU,
}

_HIGHER_IS_BETTER = {"buffer_pool_hit_rate"}


def _classify_wait(event: str) -> WaitClass:
    key = (event or "").lower()
    for needle, cls in _WAIT_CLASS_MAP.items():
        if needle in key:
            return cls
    return WaitClass.OTHER


class Diagnoser:
    """阈值比对 + 根因推断 + 等待事件分类。"""

    def __init__(self, thresholds: dict[str, dict[str, float]] | None = None) -> None:
        self.thresholds = thresholds or {}

    def diagnose(self, bundle: MetricBundle) -> list[Finding]:
        findings: list[Finding] = []
        for idx, sample in enumerate(bundle.samples):
            f = self._diagnose_one(sample, idx)
            findings.append(f)
        return findings

    def _diagnose_one(self, sample: MetricSample, idx: int) -> Finding:
        if sample.status is MetricStatus.ERROR:
            return Finding(
                id=f"{sample.name}-{Severity.ERROR.value}-{idx}",
                metric=sample.name,
                severity=Severity.ERROR,
                symptom=f"指标 {sample.name} 采集失败",
                evidence=[f"错误: {sample.error}"],
                raw={"error": sample.error},
            )

        thresholds = self.thresholds.get(sample.name, {})
        severity = self._compare_threshold(sample, thresholds)
        root_cause, suggestion = self._infer_root_cause(sample, severity)

        evidence = self._build_evidence(sample)
        symptom = self._build_symptom(sample, severity)

        return Finding(
            id=f"{sample.name}-{severity.value}-{idx}",
            metric=sample.name,
            severity=severity,
            symptom=symptom,
            evidence=evidence,
            root_cause=root_cause,
            suggestion=suggestion,
            raw={"value": sample.value, "detail": sample.detail},
        )

    @staticmethod
    def _compare_threshold(sample: MetricSample, thresholds: dict[str, float]) -> Severity:
        if not thresholds:
            return Severity.OK
        warn = thresholds.get("warn")
        crit = thresholds.get("critical")
        try:
            v = float(sample.value)
        except (TypeError, ValueError):
            return Severity.OK
        if sample.name in _HIGHER_IS_BETTER:
            if crit is not None and v <= crit:
                return Severity.CRITICAL
            if warn is not None and v < warn:
                return Severity.WARN
            return Severity.OK
        if crit is not None and v >= crit:
            return Severity.CRITICAL
        if warn is not None and v >= warn:
            return Severity.WARN
        return Severity.OK

    def _infer_root_cause(self, sample: MetricSample, severity: Severity) -> tuple[str | None, list[str]]:
        if severity is Severity.OK or severity is Severity.ERROR:
            return None, []

        detail = sample.detail or {}

        if sample.name == "lock_waits":
            blocked = detail.get("blocked_sessions") or detail.get("blocked_locks") or []
            count = len(blocked) if isinstance(blocked, list) else blocked
            return (
                f"存在 {count} 个锁等待会话，疑似阻塞源会话持锁未释放",
                ["评估 kill 阻塞源会话（见恢复建议）", "检查应用是否缺失索引导致大范围锁"],
            )

        if sample.name == "connection_usage":
            cur = detail.get("current", 0)
            return self._infer_connection_root_cause(sample, cur)

        if sample.name == "slow_queries":
            sessions = detail.get("slow_sessions") or []
            return (
                f"存在 {len(sessions)} 条慢 SQL",
                ["对慢 SQL 做执行计划分析", "检查索引覆盖与统计信息", "评估 SQL 改写"],
            )

        if sample.name == "replication_lag":
            return (
                f"复制延迟 {sample.value}s",
                ["检查网络与主库负载", "评估主备切换（见恢复建议）"],
            )

        if sample.name == "disk_usage":
            return (
                f"磁盘使用 {sample.value}MB",
                ["清理历史数据或扩容", "评估业务数据保留期"],
            )

        return None, []

    @staticmethod
    def _infer_connection_root_cause(sample: MetricSample, current: int) -> tuple[str, list[str]]:
        detail = sample.detail or {}
        max_conn = detail.get("max", 0)
        active_ratio = current / max_conn if max_conn else 0
        if active_ratio < 0.5:
            return (
                "连接数高但活跃会话少，疑似应用连接池泄漏",
                ["检查应用连接池配置与归还逻辑", "评估回收空闲连接"],
            )
        return (
            "连接数与活跃会话双高，疑似真实并发过高或慢SQL堆积",
            ["检查慢 SQL 是否拖住会话", "评估扩容 max_connections（见恢复建议）"],
        )

    @staticmethod
    def _build_evidence(sample: MetricSample) -> list[str]:
        ev = [f"指标={sample.name}, 值={sample.value}{sample.unit}"]
        detail = sample.detail or {}
        if sample.name == "top_wait_events":
            events = detail.get("wait_events") or []
            classified: dict[WaitClass, list[str]] = {}
            for e in events:
                cls = _classify_wait(e.get("event", ""))
                classified.setdefault(cls, []).append(e.get("event", ""))
            for cls, evs in classified.items():
                ev.append(f"{cls.value}: {', '.join(evs)}")
        elif sample.name == "lock_waits":
            blocked = detail.get("blocked_sessions") or detail.get("blocked_locks") or []
            ev.append(f"阻塞对象数={len(blocked) if isinstance(blocked, list) else blocked}")
        elif sample.name == "slow_queries":
            sessions = detail.get("slow_sessions") or []
            ev.append(f"慢会话数={len(sessions)}")
        return ev

    @staticmethod
    def _build_symptom(sample: MetricSample, severity: Severity) -> str:
        if severity is Severity.OK:
            return f"{sample.name} 正常（{sample.value}{sample.unit}）"
        return f"{sample.name} {severity.value}（{sample.value}{sample.unit}）"


def classify_wait_events(events: list[dict[str, Any]]) -> dict[WaitClass, list[str]]:
    grouped: dict[WaitClass, list[str]] = {}
    for e in events:
        cls = _classify_wait(e.get("event", ""))
        grouped.setdefault(cls, []).append(e.get("event", ""))
    return grouped
