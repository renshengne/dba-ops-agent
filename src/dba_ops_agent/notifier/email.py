"""SMTP 邮件告警。"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from ..config import EmailConfig


class EmailNotifier:
    def __init__(self, cfg: EmailConfig) -> None:
        self.cfg = cfg

    def send(self, subject: str, body: str) -> bool:
        if not self.cfg.enabled or not self.cfg.recipients:
            return False
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self.cfg.sender
            msg["To"] = ",".join(self.cfg.recipients)
            with smtplib.SMTP_SSL(self.cfg.smtp_host, self.cfg.smtp_port, timeout=10) as smtp:
                smtp.login(self.cfg.sender, self.cfg.password)
                smtp.sendmail(self.cfg.sender, self.cfg.recipients, msg.as_string())
            return True
        except Exception:
            return False
