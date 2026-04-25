"""
services/llm_gateway.py
LLM Gateway — Groq / Ollama 路由，支援 Tool Call（function calling）
- Groq：原生 function calling API
- Ollama：先嘗試原生，失敗時 fallback 到 system prompt JSON 模式
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from groq import AsyncGroq

logger = logging.getLogger(__name__)


# ======================================================================
# Data classes
# ======================================================================

@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None   # role="tool" 時填入
    tool_calls: list[dict] | None = None  # role="assistant" 且有 tool call 時填入


@dataclass
class ToolCall:
    """LLM 要求呼叫的工具"""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


# ======================================================================
# LLMGateway
# ======================================================================

class LLMGateway:
    def __init__(self, cfg: dict, debug: bool = False):
        self.root_cfg = cfg
        self.cfg = cfg["llm"]
        self.agent_cfg = cfg.get("agent", {})
        self.debug = debug
        self._groq_client: AsyncGroq | None = None
        self._http_client: httpx.AsyncClient | None = None
        # 註冊的 tool schemas（由 Planner 呼叫 register_tools 設定）
        self._tools: list[dict] = []

    # ------------------------------------------------------------------
    # Tool 註冊
    # ------------------------------------------------------------------

    def register_tools(self, schemas: list[dict]):
        """
        由 Planner 在初始化時呼叫，傳入所有啟用技能的 TOOL_SCHEMA。
        schemas 格式為 OpenAI function calling 格式。
        """
        self._tools = schemas
        logger.info("已註冊 %d 個工具: %s", len(schemas), [s["name"] for s in schemas])

    # ------------------------------------------------------------------
    # 生命週期
    # ------------------------------------------------------------------

    async def start(self):
        if self.cfg.get("groq_api_key"):
            self._groq_client = AsyncGroq(api_key=self.cfg["groq_api_key"])
        self._http_client = httpx.AsyncClient(
            base_url=self.cfg["ollama_base_url"],
            timeout=self.cfg["timeout"],
        )
        logger.info("LLM Gateway started.")

    async def stop(self):
        if self._http_client:
            await self._http_client.aclose()
        if self._groq_client:
            await self._groq_client.close()

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _build_system_prompt(self, include_tool_fallback: bool = False) -> str:
        agent_cfg = self.agent_cfg
        assistant_name = agent_cfg.get("assistant_name") or "助理"
        owner_name     = agent_cfg.get("owner_name") or "使用者"
        persona        = agent_cfg.get("persona") or "assistant"
        city           = agent_cfg.get("city") or "Taipei"
        language       = agent_cfg.get("language") or "zh-TW"
        custom_prompt  = agent_cfg.get("system_prompt", "").strip()

        prompt = (
            f"你是一個智慧個人助理。\n"
            f"你的名字是 {assistant_name}。\n"
            f"你的主要使用者是 {owner_name}。\n"
            f"你的角色風格是 {persona}。\n"
            f"你的預設地區是 {city}。\n"
            f"請優先使用 {language} 回覆。\n"
            "不要把使用者的名字誤認成你自己的名字。\n"
            f"當你需要稱呼使用者時，優先稱呼對方為 {owner_name}。\n"
            "回覆時直接、清楚、實用，不要編造資訊。"
        )
        if custom_prompt:
            prompt += f"\n{custom_prompt}"

        # Ollama fallback：在 system prompt 裡描述工具格式
        if include_tool_fallback and self._tools:
            tool_descs = "\n".join(
                f'- {t["name"]}: {t["description"]}  參數: {json.dumps(t["parameters"], ensure_ascii=False)}'
                for t in self._tools
            )
            prompt += (
                "\n\n你可以使用以下工具。若需要呼叫工具，"
                "請只輸出一個 JSON 物件（不要加任何其他文字）：\n"
                '{"tool": "<工具名稱>", "args": {<參數>}}\n'
                f"可用工具：\n{tool_descs}\n"
                "若不需要呼叫工具，正常回覆即可。"
            )

        return prompt

    # ------------------------------------------------------------------
    # Debug log
    # ------------------------------------------------------------------

    def _log_prompt(self, system_prompt: str, messages: list[Message]):
        if not self.debug:
            return
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "(無 user message)",
        )
        logger.info("=" * 50)
        logger.info("[DEBUG] system prompt:\n%s", system_prompt)
        logger.info("[DEBUG] last user message:\n%s", last_user)
        logger.info("=" * 50)

    def _build_json_tool_prompt(self, base_system_prompt: str) -> str:
        """Append explicit JSON tool-call instructions for fallback mode."""
        if not self._tools:
            return base_system_prompt

        tool_descs = "\n".join(
            f'- {t["name"]}: params={json.dumps(t["parameters"], ensure_ascii=False)}'
            for t in self._tools
        )
        return (
            f"{base_system_prompt}\n\n"
            "If you need to use a tool, do not use native function calling markup.\n"
            "Output exactly one JSON object and nothing else.\n"
            'Format: {"tool": "<tool_name>", "args": {...}}\n'
            "If no tool is needed, answer normally.\n"
            f"Available tools:\n{tool_descs}"
        )

    def _should_fallback_groq_tool_call(self, exc: Exception) -> bool:
        text = str(exc)
        return "tool_use_failed" in text or "tool call validation failed" in text

    # ------------------------------------------------------------------
    # 公開 chat 介面
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[Message],
        *,
        force_local: bool = False,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        provider = self.cfg["default_provider"]
        if force_local:
            provider = "ollama"
        if provider == "groq" and not self._groq_client:
            logger.warning("Groq API key 未設定，fallback 到 Ollama")
            provider = "ollama"

        sys_prompt = system_prompt or self._build_system_prompt(
            include_tool_fallback=(provider == "ollama")
        )
        self._log_prompt(sys_prompt, messages)

        if provider == "groq":
            return await self._call_groq(messages, sys_prompt)
        return await self._call_ollama(messages, sys_prompt)

    # ------------------------------------------------------------------
    # Groq（原生 function calling）
    # ------------------------------------------------------------------

    async def _call_groq(self, messages: list[Message], system_prompt: str) -> LLMResponse:
        formatted = [{"role": "system", "content": system_prompt}]
        for m in messages:
            if m.role == "tool":
                formatted.append({
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": m.content,
                })
            elif m.tool_calls:
                formatted.append({
                    "role": "assistant",
                    "content": m.content or "",
                    "tool_calls": m.tool_calls,
                })
            else:
                formatted.append({"role": m.role, "content": m.content})

        kwargs: dict[str, Any] = {
            "model": self.cfg["groq_model"],
            "messages": formatted,
            "max_tokens": self.cfg["max_tokens"],
            "temperature": self.cfg["temperature"],
        }
        if self._tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in self._tools]
            kwargs["tool_choice"] = "auto"

        try:
            response = await self._groq_client.chat.completions.create(**kwargs)
        except Exception as exc:
            if self._tools and self._should_fallback_groq_tool_call(exc):
                logger.warning("Groq native tool call failed, fallback to JSON mode: %s", exc)
                return await self._call_groq_json_fallback(messages, system_prompt)
            logger.error("Groq request failed: %s", exc)
            raise

        choice = response.choices[0]
        msg = choice.message
        tool_calls: list[ToolCall] = []

        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        return LLMResponse(
            content=msg.content or "",
            provider="groq",
            model=self.cfg["groq_model"],
            tool_calls=tool_calls,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )

    async def _call_groq_json_fallback(
        self, messages: list[Message], system_prompt: str
    ) -> LLMResponse:
        formatted = [{
            "role": "system",
            "content": self._build_json_tool_prompt(system_prompt),
        }]
        for m in messages:
            if m.role == "tool":
                formatted.append({
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": m.content,
                })
            else:
                formatted.append({"role": m.role, "content": m.content})

        response = await self._groq_client.chat.completions.create(
            model=self.cfg["groq_model"],
            messages=formatted,
            max_tokens=self.cfg["max_tokens"],
            temperature=0,
        )

        choice = response.choices[0]
        msg = choice.message
        content = msg.content or ""
        tool_calls = self._parse_json_tool_call(content)

        return LLMResponse(
            content=content if not tool_calls else "",
            provider="groq",
            model=self.cfg["groq_model"],
            tool_calls=tool_calls,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )

    # ------------------------------------------------------------------
    # Ollama（原生 → JSON fallback）
    # ------------------------------------------------------------------

    async def _call_ollama(self, messages: list[Message], system_prompt: str) -> LLMResponse:
        if not self._http_client:
            raise RuntimeError("HTTP client 未初始化，請先呼叫 start()")

        # 先嘗試原生 tool call（Ollama >= 0.3 + 支援的模型）
        if self._tools:
            try:
                return await self._call_ollama_native_tools(messages, system_prompt)
            except Exception as e:
                logger.warning("Ollama 原生 tool call 失敗，fallback 到 JSON 模式: %s", e)

        return await self._call_ollama_json_fallback(messages, system_prompt)

    async def _call_ollama_native_tools(
        self, messages: list[Message], system_prompt: str
    ) -> LLMResponse:
        """Ollama 原生 function calling（qwen2.5 等支援的模型）"""
        payload = {
            "model": self.cfg["ollama_model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                *[{"role": m.role, "content": m.content} for m in messages],
            ],
            "tools": [{"type": "function", "function": t} for t in self._tools],
            "stream": False,
            "options": {
                "temperature": self.cfg["temperature"],
                "num_predict": self.cfg["max_tokens"],
            },
        }

        resp = await self._http_client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        msg = data["message"]
        tool_calls: list[ToolCall] = []

        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(ToolCall(
                id=tc.get("id", f"call_{fn.get('name', 'unknown')}"),
                name=fn.get("name", ""),
                arguments=args,
            ))

        return LLMResponse(
            content=msg.get("content") or "",
            provider="ollama",
            model=self.cfg["ollama_model"],
            tool_calls=tool_calls,
        )

    async def _call_ollama_json_fallback(
        self, messages: list[Message], system_prompt: str
    ) -> LLMResponse:
        """
        Ollama JSON fallback：system prompt 內描述工具格式，
        解析 LLM 輸出的 {"tool": ..., "args": ...}
        """
        payload = {
            "model": self.cfg["ollama_model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                *[{"role": m.role, "content": m.content} for m in messages],
            ],
            "stream": False,
            "options": {
                "temperature": self.cfg["temperature"],
                "num_predict": self.cfg["max_tokens"],
            },
        }

        try:
            resp = await self._http_client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.ConnectError:
            raise RuntimeError("無法連接 Ollama，請確認 `ollama serve` 已啟動")
        except Exception as exc:
            logger.error("Ollama request failed: %s", exc)
            raise

        content: str = data["message"]["content"]
        tool_calls = self._parse_json_tool_call(content)

        return LLMResponse(
            content=content if not tool_calls else "",
            provider="ollama",
            model=self.cfg["ollama_model"],
            tool_calls=tool_calls,
        )

    # ------------------------------------------------------------------
    # JSON tool call 解析（fallback 用）
    # ------------------------------------------------------------------

    _JSON_PATTERN = re.compile(r'\{.*?"tool"\s*:.*?"args"\s*:.*?\}', re.DOTALL)

    def _parse_json_tool_call(self, text: str) -> list[ToolCall]:
        """
        從 LLM 輸出中解析 {"tool": "...", "args": {...}} 格式。
        若解析失敗或格式不符，回傳空列表（視為一般文字回覆）。
        """
        match = self._JSON_PATTERN.search(text)
        if not match:
            return []
        try:
            obj = json.loads(match.group())
            tool_name = obj.get("tool", "")
            args = obj.get("args", {})
            # 驗證是否為已知工具
            known = {t["name"] for t in self._tools}
            if tool_name not in known:
                return []
            return [ToolCall(id="fallback_0", name=tool_name, arguments=args)]
        except (json.JSONDecodeError, TypeError):
            return []
