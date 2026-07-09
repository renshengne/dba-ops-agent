"""核心数据模型：采集样本、指标包、诊断发现、报告、恢复预案、事件。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Severity(str, Enum):
    OK = "正常"
    WARN = "警告"
    CRITICAL = "严重"
    ERROR = "error"


class MetricStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


class WaitClass(str, Enum):
    CPU = "CPU"
    IO = "IO"
    LOCK = "锁"
    NETWORK = "网络"
    OTHER = "其他"


@dataclass
class MetricSample:
    name: str
    value: Any
    unit: str = ""
    threshold_ref: dict[str, float] | None = None
    collected_at: datetime = field(default_factory=datetime.now)
    status: MetricStatus = MetricStatus.OK
    error: str | None = None
    detail: dict[str, Any] | None = None

    @property
    def is_error(self) -> bool:
        return self.status is MetricStatus.ERROR


@dataclass
class MetricBundle:
    database: str
    task: str
    samples: list[MetricSample] = field(default_factory=list)
    collected_at: datetime = field(default_factory=datetime.now)

    def get(self, name: str) -> MetricSample | None:
        for s in self.samples:
            if s.name == name:
                return s
        return None


@dataclass
class Finding:
    id: str
    metric: str
    severity: Severity
    symptom: str
    evidence: list[str]
    root_cause: str | None = None
    suggestion: list[str] = field(default_factory=list)
    raw: dict[str, Any] | None = None


@dataclass
class Report:
    database: str
    task: str
    findings: list[Finding]
    narrative: str = ""
    llm_available: bool = True
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class RecoveryStep:
    title: str
    script: str
    note: str = ""


@dataclass
class RecoveryPlan:
    finding_id: str
    action_type: str
    steps: list[RecoveryStep] = field(default_factory=list)
    impact: str = ""
    rollback: str = ""
    requires_human: bool = True
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class AgentEvent:
    stage: str
    status: str
    message: str = ""
    data: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "message": self.message,
            "data": self.data or {},
            "timestamp": self.timestamp.isoformat(),
        }
