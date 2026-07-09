"""配置加载：数据库连接、LLM、告警、巡检模板。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


@dataclass
class DatabaseConfig:
    name: str
    dialect: str
    host: str
    port: int
    user: str
    password: str
    database: str | None = None
    service_name: str | None = None
    allow_write_account: bool = False


@dataclass
class LLMConfig:
    enabled: bool = True
    base_url: str = ""
    api_key: str = ""
    model: str = "gpt-4o-mini"
    timeout: int = 30


@dataclass
class WebhookConfig:
    type: str = "feishu"
    url: str = ""


@dataclass
class EmailConfig:
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 465
    sender: str = ""
    password: str = ""
    recipients: list[str] = field(default_factory=list)


@dataclass
class NotifierConfig:
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    email: EmailConfig = field(default_factory=EmailConfig)


@dataclass
class PatrolTemplate:
    metrics: list[str]
    thresholds: dict[str, dict[str, float]]
    cron: str = "0 */6 * * *"


@dataclass
class AppConfig:
    databases: dict[str, DatabaseConfig]
    llm: LLMConfig
    notifier: NotifierConfig
    patrol_templates: dict[str, PatrolTemplate]
    reports_dir: str = "reports"

    def get_database(self, name: str) -> DatabaseConfig:
        if name not in self.databases:
            raise KeyError(f"database '{name}' not configured")
        return self.databases[name]


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), m.group(0)), value
        )
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    raw = _expand_env(raw)

    databases: dict[str, DatabaseConfig] = {}
    for name, cfg in (raw.get("databases") or {}).items():
        databases[name] = DatabaseConfig(
            name=name,
            dialect=cfg["dialect"],
            host=cfg["host"],
            port=int(cfg["port"]),
            user=cfg["user"],
            password=cfg.get("password", ""),
            database=cfg.get("database"),
            service_name=cfg.get("service_name"),
            allow_write_account=bool(cfg.get("allow_write_account", False)),
        )

    llm_raw = raw.get("llm") or {}
    llm = LLMConfig(
        enabled=bool(llm_raw.get("enabled", True)),
        base_url=llm_raw.get("base_url", ""),
        api_key=llm_raw.get("api_key", ""),
        model=llm_raw.get("model", "gpt-4o-mini"),
        timeout=int(llm_raw.get("timeout", 30)),
    )

    notifier_raw = raw.get("notifier") or {}
    webhook_raw = notifier_raw.get("webhook") or {}
    email_raw = notifier_raw.get("email") or {}
    notifier = NotifierConfig(
        webhook=WebhookConfig(
            type=webhook_raw.get("type", "feishu"),
            url=webhook_raw.get("url", ""),
        ),
        email=EmailConfig(
            enabled=bool(email_raw.get("enabled", False)),
            smtp_host=email_raw.get("smtp_host", ""),
            smtp_port=int(email_raw.get("smtp_port", 465)),
            sender=email_raw.get("sender", ""),
            password=email_raw.get("password", ""),
            recipients=list(email_raw.get("recipients") or []),
        ),
    )

    patrol_raw = raw.get("patrol") or {}
    templates_raw = patrol_raw.get("templates") or {}
    templates: dict[str, PatrolTemplate] = {}
    for tname, tcfg in templates_raw.items():
        templates[tname] = PatrolTemplate(
            metrics=list(tcfg.get("metrics") or []),
            thresholds=tcfg.get("thresholds") or {},
            cron=tcfg.get("cron", "0 */6 * * *"),
        )

    return AppConfig(
        databases=databases,
        llm=llm,
        notifier=notifier,
        patrol_templates=templates,
        reports_dir=raw.get("reports_dir", "reports"),
    )
