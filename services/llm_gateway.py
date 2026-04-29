"""
services/llm_gateway.py — 統一 LLM 呼叫層
路徑：services/llm_gateway.py

職責：
  - 對外提供唯一的 LLMGateway 介面，Planner 只需呼叫 gateway.chat()
  - 對內處理 Groq / Ollama 的格式差異、retry 邏輯、rate limit 等髒活
  - Tool schema 格式統一為 OpenAI function calling 格式
    （Groq 原生支援；Ollama 先嘗試原生，失敗時 fallback 到 JSON prompt）

使用方式：
    from services.llm_gateway import LLMGateway
    gw = LLMGateway(provider="groq")
    result = await gw.chat(messages, tools)

回傳格式（LLMResponse）：
    result.content   → str | None   （最終文字回覆）
    result.tool_calls→ list[ToolCall]（LLM 要求呼叫的工具）
    result.raw       → dict          （原始 API 回應，debug 用）
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx  # type: ignore

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# 資料結構
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ToolCall:
    """LLM 要求執行的一次工具呼叫"""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """gateway.chat() 統一回傳格式"""
    content: str | None          # 純文字回覆（tool call 輪次可能為 None）
    tool_calls: list[ToolCall]   # LLM 要求的工具呼叫（可能為空）
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def is_final(self) -> bool:
        """沒有 tool call，代表 LLM 已給出最終回覆"""
        return not self.has_tool_calls


# ══════════════════════════════════════════════════════════════════════
# 訊息格式 helpers
# ══════════════════════════════════════════════════════════════════════

def user_message(content: str) -> dict:
    return {"role": "user", "content": content}


def assistant_message(content: str | None = None,
                      tool_calls: list[ToolCall] | None = None) -> dict:
    """組出 assistant 訊息，供加入 history 用"""
    msg: dict = {"role": "assistant", "content": content or ""}
    if tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            for tc in tool_calls
        ]
    return msg


def tool_result_message(tool_call_id: str, name: str, result: str) -> dict:
    """工具執行結果，加回 history 讓 LLM 看到"""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": result,
    }


# ══════════════════════════════════════════════════════════════════════
# Groq 後端
# ══════════════════════════════════════════════════════════════════════

# 依序嘗試的模型（前者優先，失敗時自動 fallback）
_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
]

_GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def _parse_groq_response(data: dict) -> LLMResponse:
    """把 Groq API 回應轉成 LLMResponse"""
    choice = data["choices"][0]
    message = choice["message"]
    content = message.get("content") or None

    tool_calls: list[ToolCall] = []
    for tc in message.get("tool_calls") or []:
        try:
            args = json.loads(tc["function"]["arguments"])
        except (json.JSONDecodeError, KeyError):
            args = {}
        tool_calls.append(ToolCall(
            id=tc.get("id", f"call_{tc['function']['name']}"),
            name=tc["function"]["name"],
            arguments=args,
        ))

    return LLMResponse(content=content, tool_calls=tool_calls, raw=data)


async def _groq_chat(
    messages: list[dict],
    tools: list[dict],
    api_key: str,
    model: str,
    max_tokens: int,
    timeout: int,
) -> LLMResponse:
    """單次 Groq API 呼叫"""
    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            _GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return _parse_groq_response(resp.json())


async def _groq_chat_with_retry(
    messages: list[dict],
    tools: list[dict],
    api_key: str,
    max_tokens: int,
    timeout: int,
) -> LLMResponse:
    """
    依序嘗試 _GROQ_MODELS。
    處理 429 rate limit（讀 retry-after header）與 503 過載（換下一個模型）。
    """
    import re

    for model in _GROQ_MODELS:
        for attempt in range(3):
            try:
                logger.debug(f"[Groq] 使用模型：{model}（第 {attempt + 1} 次）")
                return await _groq_chat(messages, tools, api_key, model, max_tokens, timeout)

            except httpx.HTTPStatusError as e:
                status = e.response.status_code

                if status == 429:
                    # 讀 retry-after，若沒有就等 60 秒
                    retry_after = e.response.headers.get("retry-after", "60")
                    try:
                        wait = int(re.search(r"\d+", retry_after).group()) + 2  # type: ignore[union-attr]
                    except (AttributeError, ValueError):
                        wait = 60
                    logger.warning(f"[Groq] Rate limit，等待 {wait}s 後重試...")
                    await asyncio.sleep(wait)
                    continue  # 同一個模型再試

                if status in (503, 502, 500):
                    logger.warning(f"[Groq] {model} 過載（{status}），換下一個模型")
                    break  # 換下一個模型

                # 其他錯誤直接拋出
                logger.error(f"[Groq] HTTP {status}: {e.response.text[:300]}")
                raise

            except httpx.TimeoutException:
                logger.warning(f"[Groq] {model} 超時（{attempt + 1}/3）")
                if attempt == 2:
                    break  # 換下一個模型

        # 三次都失敗，換下一個模型
    raise RuntimeError("所有 Groq 模型都無法使用，請稍後再試")


# ══════════════════════════════════════════════════════════════════════
# Ollama 後端
# ══════════════════════════════════════════════════════════════════════

def _parse_ollama_response(data: dict) -> LLMResponse:
    """把 Ollama /v1/chat/completions 回應轉成 LLMResponse"""
    choice = data["choices"][0]
    message = choice["message"]
    content = message.get("content") or None

    tool_calls: list[ToolCall] = []
    for tc in message.get("tool_calls") or []:
        try:
            raw_args = tc["function"]["arguments"]
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except (json.JSONDecodeError, KeyError):
            args = {}
        tool_calls.append(ToolCall(
            id=tc.get("id", f"call_{tc['function']['name']}"),
            name=tc["function"]["name"],
            arguments=args,
        ))

    return LLMResponse(content=content, tool_calls=tool_calls, raw=data)


def _build_json_fallback_prompt(tools: list[dict]) -> str:
    """
    當 Ollama 模型不支援原生 tool call 時，
    把工具定義塞進 system prompt，要求模型輸出 JSON。
    """
    tool_desc = json.dumps(tools, ensure_ascii=False, indent=2)
    return f"""你可以使用以下工具（JSON 格式）。
如果需要呼叫工具，請只輸出以下格式的 JSON，不要輸出其他內容：

{{
  "tool_calls": [
    {{
      "name": "工具名稱",
      "arguments": {{ "參數名": "參數值" }}
    }}
  ]
}}

如果不需要呼叫工具，直接用繁體中文回覆使用者。

可用工具：
{tool_desc}
"""


def _try_parse_json_tool_call(content: str) -> list[ToolCall] | None:
    """
    嘗試從純文字中解析 JSON tool call（Ollama fallback 模式用）。
    成功回傳 ToolCall 列表，失敗回傳 None。
    """
    import re

    # 先找 ```json ... ``` 或裸 JSON
    candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if not candidates:
        # 嘗試整個 content 當 JSON
        candidates = [content.strip()]

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            raw_calls = data.get("tool_calls", [])
            if not raw_calls:
                continue
            calls = []
            for tc in raw_calls:
                calls.append(ToolCall(
                    id=f"call_{tc.get('name', 'unknown')}",
                    name=tc["name"],
                    arguments=tc.get("arguments", {}),
                ))
            return calls
        except (json.JSONDecodeError, KeyError):
            continue
    return None


async def _ollama_chat(
    messages: list[dict],
    tools: list[dict],
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: int,
) -> LLMResponse:
    """
    單次 Ollama 呼叫。
    策略：先嘗試原生 tool call；若模型不支援（回傳純文字 JSON），fallback 解析。
    """
    url = f"{base_url.rstrip('/')}/v1/chat/completions"

    # ── 先嘗試原生 tool call ──────────────────────────────────────────
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    result = _parse_ollama_response(data)

    # ── 原生成功（有 tool_calls 或 stop_reason 正常）────────────────
    if result.has_tool_calls:
        logger.debug(f"[Ollama] 原生 tool call 成功：{[tc.name for tc in result.tool_calls]}")
        return result

    # ── 嘗試從文字解析 JSON fallback ─────────────────────────────────
    if result.content and tools:
        parsed = _try_parse_json_tool_call(result.content)
        if parsed:
            logger.debug(f"[Ollama] JSON fallback 解析成功：{[tc.name for tc in parsed]}")
            return LLMResponse(content=None, tool_calls=parsed, raw=data)

    # ── 純文字回覆（不需要工具）──────────────────────────────────────
    return result


async def _ollama_chat_with_start(
    messages: list[dict],
    tools: list[dict],
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: int,
) -> LLMResponse:
    """
    嘗試呼叫 Ollama；若服務未啟動，自動嘗試起動 ollama serve。
    """
    try:
        return await _ollama_chat(messages, tools, base_url, model, max_tokens, timeout)
    except httpx.ConnectError:
        logger.warning("[Ollama] 連線失敗，嘗試自動啟動 ollama serve...")
        started = await _try_start_ollama(base_url)
        if not started:
            raise RuntimeError(
                "無法連線到 Ollama，請手動執行 `ollama serve` 後再試"
            )
        # 稍等讓模型載入
        await asyncio.sleep(3)
        return await _ollama_chat(messages, tools, base_url, model, max_tokens, timeout)


async def _try_start_ollama(base_url: str, wait_secs: int = 20) -> bool:
    """
    嘗試在背景啟動 ollama serve，最多等待 wait_secs 秒。
    回傳是否成功連線。
    """
    import subprocess

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        logger.error("[Ollama] ollama 執行檔不存在，請先安裝 Ollama")
        return False

    tags_url = f"{base_url.rstrip('/')}/api/tags"
    for i in range(wait_secs):
        await asyncio.sleep(1)
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                r = await client.get(tags_url)
                if r.status_code == 200:
                    logger.info(f"[Ollama] 服務已啟動（等待 {i + 1}s）")
                    return True
        except Exception:
            pass
    logger.error("[Ollama] 服務啟動超時")
    return False


# ══════════════════════════════════════════════════════════════════════
# 主要介面：LLMGateway
# ══════════════════════════════════════════════════════════════════════

class LLMGateway:
    """
    統一 LLM 呼叫介面。

    使用方式：
        from services.llm_gateway import LLMGateway
        from config import cfg

        gateway = LLMGateway.from_config(cfg, provider="groq")
        response = await gateway.chat(messages, tools)

    provider 優先順序：
        1. 明確傳入 provider 參數
        2. cfg.llm.provider（來自 .env LLM_PROVIDER）
        3. 預設 "groq"
    """

    def __init__(
        self,
        provider: str,
        *,
        groq_api_key: str = "",
        groq_model: str = "llama-3.3-70b-versatile",
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5:14b",
        max_tokens: int = 1024,
        timeout: int = 60,
    ) -> None:
        if provider not in ("groq", "ollama"):
            raise ValueError(f"不支援的 provider：{provider!r}，請使用 'groq' 或 'ollama'")
        self.provider = provider
        self._groq_api_key = groq_api_key
        self._groq_model = groq_model
        self._ollama_base_url = ollama_base_url
        self._ollama_model = ollama_model
        self._max_tokens = max_tokens
        self._timeout = timeout

    @classmethod
    def from_config(cls, cfg: Any, provider: str | None = None) -> "LLMGateway":
        """
        從 Config 物件建立 Gateway。
        provider 可覆蓋 cfg 的預設值（router 用來強制指定 ollama）。
        """
        lc = cfg.llm
        resolved = provider or lc.provider
        # auto 模式下，gateway 層不做路由決策，由 router.py 決定後再傳入
        if resolved == "auto":
            resolved = lc.cloud_provider
        return cls(
            provider=resolved,
            groq_api_key=lc.groq_api_key,
            groq_model=lc.groq_model,
            ollama_base_url=lc.ollama_base_url,
            ollama_model=lc.ollama_model,
            max_tokens=lc.max_tokens,
            timeout=lc.timeout,
        )

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """
        核心呼叫方法。

        Args:
            messages: OpenAI 格式的對話歷史
                [{"role": "user", "content": "..."}, ...]
            tools: OpenAI function calling 格式的工具定義清單
                [{"name": "get_weather", "description": "...", "parameters": {...}}, ...]
                傳入 None 或 [] 代表不提供工具

        Returns:
            LLMResponse：含 content（文字）與 tool_calls（工具呼叫請求）
        """
        tools = tools or []
        logger.debug(f"[Gateway] provider={self.provider}, messages={len(messages)}, tools={len(tools)}")

        if self.provider == "groq":
            return await _groq_chat_with_retry(
                messages=messages,
                tools=tools,
                api_key=self._groq_api_key,
                max_tokens=self._max_tokens,
                timeout=self._timeout,
            )

        # ollama
        return await _ollama_chat_with_start(
            messages=messages,
            tools=tools,
            base_url=self._ollama_base_url,
            model=self._ollama_model,
            max_tokens=self._max_tokens,
            timeout=self._timeout,
        )

    def __repr__(self) -> str:
        if self.provider == "groq":
            return f"LLMGateway(groq, model={self._groq_model!r})"
        return f"LLMGateway(ollama, model={self._ollama_model!r}, url={self._ollama_base_url!r})"
