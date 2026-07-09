"""FastAPI Web 控制台：宣传主页 + 巡检/诊断/性能/恢复 API + SSE 对话。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from importlib import resources

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from ..config import AppConfig
from ..runner import AgentRunner

_CONSOLE_HTML = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>DBA Agent 控制台</title>
<style>body{font-family:sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}
h1{font-size:1.4rem} .box{border:1px solid #ddd;padding:1rem;margin:1rem 0;border-radius:6px}
pre{background:#f6f8fa;padding:.5rem;overflow:auto;white-space:pre-wrap}
input,button{padding:.4rem .6rem;margin:.2rem}</style></head>
<body><h1>DBA 智能运维 Agent 控制台</h1>
<p><a href="/">← 返回宣传主页</a></p>
<div class="box"><h3>巡检/诊断</h3>
<input id="db" placeholder="数据库实例名" value="prod-mysql">
<button onclick="runTask('patrol')">巡检</button>
<button onclick="runTask('diagnose:锁等待')">异常诊断</button>
<button onclick="runTask('perf')">性能诊断</button>
</div>
<div class="box"><h3>对话问诊</h3>
<input id="q" placeholder="如：prod 库为什么慢" style="width:60%">
<button onclick="chat()">提问</button></div>
<div class="box"><h3>事件流</h3><pre id="log">（等待操作）</pre></div>
<script>
async function runTask(task){
  const db=document.getElementById('db').value;
  const log=document.getElementById('log');
  log.textContent='';
  const resp=await fetch('/api/run?db='+encodeURIComponent(db)+'&task='+encodeURIComponent(task));
  const reader=resp.body.getReader();const dec=new TextDecoder();
  while(true){const {done,value}=await reader.read();if(done)break;
  log.textContent+=dec.decode(value);}
}
async function chat(){
  const db=document.getElementById('db').value;const q=document.getElementById('q').value;
  const resp=await fetch(`/api/chat?db=${encodeURIComponent(db)}&q=${encodeURIComponent(q)}`);
  document.getElementById('log').textContent=await resp.text();
}
</script></body></html>"""


def _load_landing() -> str:
    try:
        return resources.files(__package__).joinpath("landing.html").read_text(encoding="utf-8")
    except Exception:
        return _CONSOLE_HTML


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="DBA Ops Agent")
    runner = AgentRunner(config)
    landing_html = _load_landing()

    @app.get("/", response_class=HTMLResponse)
    def landing() -> str:
        return landing_html

    @app.get("/console", response_class=HTMLResponse)
    def console() -> str:
        return _CONSOLE_HTML

    @app.get("/api/run")
    def run(db: str, task: str) -> StreamingResponse:
        def gen() -> Iterator[bytes]:
            for ev in runner.run(db, task):
                yield (json.dumps(ev.to_dict(), ensure_ascii=False) + "\n").encode("utf-8")

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @app.get("/api/chat")
    def chat(db: str, q: str) -> str:
        return runner.chat(db, q)

    @app.get("/api/last/{db}")
    def last(db: str) -> dict:
        report = runner.last_report(db)
        plans = runner.last_plans(db) or []
        return {
            "report": report.narrative if report else None,
            "llm_available": report.llm_available if report else None,
            "plans": [p.__dict__ for p in plans],
        }

    return app
