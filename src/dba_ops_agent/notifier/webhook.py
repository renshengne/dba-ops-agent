"""webhook 推送（飞书/钉钉）。"""

from __future__ import annotations

import json
from typing import Any

import requests


class WebhookNotifier:
    def __init__(self, url: str, platform: str = "feishu") -> None:
        self.url = url
        self.platform = platform

    def send(self, alert: dict[str, Any]) -> bool:
        if not self.url:
            return False
        try:
            payload = self._build_payload(alert)
            resp = requests.post(
                self.url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _build_payload(self, alert: dict[str, Any]) -> dict[str, Any]:
        title = f"[DBA告警] {alert.get('instance','')} - {alert.get('item','')}"
        content = (
            f"严重度: {alert.get('severity','')}\n"
            f"建议: {alert.get('suggestion','')}"
        )
        if self.platform == "feishu":
            return {
                "msg_type": "text",
                "content": {"text": f"{title}\n{content}"},
            }
        if self.platform == "dingtalk":
            return {
                "msgtype": "text",
                "text": {"content": f"{title}\n{content}"},
            }
        return {"title": title, "content": content}
