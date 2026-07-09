"""CLI 主入口：patrol/diagnose/perf/recovery/web/schedule。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import click

from ..config import load_config
from ..runner import AgentRunner

_DEFAULT_CONFIG = "config/config.yaml"


def _load_runner(config: str) -> AgentRunner:
    cfg = load_config(config)
    return AgentRunner(cfg)


def _save_report(runner: AgentRunner, db: str, task: str, events_list: list) -> Path:
    reports_dir = Path(runner.config.reports_dir)
    db_dir = reports_dir / db
    db_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = db_dir / f"{task}_{date}.md"
    json_path = db_dir / f"{task}_{date}.json"

    final_data = {}
    for ev in events_list:
        if ev.stage == "done" and ev.data:
            final_data = ev.data

    md_lines = [f"# {db} - {task} 报告", ""]
    md_lines.append(f"生成时间: {datetime.now().isoformat()}")
    md_lines.append(f"LLM 可用: {final_data.get('llm_available')}")
    md_lines.append("")
    md_lines.append("## 报告")
    md_lines.append(final_data.get("report_narrative", "(无)"))
    md_lines.append("")
    md_lines.append("## 发现")
    for f in final_data.get("findings", []):
        md_lines.append(f"- {f.get('metric')} [{f.get('severity')}]: {f.get('symptom')}")
    md_lines.append("")
    md_lines.append("## 恢复建议")
    for p in final_data.get("plans", []):
        md_lines.append(f"- {p.get('action_type')} (需人工执行: {p.get('requires_human')})")
        md_lines.append(f"  - 影响: {p.get('impact')}")
        md_lines.append(f"  - 回滚: {p.get('rollback')}")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    json_path.write_text(
        json.dumps(final_data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return md_path


@click.group()
@click.option("--config", default=_DEFAULT_CONFIG, help="配置文件路径")
@click.pass_context
def cli(ctx: click.Context, config: str) -> None:
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@cli.command()
@click.option("--db", required=True, help="数据库实例名")
@click.pass_context
def patrol(ctx: click.Context, db: str) -> None:
    """智能巡检。"""
    runner = _load_runner(ctx.obj["config_path"])
    events_list = list(runner.run(db, task="patrol"))
    for ev in events_list:
        click.echo(f"[{ev.stage}] {ev.message}")
    md_path = _save_report(runner, db, "patrol", events_list)
    click.echo(f"\n报告已保存: {md_path}")


@cli.command()
@click.option("--db", required=True)
@click.option("--topic", required=True, help="诊断主题，如 '大量锁等待'")
@click.pass_context
def diagnose(ctx: click.Context, db: str, topic: str) -> None:
    """异常诊断。"""
    runner = _load_runner(ctx.obj["config_path"])
    events_list = list(runner.run(db, task=f"diagnose:{topic}"))
    for ev in events_list:
        click.echo(f"[{ev.stage}] {ev.message}")
    _save_report(runner, db, f"diagnose_{topic}", events_list)


@cli.command()
@click.option("--db", required=True)
@click.option("--sql-id", default=None, help="指定慢SQL ID（可选）")
@click.pass_context
def perf(ctx: click.Context, db: str, sql_id: str | None) -> None:
    """性能诊断。"""
    runner = _load_runner(ctx.obj["config_path"])
    metrics = ["slow_queries", "top_sql", "connection_usage"]
    if runner.config.get_database(db).dialect == "oracle":
        metrics = ["slow_queries", "top_sql", "top_wait_events", "connection_usage"]
    events_list = list(runner.run(db, task="perf", metrics=metrics))
    for ev in events_list:
        click.echo(f"[{ev.stage}] {ev.message}")
    _save_report(runner, db, "perf", events_list)


@cli.command()
@click.option("--db", required=True)
@click.option("--finding-id", required=True, help="诊断发现 ID")
@click.pass_context
def recovery(ctx: click.Context, db: str, finding_id: str) -> None:
    """快速恢复建议。"""
    runner = _load_runner(ctx.obj["config_path"])
    plans = runner.last_plans(db) or []
    matched = [p for p in plans if p.finding_id == finding_id]
    if not matched:
        click.echo(f"未找到 finding_id={finding_id} 的恢复建议，可用:")
        for p in plans:
            click.echo(f"  - {p.finding_id} -> {p.action_type}")
        return
    for p in matched:
        click.echo(f"=== {p.action_type} ===")
        click.echo(f"影响: {p.impact}")
        click.echo(f"回滚: {p.rollback}")
        click.echo("步骤:")
        for s in p.steps:
            click.echo(f"  - {s.title}:")
            click.echo(f"    {s.script}")
            if s.note:
                click.echo(f"    注: {s.note}")
        click.echo("⚠ 需 DBA 人工执行，Agent 不自动执行任何写操作")


@cli.command()
@click.option("--db", required=True)
@click.option("--question", required=True, help="问题")
@click.pass_context
def chat(ctx: click.Context, db: str, question: str) -> None:
    """对话问诊。"""
    runner = _load_runner(ctx.obj["config_path"])
    answer = runner.chat(db, question)
    click.echo(answer)


@cli.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8088)
@click.pass_context
def web(ctx: click.Context, host: str, port: int) -> None:
    """启动 Web 控制台。"""
    from ..web.main import create_app

    cfg = load_config(ctx.obj["config_path"])
    app = create_app(cfg)
    import uvicorn

    uvicorn.run(app, host=host, port=port)


@cli.command()
@click.pass_context
def schedule(ctx: click.Context) -> None:
    """启动定时巡检。"""
    from ..scheduler import start_scheduler

    cfg = load_config(ctx.obj["config_path"])
    start_scheduler(cfg)


if __name__ == "__main__":
    cli()
