"""OpenAI 兼容客户端封装。"""

from __future__ import annotations

import logging

from ..config import LLMConfig

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg
        self._client = None
        self._available = False
        if not cfg.enabled:
            self._available = False
            return
        try:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=cfg.base_url or None,
                api_key=cfg.api_key or "EMPTY",
                timeout=cfg.timeout,
            )
            self._available = True
        except Exception as e:
            logger.warning("LLM 客户端初始化失败: %s: %s", type(e).__name__, e)
            self._client = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def chat(self, messages: list[dict], timeout: int | None = None) -> str:
        if not self._available or self._client is None:
            raise LLMUnavailable("LLM client not available")
        try:
            kwargs: dict = {
                "model": self.cfg.model,
                "messages": messages,
            }
            if timeout is not None:
                kwargs["timeout"] = timeout
            resp = self._client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as e:
            raise LLMUnavailable(str(e)) from e
