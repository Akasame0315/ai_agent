from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import httpx
from groq import AsyncGroq

logger = logging.getLogger(__name__)


@dataclass
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMGateway:
    def __init__(self, cfg: dict, debug: bool = False):
        self.root_cfg = cfg
        self.cfg = cfg["llm"]
        self.agent_cfg = cfg.get("agent", {})
        self.debug = debug
        self._groq_client: AsyncGroq | None = None
        self._http_client: httpx.AsyncClient | None = None

    def _build_system_prompt(self) -> str:
        assistant_name = self.agent_cfg.get("assistant_name") or "助理"
        owner_name = self.agent_cfg.get("owner_name") or self.agent_cfg.get("name") or "使用者"
        persona = self.agent_cfg.get("persona") or "assistant"
        city = self.agent_cfg.get("city") or "Taipei"
        language = self.agent_cfg.get("language") or "zh-TW"
        custom_prompt = self.agent_cfg.get("system_prompt", "").strip()

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
        return prompt

    def _log_prompt(self, system_prompt: str, messages: list[Message]):
        """Debug 模式下印出 system prompt 與最後一條 user message"""
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
            logger.warning("Groq API key not available; falling back to Ollama.")
            provider = "ollama"

        sys_prompt = system_prompt or self._build_system_prompt()

        self._log_prompt(sys_prompt, messages)

        if provider == "groq":
            return await self._call_groq(messages, sys_prompt)
        return await self._call_ollama(messages, sys_prompt)

    async def _call_groq(
        self,
        messages: list[Message],
        system_prompt: str,
    ) -> LLMResponse:
        formatted = [{"role": "system", "content": system_prompt}]
        formatted += [{"role": m.role, "content": m.content} for m in messages]

        try:
            response = await self._groq_client.chat.completions.create(
                model=self.cfg["groq_model"],
                messages=formatted,
                max_tokens=self.cfg["max_tokens"],
                temperature=self.cfg["temperature"],
            )
            choice = response.choices[0]
            return LLMResponse(
                content=choice.message.content,
                provider="groq",
                model=self.cfg["groq_model"],
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )
        except Exception as exc:
            logger.error("Groq request failed: %s", exc)
            raise

    async def _call_ollama(
        self,
        messages: list[Message],
        system_prompt: str,
    ) -> LLMResponse:
        if not self._http_client:
            raise RuntimeError("HTTP client is not initialized. Call start() first.")

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
            return LLMResponse(
                content=data["message"]["content"],
                provider="ollama",
                model=self.cfg["ollama_model"],
            )
        except httpx.ConnectError:
            raise RuntimeError(
                "Cannot connect to Ollama. Please make sure `ollama serve` is running."
            )
        except Exception as exc:
            logger.error("Ollama request failed: %s", exc)
            raise
