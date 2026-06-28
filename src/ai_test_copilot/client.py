"""Claude 调用封装。

集中处理：模型选择、adaptive thinking、structured outputs。
所有对 anthropic SDK 的依赖都收敛在这里，方便测试时打桩。
"""

from __future__ import annotations

import os
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from . import prompts
from .models import FailureAnalysis, TestPlan

# 默认用最新最强的 Opus 4.8；可用环境变量覆盖（如换成更省成本的 sonnet）。
DEFAULT_MODEL = os.environ.get("AI_TEST_COPILOT_MODEL", "claude-opus-4-8")
MAX_TOKENS = 16000

T = TypeVar("T", bound=BaseModel)


class CopilotError(RuntimeError):
    """对外暴露的统一异常，隐藏底层 SDK 细节。"""


class Copilot:
    def __init__(self, *, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or DEFAULT_MODEL
        # 不传 api_key 时，SDK 自动读取 ANTHROPIC_API_KEY。
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def _parse(self, *, system: str, user: str, schema: type[T]) -> T:
        try:
            resp = self._client.messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
            )
        except anthropic.AuthenticationError as exc:
            raise CopilotError("鉴权失败：请设置环境变量 ANTHROPIC_API_KEY") from exc
        except anthropic.APIError as exc:
            raise CopilotError(f"调用 Claude 失败：{exc}") from exc

        if resp.parsed_output is None:
            raise CopilotError("模型未返回符合结构的结果（可能触发了安全拒答）")
        return resp.parsed_output

    def generate_tests(self, spec: str) -> TestPlan:
        """根据需求/接口描述生成测试计划。"""
        return self._parse(
            system=prompts.GENERATE_SYSTEM,
            user=f"以下是被测需求/接口描述：\n\n{spec}",
            schema=TestPlan,
        )

    def analyze_failure(self, log: str) -> FailureAnalysis:
        """分析测试失败日志，定位根因。"""
        return self._parse(
            system=prompts.ANALYZE_SYSTEM,
            user=f"以下是测试失败日志：\n\n{log}",
            schema=FailureAnalysis,
        )
