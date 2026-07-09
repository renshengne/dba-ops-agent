"""LLM 推理核心（OpenAI 兼容）。"""

from .client import LLMClient
from .core import LLMCore

__all__ = ["LLMClient", "LLMCore"]
