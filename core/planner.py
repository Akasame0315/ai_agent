"""
core/planner.py — 對話管理 + Tool Call Loop
路徑：core/planner.py

流程：
  使用者訊息
    → router 決定 provider（groq / ollama）
    → LLMGateway.chat()（附帶 skill 提供的 tool schemas）
    → 若 LLM 回傳 tool_calls：
        a. skill.requires_confirmation=True → 暫存 pending，回傳確認提示
        b. 否則直接 SkillRegistry.dispatch() → 結果加回 history → 繼續 loop
    → 最終 LLM 輸出純文字 → 回傳給 Telegram Bot

依賴：
  - services/llm_gateway.py   LLMGateway, LLMResponse, ToolCall
  - core/skill_registry.py    SkillRegistry
  - core/router.py            resolve_provider(message) → "groq" | "ollama"
  - config.py                 Config（透過 LLMGateway.from_config 建立）
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from services.llm_gateway import (
    LLMGateway,
    LLMResponse,
    ToolCall,
    assistant_message,
    tool_result_message,
    user_message,
)

if TYPE_CHECKING:
    from core.skill_registry import SkillRegistry
    from config import Config

logger = logging.getLogger(__name__)

# 單次對話最多執行幾次 tool call（防止無限迴圈）
_MAX_TOOL_ROUNDS = 5


# ══════════════════════════════════════════════════════════════════════
# 對話上下文
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PendingConfirmation:
    """等待使用者 /confirm 確認的 tool call"""
    tool_call: ToolCall
    description: str    # 顯示給使用者的說明文字


@dataclass
class ConversationContext:
    """
    單一使用者的對話上下文。
    history 存放 OpenAI 格式的訊息 dict 清單。
    """
    user_id: int
    # OpenAI message dict 清單
    history: list[dict] = field(default_factory=list)
    # 保留最近幾條訊息（太長時截尾，保留 system prompt 在外層）
    max_history: int = 40
    # 等待確認的操作
    pending: PendingConfirmation | None = None

    def append(self, msg: dict) -> None:
        self.history.append(msg)
        # 超過上限時，捨棄最舊的訊息
        # 保留偶數條（user/assistant 成對），避免切到一半
        if len(self.history) > self.max_history:
            self.history = self.history[-(self.max_history):]

    def messages(self) -> list[dict]:
        """回傳 history 副本，供 LLMGateway 使用"""
        return list(self.history)


# ══════════════════════════════════════════════════════════════════════
# System Prompt
# ══════════════════════════════════════════════════════════════════════

def _build_system_prompt(cfg: "Config") -> str:
    name = cfg.agent.owner_name
    city = cfg.agent.city
    return (
        f"你是一個個人 AI 助理，請稱呼使用者為「{name}」。\n"
        f"使用者位於 {city}，請以繁體中文回覆，語氣專業但友善。\n"
        "你可以使用提供的工具來完成任務。\n"
        "不確定的事情請直說，不要捏造資訊。"
    )


# ══════════════════════════════════════════════════════════════════════
# Planner
# ══════════════════════════════════════════════════════════════════════

class Planner:
    """
    Tool Call Loop 的核心控制器。

    初始化流程（main.py）：
        registry = SkillRegistry()
        await registry.discover(cfg.paths.skills)
        planner = Planner(cfg, registry)

    Telegram Bot 呼叫：
        reply = await planner.process(user_id, user_message)
        reply = await planner.handle_confirm(user_id)
        reply = await planner.handle_cancel(user_id)
        planner.clear_context(user_id)
    """

    def __init__(
        self,
        cfg: "Config",
        registry: "SkillRegistry",
        debug: bool = False,
    ) -> None:
        self._cfg = cfg
        self._registry = registry
        self._debug = debug
        self._system_prompt = _build_system_prompt(cfg)
        # user_id → ConversationContext
        self._contexts: dict[int, ConversationContext] = {}

    # ── 上下文管理 ────────────────────────────────────────────────────

    def _get_context(self, user_id: int) -> ConversationContext:
        if user_id not in self._contexts:
            self._contexts[user_id] = ConversationContext(user_id=user_id)
        return self._contexts[user_id]

    def clear_context(self, user_id: int) -> None:
        self._contexts.pop(user_id, None)
        logger.info(f"[Planner] 已清除 user {user_id} 的對話記憶")

    # ── 確認機制 ──────────────────────────────────────────────────────

    async def handle_confirm(self, user_id: int) -> str:
        """處理 /confirm 指令"""
        ctx = self._get_context(user_id)
        if not ctx.pending:
            return "目前沒有等待確認的操作。"
        tc = ctx.pending.tool_call
        ctx.pending = None
        return await self._run_tool_and_followup(ctx, tc)

    async def handle_cancel(self, user_id: int) -> str:
        """處理 /cancel 指令"""
        ctx = self._get_context(user_id)
        if not ctx.pending:
            return "目前沒有等待取消的操作。"
        desc = ctx.pending.description
        ctx.pending = None
        logger.info(f"[Planner] user {user_id} 取消了操作：{desc}")
        return f"✅ 已取消：{desc}"

    # ── 主入口 ────────────────────────────────────────────────────────

    async def process(self, user_id: int, user_msg: str) -> str:
        """
        處理一條使用者訊息。
        回傳 Agent 的文字回覆。
        """
        ctx = self._get_context(user_id)

        # 有待確認的操作，先提醒使用者處理
        if ctx.pending:
            return (
                f"⚠️ 還有一個待確認的操作：{ctx.pending.description}\n"
                "請先回覆 /confirm 確認，或 /cancel 取消。"
            )

        ctx.append(user_message(user_msg))

        if self._debug:
            logger.debug(f"[Planner] user={user_id} history={len(ctx.history)} msg={user_msg[:60]}")

        try:
            return await self._tool_call_loop(ctx, user_msg)
        except Exception as e:
            logger.error(f"[Planner] process 失敗：{e}", exc_info=True)
            return f"⚠️ 處理時發生錯誤，請再試一次。（{e}）"

    # ── Tool Call Loop ────────────────────────────────────────────────

    async def _tool_call_loop(self, ctx: ConversationContext, user_msg: str) -> str:
        """
        反覆呼叫 LLM，直到：
          a) LLM 回傳純文字（無 tool call）→ 回傳結果
          b) 遇到需要確認的工具 → 暫停，回傳確認提示
          c) 達到 _MAX_TOOL_ROUNDS → 強制結束
        """
        # 決定這輪用哪個 provider
        provider = self._resolve_provider(user_msg)
        gateway = LLMGateway.from_config(self._cfg, provider=provider)

        # 準備工具 schema
        tool_schemas = self._registry.get_all_schemas()

        # 在 history 前面插入 system prompt（不存入 ctx，每次動態組）
        def _messages_with_system() -> list[dict]:
            return [
                {"role": "system", "content": self._system_prompt},
                *ctx.messages(),
            ]

        for round_num in range(_MAX_TOOL_ROUNDS):
            response: LLMResponse = await gateway.chat(
                messages=_messages_with_system(),
                tools=tool_schemas,
            )

            if self._debug:
                logger.debug(
                    f"[Planner] round={round_num+1}/{_MAX_TOOL_ROUNDS} "
                    f"provider={provider} "
                    f"tool_calls={[tc.name for tc in response.tool_calls]}"
                )

            # ── 純文字回覆，結束 loop ──────────────────────────────
            if response.is_final:
                reply = response.content or "（無回覆）"
                ctx.append(assistant_message(content=reply))
                return reply

            # ── 有 tool call（目前取第一個）────────────────────────
            tc = response.tool_calls[0]

            # 把 assistant 的 tool_calls 記入 history（格式必須完整）
            ctx.append(assistant_message(
                content=response.content,
                tool_calls=response.tool_calls,
            ))

            # ── 確認機制 ──────────────────────────────────────────
            skill = self._registry.get_skill_by_tool(tc.name)
            if skill and getattr(skill, "requires_confirmation", False):
                desc = self._describe_tool_call(tc)
                ctx.pending = PendingConfirmation(tool_call=tc, description=desc)
                return (
                    f"⚠️ 即將執行：{desc}\n"
                    "確認請回覆 /confirm，取消請回覆 /cancel"
                )

            # ── 執行工具 ──────────────────────────────────────────
            tool_result = await self._registry.dispatch(tc.name, **tc.arguments)
            logger.info(f"[Tool] {tc.name} → {tool_result[:100]}")

            # 把結果加回 history
            ctx.append(tool_result_message(tc.id, tc.name, tool_result))

        # ── 超過最大輪數，強制取得純文字回覆 ─────────────────────────
        logger.warning(f"[Planner] 達到最大 tool call 次數（{_MAX_TOOL_ROUNDS}），強制結束")
        forced_messages = [
            {"role": "system", "content": self._system_prompt + "\n請直接用文字回覆使用者，不要再呼叫工具。"},
            *ctx.messages(),
        ]
        final: LLMResponse = await gateway.chat(messages=forced_messages, tools=[])
        reply = final.content or "已完成，但無法產生最終回覆，請重新提問。"
        ctx.append(assistant_message(content=reply))
        return reply

    # ── 確認後執行（/confirm 觸發）────────────────────────────────────

    async def _run_tool_and_followup(
        self, ctx: ConversationContext, tc: ToolCall
    ) -> str:
        """執行已確認的工具，然後讓 LLM 產生最終回覆"""
        tool_result = await self._registry.dispatch(tc.name, **tc.arguments)
        logger.info(f"[Tool/confirmed] {tc.name} → {tool_result[:100]}")
        ctx.append(tool_result_message(tc.id, tc.name, tool_result))

        provider = self._resolve_provider_from_tool(tc.name)
        gateway = LLMGateway.from_config(self._cfg, provider=provider)

        def _messages_with_system() -> list[dict]:
            return [
                {"role": "system", "content": self._system_prompt},
                *ctx.messages(),
            ]

        response = await gateway.chat(messages=_messages_with_system(), tools=[])
        reply = response.content or "操作已完成。"
        ctx.append(assistant_message(content=reply))
        return reply

    # ── Provider 路由 ─────────────────────────────────────────────────

    def _resolve_provider(self, user_msg: str) -> str:
        """
        根據訊息內容決定使用哪個 LLM provider。
        敏感訊息強制走 ollama（本地），否則依 cfg 設定。
        """
        try:
            from core.router import resolve_provider
            return resolve_provider(user_msg, self._cfg)
        except ImportError:
            # router 未實作時的 fallback
            provider = self._cfg.llm.provider
            return self._cfg.llm.cloud_provider if provider == "auto" else provider

    def _resolve_provider_from_tool(self, tool_name: str) -> str:
        """根據工具的 privacy_level 決定 follow-up 用的 provider"""
        local_tools = self._registry.get_local_only_tools()
        if tool_name in local_tools:
            return "ollama"
        provider = self._cfg.llm.provider
        return self._cfg.llm.cloud_provider if provider == "auto" else provider

    # ── 工具描述（確認提示用）────────────────────────────────────────

    _CONFIRM_DESCRIPTIONS: dict[str, str] = {
        "write_file":  "寫入檔案 {path}",
        "delete_file": "刪除檔案 {path}",
        "set_volume":  "設定音量為 {level}%",
        "open_app":    "開啟應用程式 {name}",
        "run_shell":   "執行 shell 指令：{command}",
        "send_email":  "寄送郵件給 {to}，主旨：{subject}",
    }

    def _describe_tool_call(self, tc: ToolCall) -> str:
        """產生人類可讀的操作描述，用於 /confirm 確認提示"""
        template = self._CONFIRM_DESCRIPTIONS.get(tc.name)
        if template:
            try:
                return template.format(**tc.arguments)
            except KeyError:
                pass
        # 沒有模板時，輸出工具名稱與參數
        args_str = ", ".join(f"{k}={v!r}" for k, v in tc.arguments.items())
        return f"{tc.name}（{args_str}）"
