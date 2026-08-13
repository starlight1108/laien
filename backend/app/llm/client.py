"""OpenAI 兼容 LLM 客户端。

设计要点：
- 一套代码兼容 OpenAI / Anthropic / DeepSeek / Gemini / 本地 Ollama。
- 结构化输出：优先使用 response_format(json_schema)；提供商不支持时自动降级为
  普通 JSON 输出 + 客户端解析校验。
- 失败处理：指数退避重试，最终抛 LLMError 交由阶段降级。
- 密钥仅通过构造参数传入（内存），不落盘、不写日志。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        max_retries: int = 2,
        timeout: float = 120.0,
    ) -> None:
        if not base_url:
            raise LLMError("缺少 base_url（请选择提供商或填写自定义 Base URL）")
        if not model:
            raise LLMError("缺少模型名称")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "not-needed"  # Ollama 本地可留空
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.client = OpenAI(
            base_url=self.base_url, api_key=self.api_key, timeout=timeout
        )

    # ------------------------------------------------------------------
    def complete_json(
        self,
        system: str,
        user: str,
        schema: Optional[dict] = None,
        temperature: Optional[float] = None,
    ) -> dict[str, Any]:
        """调用 chat.completions 并解析 JSON 结果。

        schema: {"name": str, "schema": json-schema-dict}
        """
        temp = self.temperature if temperature is None else temperature
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                kwargs: dict[str, Any] = {"temperature": temp}
                if schema is not None:
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema.get("name", "response"),
                            "strict": True,
                            "schema": schema.get("schema", {}),
                        },
                    }
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    **kwargs,
                )
                text = (resp.choices[0].message.content or "").strip()
                return self._parse_json(text)
            except LLMError:
                raise
            except Exception as e:  # noqa: BLE001
                last_err = e
                # json_schema 不受支持时（部分 OpenAI 兼容端点），去掉 schema 重试
                if schema is not None and self._schema_unsupported(str(e)):
                    logger.warning(
                        "提供商不支持 json_schema（%s），降级为普通 JSON 输出重试", self.model
                    )
                    schema = None
                    continue
                delay = min(2 ** attempt, 30)
                time.sleep(delay)
                logger.warning("LLM attempt %d failed: %s", attempt + 1, e)
        raise LLMError(f"LLM 调用失败（model={self.model}）: {last_err}")

    # ------------------------------------------------------------------
    def test_connection(self) -> dict:
        """连通性测试：返回耗时与模型名，供 UI '测试连接' 使用。"""
        start = time.time()
        self.complete_json(
            system="你是测试助手。",
            user="请只回复 JSON：{\"ok\": true}",
        )
        return {"ok": True, "model": self.model, "latency_ms": int((time.time() - start) * 1000)}

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_json(text: str) -> dict:
        # 容忍模型输出被 ```json ... ``` 包裹
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"模型输出不是合法 JSON: {e}") from e
        if not isinstance(data, dict):
            raise LLMError("模型输出应为 JSON 对象")
        return data

    @staticmethod
    def _schema_unsupported(err: str) -> bool:
        return any(
            k in err.lower()
            for k in (
                "response_format",
                "json_schema",
                "not supported",
                "unsupported",
                "invalid parameter",
            )
        )
