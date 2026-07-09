"""AgentEvent 流式事件构造工具。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .models import AgentEvent


def plan(message: str, data: dict[str, Any] | None = None) -> AgentEvent:
    return AgentEvent(stage="plan", status="running", message=message, data=data)


def collect(message: str, data: dict[str, Any] | None = None) -> AgentEvent:
    return AgentEvent(stage="collect", status="running", message=message, data=data)


def diagnose(message: str, data: dict[str, Any] | None = None) -> AgentEvent:
    return AgentEvent(stage="diagnose", status="running", message=message, data=data)


def advise(message: str, data: dict[str, Any] | None = None) -> AgentEvent:
    return AgentEvent(stage="advise", status="running", message=message, data=data)


def done(message: str = "done", data: dict[str, Any] | None = None) -> AgentEvent:
    return AgentEvent(stage="done", status="ok", message=message, data=data)


def error(message: str, data: dict[str, Any] | None = None) -> AgentEvent:
    return AgentEvent(stage="error", status="error", message=message, data=data)


def stream(events: list[AgentEvent]) -> Iterator[AgentEvent]:
    yield from events
