"""模型调用封装（OpenAI 兼容）。

为兼容各家国产/开源模型，这里用 openai SDK + 可配置 base_url，
任何 OpenAI 兼容的服务（硅基流动 / DeepSeek / 通义千问 / Kimi / 智谱 / OpenAI…）
都能直接接入。结构化输出用「JSON 模式 + 本地 Pydantic 校验 + 一次纠错重试」实现，
不依赖各家不统一的 strict json_schema。
"""

from __future__ import annotations

import json
import os
from typing import TypeVar

import openai
from pydantic import BaseModel, ValidationError

from . import prompts
from .models import FailureAnalysis, TestPlan

# 默认指向硅基流动；都可用环境变量覆盖。
DEFAULT_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "deepseek-ai/DeepSeek-V3")
TEMPERATURE = 0.3
MAX_TOKENS = 8000

T = TypeVar("T", bound=BaseModel)


class CopilotError(RuntimeError):
    """对外暴露的统一异常，隐藏底层 SDK 细节。"""


def _strip_fences(text: str) -> str:
    """去掉模型有时擅自加上的 ```json 代码围栏。"""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: -3]
    return t.strip()


class Copilot:
    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model or DEFAULT_MODEL
        key = api_key or os.environ.get("LLM_API_KEY")
        if not key:
            raise CopilotError("缺少 LLM_API_KEY（模型服务的 API key）")
        self._client = openai.OpenAI(api_key=key, base_url=base_url or DEFAULT_BASE_URL)

    def _create(self, messages: list[dict], *, json_mode: bool):
        kwargs = dict(model=self.model, messages=messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            return self._client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise CopilotError("鉴权失败：请检查 LLM_API_KEY") from exc
        except openai.BadRequestError:
            # 个别模型不支持 response_format，降级为纯提示词约束。
            if json_mode:
                return self._create(messages, json_mode=False)
            raise
        except openai.APIError as exc:
            raise CopilotError(f"调用模型失败：{exc}") from exc

    def _complete_json(self, *, system: str, user: str, schema: type[T]) -> T:
        schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        sys_full = (
            f"{system}\n\n"
            "只输出一个 JSON 对象，不要任何额外文字、解释或 markdown 代码块。"
            f"JSON 必须严格符合以下 JSON Schema：\n{schema_text}"
        )
        messages = [
            {"role": "system", "content": sys_full},
            {"role": "user", "content": user},
        ]

        last_err: Exception | None = None
        for _ in range(2):  # 最多一次纠错重试
            resp = self._create(messages, json_mode=True)
            content = resp.choices[0].message.content or ""
            try:
                return schema.model_validate_json(_strip_fences(content))
            except ValidationError as exc:
                last_err = exc
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {"role": "user", "content": f"上面的 JSON 不符合要求：{exc}\n请只输出修正后的 JSON。"}
                )
        raise CopilotError(f"模型返回的结果无法解析为期望结构：{last_err}")

    def generate_tests(self, spec: str) -> TestPlan:
        """根据需求/接口描述生成测试计划。"""
        return self._complete_json(
            system=prompts.GENERATE_SYSTEM,
            user=f"以下是被测需求/接口描述：\n\n{spec}",
            schema=TestPlan,
        )

    def analyze_failure(self, log: str) -> FailureAnalysis:
        """分析测试失败日志，定位根因。"""
        return self._complete_json(
            system=prompts.ANALYZE_SYSTEM,
            user=f"以下是测试失败日志：\n\n{log}",
            schema=FailureAnalysis,
        )
