"""LLM 根因综合、对话问答，含规则降级。"""

from __future__ import annotations

import json
import logging

from ..config import LLMConfig
from ..models import Finding, Report
from .client import LLMClient, LLMUnavailable

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是一名资深数据库 DBA。根据提供的诊断发现（含指标值、证据、初步根因），"
    "用自然语言写一份根因报告，要求：1) 指出最可能的根因；2) 引用具体证据（指标值/样本）；"
    "3) 给出处置建议但强调需人工验证后执行。用中文回答。"
)

_CHAT_SYSTEM_PROMPT = (
    "你是一名资深数据库 DBA 助手。根据用户问题与已采集的诊断上下文，回答数据库运维问题。"
    "若上下文不足，说明需要采集哪些指标。用中文回答。"
)


def _findings_to_context(findings: list[Finding]) -> str:
    items = []
    for f in findings:
        items.append(
            {
                "metric": f.metric,
                "severity": f.severity.value,
                "symptom": f.symptom,
                "evidence": f.evidence,
                "root_cause": f.root_cause,
                "suggestion": f.suggestion,
            }
        )
    return json.dumps(items, ensure_ascii=False)


def _rule_fallback_narrative(findings: list[Finding]) -> str:
    lines = ["[LLM 不可用，以下为规则结论]"]
    for f in findings:
        if f.severity.value in ("正常", "error") and f.severity.value != "error":
            if f.severity.value == "正常":
                continue
        lines.append(f"- {f.metric} [{f.severity.value}]: {f.symptom}")
        if f.root_cause:
            lines.append(f"  根因: {f.root_cause}")
        if f.suggestion:
            lines.append(f"  建议: {'; '.join(f.suggestion)}")
    return "\n".join(lines)


def explain_findings(
    findings: list[Finding],
    db: str,
    task: str,
    client: LLMClient | None = None,
) -> Report:
    if client is None or not client.available:
        return Report(
            database=db,
            task=task,
            findings=findings,
            narrative=_rule_fallback_narrative(findings),
            llm_available=False,
        )
    try:
        user_msg = f"数据库: {db}\n任务: {task}\n诊断发现:\n{_findings_to_context(findings)}"
        text = client.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ]
        )
        return Report(
            database=db,
            task=task,
            findings=findings,
            narrative=text,
            llm_available=True,
        )
    except LLMUnavailable as e:
        logger.warning("explain_findings LLM 不可用，降级规则结论: %s: %s", type(e).__name__, e)
        return Report(
            database=db,
            task=task,
            findings=findings,
            narrative=_rule_fallback_narrative(findings),
            llm_available=False,
        )


def chat_with_context(
    question: str,
    findings: list[Finding] | None = None,
    client: LLMClient | None = None,
) -> str:
    context = _findings_to_context(findings) if findings else "无已采集上下文"
    if client is None or not client.available:
        return _rule_fallback_narrative(findings or []) + f"\n\n用户问题: {question}"
    try:
        return client.chat(
            [
                {"role": "system", "content": _CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": f"已采集上下文:\n{context}\n\n用户问题: {question}"},
            ]
        )
    except LLMUnavailable as e:
        logger.warning("chat_with_context LLM 不可用，降级规则结论: %s: %s", type(e).__name__, e)
        return _rule_fallback_narrative(findings or []) + f"\n\n用户问题: {question}"


class LLMCore:
    """LLM 推理核心顶层封装。"""

    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg
        self.client = LLMClient(cfg)

    @property
    def is_available(self) -> bool:
        return self.client.available

    def explain(self, findings: list[Finding], db: str, task: str) -> Report:
        return explain_findings(findings, db, task, self.client)

    def chat(self, question: str, findings: list[Finding] | None = None) -> str:
        return chat_with_context(question, findings, self.client)
