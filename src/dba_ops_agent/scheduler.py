"""定时巡检调度（APScheduler + cron）。"""

from __future__ import annotations

from .config import AppConfig
from .runner import AgentRunner


def start_scheduler(config: AppConfig) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BlockingScheduler()
    runner = AgentRunner(config)

    for tname, template in config.patrol_templates.items():
        for db_name in config.databases:
            def _job(db=db_name, tn=tname) -> None:
                _run_patrol(runner, db, tn)

            trigger = CronTrigger.from_crontab(template.cron)
            scheduler.add_job(_job, trigger, id=f"patrol-{db_name}-{tname}")

    scheduler.start()


def _run_patrol(runner: AgentRunner, db: str, template_name: str) -> None:
    template = runner.config.patrol_templates.get(template_name)
    metrics = template.metrics if template else None
    for ev in runner.run(db, task=f"patrol:{template_name}", metrics=metrics):
        if ev.stage == "done":
            from .notifier import Notifier
            notifier = Notifier(runner.config.notifier)
            findings_data = (ev.data or {}).get("findings", [])
            from .models import Finding, Severity
            for f in findings_data:
                finding = Finding(
                    id=f.get("id", ""),
                    metric=f.get("metric", ""),
                    severity=Severity(f.get("severity", Severity.OK.value)),
                    symptom=f.get("symptom", ""),
                    evidence=[],
                    root_cause=f.get("root_cause"),
                    suggestion=[],
                )
                notifier.send_alert(db, finding)
