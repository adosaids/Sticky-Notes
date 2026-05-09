"""
AI 任务整理器：异步流式调用（aiohttp + asyncio）
"""

import json
import re

import aiohttp


AI_DISCUSS_PROMPT = """你是一个任务规划助手。帮助用户整理、拆分、重组任务。
用自然语言回答，可以给出建议、分析、追问。
不需要返回 JSON，正常对话即可。"""

AI_WRITE_PROMPT = """你是一个任务规划助手。请将对话内容整理为层级化任务列表。

规则：
1. 只返回纯 JSON 数组，不要 markdown 代码块、不要任何解释文字。
2. 数组中每个对象必须包含：
   - "text": 字符串，任务描述
   - "level": 整数 1-4（1=顶级目标/分类，2=子目标，3=可执行任务，4=详细步骤）
3. 顺序必须是：子任务紧跟在父任务之后。
4. 合并相似的任务，将模糊的大任务拆分为具体的子任务。
5. 所有任务的 completed 字段都为 false。"""


class AIOrganizer:
    """异步 OpenAI 兼容 API 客户端（aiohttp）"""

    def __init__(self, config: dict):
        self.endpoint = config.get("endpoint", "").rstrip("/")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "")

    def _build_url(self) -> str:
        url = self.endpoint
        if not url.endswith("/chat/completions"):
            url = url.rstrip("/") + "/chat/completions"
        return url

    async def chat(self, messages: list[dict], on_chunk, on_complete, on_error,
                   mode: str = "discuss"):
        """异步流式聊天。

        mode: "discuss" = 讨论模式（自然语言）
              "write"   = 写入模式（强制返回 JSON）
        """
        system_prompt = AI_DISCUSS_PROMPT if mode == "discuss" else AI_WRITE_PROMPT

        # 确保 system message 在最前
        full_messages = list(messages)
        if not any(m["role"] == "system" for m in full_messages):
            full_messages.insert(0, {"role": "system", "content": system_prompt})

        payload = {
            "model": self.model if self.model else "gpt-4o-mini",
            "messages": full_messages,
            "temperature": 0.3,
            "stream": True,
        }

        url = self._build_url()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        on_error(f"API 请求失败 (HTTP {resp.status}): {body}")
                        return
                    await self._read_stream(resp, on_chunk, on_complete)
        except Exception as e:
            on_error(f"请求失败: {e}")

    @staticmethod
    async def _read_stream(resp, on_chunk, on_complete):
        """按行读取 SSE 流，逐 event 回调。"""
        buffer = ""
        async for line_bytes in resp.content:
            try:
                line = line_bytes.decode("utf-8").strip()
            except Exception:
                continue
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    on_complete()
                    return
                try:
                    event = json.loads(data_str)
                    delta = event.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        on_chunk(content)
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass

    async def test_connection(self) -> tuple[bool, str]:
        """测试 API 连接。"""
        payload = {
            "model": self.model if self.model else "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
        }
        url = self._build_url()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return True, "连接成功"
                    else:
                        body = await resp.text()
                        return False, f"HTTP {resp.status}: {body}"
        except Exception as e:
            return False, f"连接失败: {e}"

    @staticmethod
    def parse_tasks_from_text(text: str) -> list[dict] | None:
        """从文本中提取 JSON 数组。"""
        # 直接解析
        try:
            items = json.loads(text)
            if isinstance(items, list):
                return items
        except json.JSONDecodeError:
            pass

        # markdown 代码块
        match = re.search(r"```(?:json)?\s*\n([\s\S]*?)\n?```", text)
        if match:
            try:
                items = json.loads(match.group(1))
                if isinstance(items, list):
                    return items
            except json.JSONDecodeError:
                pass

        # 提取 [ ... ]
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                items = json.loads(match.group(0))
                if isinstance(items, list):
                    return items
            except json.JSONDecodeError:
                pass

        return None
