"""OpenAI 兼容的聊天客户端（已实测 DeepSeek 官方 API 可用）。

- base_url 默认 https://api.deepseek.com
- 模型默认 deepseek-chat（DeepSeek 官方别名，2026-08 实测可用；
  也可填 deepseek-v4-flash / deepseek-v4-pro 等实际模型 ID）
"""
from __future__ import annotations

from typing import List, Optional

import requests


class ChatClient:
    """同步聊天客户端，失败抛异常，由上层捕获。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: float = 30.0,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.timeout = timeout

    @property
    def _endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def chat(self, messages: List[dict], temperature: float = 0.9, max_tokens: int = 120) -> str:
        """发送多轮消息，返回助手回复文本。"""
        if not self.api_key:
            raise RuntimeError("未配置 AI API Key")
        resp = requests.post(
            self._endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            },
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"AI 接口返回 HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"AI 响应解析失败: {data}") from exc

    def ping(self) -> str:
        """连通性测试（列出可用模型），供 tools/test_ai.py 使用。"""
        resp = requests.get(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=15,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"模型列表请求失败: HTTP {resp.status_code}")
        models = [m.get("id") for m in resp.json().get("data", [])]
        return ", ".join(models) or "（空）"
