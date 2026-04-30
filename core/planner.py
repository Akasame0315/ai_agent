"""
core/planner.py — 對話管理 + Tool Call Loop
路徑：core/planner.py

流程：
  使用者訊息
    → router 決定 provider（groq / ollama）
    → LLMGateway.chat()（附帶 skill 提供的 tool schemas）
    → 若 LLM 回傳 tool_calls：
        a. confirm_policy.needs_confirmation(tool) → 暫存 pending，回傳確認提示
        b. 否則直接 SkillRegistry.dispatch() → 結果加回 history → 繼續 loop
    → 最終 LLM 輸出純文字 → 回傳給 Telegram Bot

變更：
  - 使用 core/confirm_policy.py 做細粒度確認判斷
    （read_file、list_files 等不需要確認，即使在 requires_confirmation 的 skill 內）
"""
from __future__ import annotations

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

_MAX_TOOL_ROUNDS = 5


# ══════════════════════════════════════════════════════════════════════
# 對話上下文
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PendingConfirmation:
    tool_call: ToolCall
    description: str


@dataclass
class ConversationContext:
    user_id: int
    history: list[dict] = field(default_factory=list)
    max_history: int = 40
    pending: PendingConfirmation | None = None

    def append(self, msg: dict) -> None:
        self.history.append(msg)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def messages(self) -> list[dict]:
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
        "不確定的事情請直說，不要捏造資訊。\n"
        "使用工具後，請根據工具回傳的結果給出清楚的說明。"
    )


# ══════════════════════════════════════════════════════════════════════
# Planner
# ══════════════════════════════════════════════════════════════════════

class Planner:

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
        ctx = self._get_context(user_id)
        if not ctx.pending:
            return "目前沒有等待確認的操作。"
        tc = ctx.pending.tool_call
        ctx.pending = None
        return await self._run_tool_and_followup(ctx, tc)

    async def handle_cancel(self, user_id: int) -> str:
        ctx = self._get_context(user_id)
        if not ctx.pending:
            return "目前沒有等待取消的操作。"
        desc = ctx.pending.description
        ctx.pending = None
        logger.info(f"[Planner] user {user_id} 取消了操作：{desc}")
        return f"✅ 已取消：{desc}"

    # ── 主入口 ────────────────────────────────────────────────────────

    async def process(self, user_id: int, user_msg: str) -> str:
        ctx = self._get_context(user_id)

        if ctx.pending:
            return (
                f"⚠️ 還有一個待確認的操作：{ctx.pending.description}\n"
                "請先回覆 /confirm 確認，或 /cancel 取消。"
            )

        ctx.append(user_message(user_msg))

        if self._debug:
            logger.debug(
                f"[Planner] user={user_id} history={len(ctx.history)} "
                f"msg={user_msg[:60]}"
            )

        try:
            return await self._tool_call_loop(ctx, user_msg)
        except Exception as e:
            logger.error(f"[Planner] process 失敗：{e}", exc_info=True)
            return f"⚠️ 處理時發生錯誤，請再試一次。（{e}）"

    # ── Tool Call Loop ────────────────────────────────────────────────

    async def _tool_call_loop(self, ctx: ConversationContext, user_msg: str) -> str:
        provider = self._resolve_provider(user_msg)
        gateway = LLMGateway.from_config(self._cfg, provider=provider)
        tool_schemas = self._registry.get_all_schemas()

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
                    f"[Planner] round={round_num + 1}/{_MAX_TOOL_ROUNDS} "
                    f"provider={provider} "
                    f"tool_calls={[tc.name for tc in response.tool_calls]}"
                )

            # 純文字回覆
            if response.is_final:
                reply = response.content or "（無回覆）"
                ctx.append(assistant_message(content=reply))
                return reply

            # 有 tool call
            tc = response.tool_calls[0]

            ctx.append(assistant_message(
                content=response.content,
                tool_calls=response.tool_calls,
            ))

            # ── 確認策略（細粒度，依工具名稱判斷） ───────────────────
            from core.confirm_policy import needs_confirmation
            if needs_confirmation(tc.name, tc.arguments):
                desc = self._describe_tool_call(tc)
                ctx.pending = PendingConfirmation(tool_call=tc, description=desc)
                return (
                    f"⚠️ 即將執行：**{desc}**\n\n"
                    "請確認後回覆 /confirm，取消請回覆 /cancel"
                )

            # 直接執行
            tool_result = await self._registry.dispatch(tc.name, **tc.arguments)
            logger.info(f"[Tool] {tc.name} → {str(tool_result)[:120]}")
            ctx.append(tool_result_message(tc.id, tc.name, tool_result))

        # 超過最大輪數
        logger.warning(f"[Planner] 達到最大 tool call 次數（{_MAX_TOOL_ROUNDS}）")
        forced = [
            {
                "role": "system",
                "content": self._system_prompt
                + "\n請直接用文字回覆使用者，不要再呼叫工具。",
            },
            *ctx.messages(),
        ]
        final = await gateway.chat(messages=forced, tools=[])
        reply = final.content or "已完成，但無法產生最終回覆，請重新提問。"
        ctx.append(assistant_message(content=reply))
        return reply

    # ── 確認後執行 ────────────────────────────────────────────────────

    async def _run_tool_and_followup(
        self, ctx: ConversationContext, tc: ToolCall
    ) -> str:
        tool_result = await self._registry.dispatch(tc.name, **tc.arguments)
        logger.info(f"[Tool/confirmed] {tc.name} → {str(tool_result)[:120]}")
        ctx.append(tool_result_message(tc.id, tc.name, tool_result))

        provider = self._resolve_provider_from_tool(tc.name)
        gateway = LLMGateway.from_config(self._cfg, provider=provider)

        response = await gateway.chat(
            messages=[
                {"role": "system", "content": self._system_prompt},
                *ctx.messages(),
            ],
            tools=[],
        )
        reply = response.content or "操作已完成。"
        ctx.append(assistant_message(content=reply))
        return reply

    # ── Provider 路由 ─────────────────────────────────────────────────

    def _resolve_provider(self, user_msg: str) -> str:
        try:
            from core.router import resolve_provider
            return resolve_provider(user_msg, self._cfg)
        except ImportError:
            provider = self._cfg.llm.provider
            return self._cfg.llm.cloud_provider if provider == "auto" else provider

    def _resolve_provider_from_tool(self, tool_name: str) -> str:
        local_tools = self._registry.get_local_only_tools()
        if tool_name in local_tools:
            return "ollama"
        provider = self._cfg.llm.provider
        return self._cfg.llm.cloud_provider if provider == "auto" else provider

    # ── 工具描述（確認提示用）────────────────────────────────────────

    _CONFIRM_DESCRIPTIONS: dict[str, str] = {
        "write_file":       "寫入檔案 {filename}",
        "delete_file":      "刪除檔案 {filename}",
        "set_volume":       "設定音量（動作：{action}）",
        "open_application": "開啟應用程式「{target}」",
        "close_application":"關閉應用程式「{name}」",
        "run_shell":        "執行指令：{command}",
        "send_email":       "寄送郵件給 {to}，主旨：{subject}",
        "reply_email":      "回覆信件 {message_id}",
        "move_to_trash":    "刪除信件 {message_id}",
    }

    def _describe_tool_call(self, tc: ToolCall) -> str:
        template = self._CONFIRM_DESCRIPTIONS.get(tc.name)
        if template:
            try:
                return template.format(**tc.arguments)
            except KeyError:
                pass
        args_str = ", ".join(f"{k}={v!r}" for k, v in tc.arguments.items())
        return f"{tc.name}（{args_str}）"
