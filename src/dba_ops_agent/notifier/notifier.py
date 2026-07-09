"""告警通知顶层封装。"""

from __future__ import annotations

from ..config import NotifierConfig
from ..models import Finding, Severity
from .email import EmailNotifier
from .webhook import WebhookNotifier


class Notifier:
    def __init__(self, cfg: NotifierConfig) -> None:
        self.webhook = WebhookNotifier(cfg.webhook.url, cfg.webhook.type)
        self.email = EmailNotifier(cfg.email)

    def send_alert(self, instance: str, finding: Finding) -> None:
        if finding.severity is not Severity.CRITICAL:
            return
        alert = {
            "instance": instance,
            "item": finding.metric,
            "severity": finding.severity.value,
            "suggestion": "; ".join(finding.suggestion) if finding.suggestion else finding.symptom,
        }
        try:
            self.webhook.send(alert)
        except Exception:
            pass
        try:
            self.email.send(
                subject=f"[DBA告警] {instance} - {finding.metric}",
                body=f"{finding.symptom}\n根因: {finding.root_cause}\n建议: {alert['suggestion']}",
            )
        except Exception:
            pass
